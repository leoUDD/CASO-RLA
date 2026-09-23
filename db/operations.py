"""Operaciones transaccionales del catálogo. Ninguna importación publica por sí sola."""
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

from db.build_catalog import VERSION, build
from db.import_excel import clean, decimal_text

DEFAULT_DB = Path('data/rla_modelo_v4.sqlite3')
TECHNICAL = {'DEFAULTITEM', 'DEFAULTLABOR', 'DEFAULTMISC', 'SYSTEMDEFAULT'}


def connect(path=DEFAULT_DB):
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db


def backup(db, directory=Path('data/backups')):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ('rla_operaciones_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.sqlite3')
    with closing(sqlite3.connect(path)) as target:
        db.backup(target)
    return str(path)


def setup(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS technical_decisions(
      raw_record_id INTEGER PRIMARY KEY REFERENCES raw_records,
      decision TEXT NOT NULL CHECK(decision IN ('pending','exclude')),
      actor TEXT NOT NULL, reason TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS publications(
      load_id INTEGER PRIMARY KEY REFERENCES loads, actor TEXT NOT NULL,
      reason TEXT NOT NULL, snapshot_at TEXT NOT NULL,
      published_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS manual_requests(
      request_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL,
      master_id INTEGER NOT NULL REFERENCES master_products);
    CREATE TABLE IF NOT EXISTS quality_samples(
      load_id INTEGER NOT NULL REFERENCES loads,legacy_id INTEGER NOT NULL REFERENCES legacy_products,
      original_json TEXT NOT NULL, PRIMARY KEY(load_id,legacy_id));
    ''')
    if 'date_basis' not in [r[1] for r in db.execute('PRAGMA table_info(publications)')]:
        with db:
            db.execute("ALTER TABLE publications ADD COLUMN date_basis TEXT NOT NULL DEFAULT 'confirmed' CHECK(date_basis IN ('confirmed','received_at'))")


def audit(db, kind, key, action, before, after, actor, reason):
    db.execute('INSERT INTO audit_events(entity_type,entity_id,action,before_json,after_json,actor,reason) VALUES(?,?,?,?,?,?,?)',
               (kind, str(key), action, json.dumps(before, ensure_ascii=False), json.dumps(after, ensure_ascii=False), actor, reason))


def credentials(data):
    actor, reason = clean(data.get('actor')), clean(data.get('reason'))
    if not actor or not reason:
        raise ValueError('Revisor y motivo son obligatorios')
    return actor, reason


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def review_rows(db, load_id):
    rows = [dict(r) for r in db.execute('''SELECT u.*,l.legacy_code,m.master_code,m.standard_name,
       f.name family,c.name category FROM unified_catalog_reviews u
       JOIN legacy_products l USING(legacy_id) LEFT JOIN master_products m ON m.master_id=u.master_id
       LEFT JOIN families f ON f.family_id=u.family_id LEFT JOIN categories c ON c.category_id=f.category_id
       WHERE u.load_id=? AND u.version=? ORDER BY l.legacy_code''', (load_id, VERSION))]
    for row in rows:
        row['revision'] = digest(row)
        row['evidence'] = json.loads(row.pop('evidence_json'))
    return rows


def pending_group(row):
    reason = row['reason'].lower()
    evidence = row['evidence']
    if row['status'] == 'quarantined': return 'Cuarentena'
    if 'paquete' in reason: return 'Paquetes'
    if 'advertencia' in reason: return 'Advertencias operacionales'
    if 'tipo de' in reason: return 'Servicios, repuestos o cargos'
    if len(evidence.get('groups', [])) > 1 or len(evidence.get('lexical', [])) > 1: return 'Evidencia contradictoria'
    if row['family_id']: return 'Familia propuesta por confirmar'
    return 'Sin familia suficiente'


def sample(rows):
    """Muestra reproducible estratificada, hasta cinco códigos por familia. No estima exactitud."""
    strata = defaultdict(list)
    for row in rows:
        if row['status'] == 'approved_by_rule': strata[row['family']].append(row)
    chosen = []
    for family in sorted(strata):
        chosen.extend(sorted(strata[family], key=lambda r: digest(r['legacy_code']))[:5])
    return chosen


def ensure_sample(db, load_id):
    if not db.execute('SELECT 1 FROM quality_samples WHERE load_id=?',(load_id,)).fetchone():
        with db:
            db.executemany('INSERT INTO quality_samples VALUES(?,?,?)',
                [(load_id,r['legacy_id'],json.dumps(r,ensure_ascii=False)) for r in sample(review_rows(db,load_id))])


def save_review(db, data):
    actor, reason = credentials(data)
    with db:
        db.execute('BEGIN IMMEDIATE')
        row = next((r for r in review_rows(db, int(data['load_id'])) if r['legacy_id'] == int(data['legacy_id'])), None)
        if not row: raise ValueError('Revisión inexistente')
        if row['revision'] != data.get('revision'): raise ValueError('La revisión cambió; recargue antes de guardar')
        if row['status'] == 'quarantined': raise ValueError('Resolver cuarentena en la sección de registros técnicos')
        if db.execute('SELECT 1 FROM unified_catalog_reviews WHERE master_id=? AND load_id>? LIMIT 1',(row['master_id'],row['load_id'])).fetchone():
            raise ValueError('Hay una carga más reciente para este maestro; revise esa carga')
        decision = data.get('decision')
        if decision not in {'approve', 'reject', 'pending'}: raise ValueError('Decisión inválida')
        fid = int(data['family_id']) if data.get('family_id') else None
        if decision == 'approve' and not fid: raise ValueError('Seleccione una familia')
        if fid and not db.execute("SELECT 1 FROM families WHERE family_id=? AND status<>'inactive'", (fid,)).fetchone():
            raise ValueError('Familia inexistente o inactiva')
        status = {'approve':'approved_by_reviewer', 'reject':'rejected', 'pending':'pending'}[decision]
        master = dict(db.execute('SELECT * FROM master_products WHERE master_id=?', (row['master_id'],)).fetchone())
        # Rechazar o reabrir retira únicamente la clasificación que esta revisión aplicó.
        applied = fid if decision == 'approve' else None
        if decision == 'approve' or (row['status'] in {'approved_by_rule','approved_by_reviewer'} and master['family_id'] == row['family_id']):
            db.execute('UPDATE master_products SET family_id=?,category_id=NULL WHERE master_id=?', (applied, row['master_id']))
        db.execute('UPDATE unified_catalog_reviews SET status=?,family_id=?,reason=? WHERE load_id=? AND legacy_id=? AND version=?',
                   (status, fid, reason, row['load_id'], row['legacy_id'], VERSION))
        if decision == 'approve':
            db.execute("UPDATE families SET status='approved' WHERE family_id=?", (fid,))
            db.execute("UPDATE categories SET status='approved' WHERE category_id=(SELECT category_id FROM families WHERE family_id=?)", (fid,))
        audit(db, 'catalog_review', f"{row['load_id']}:{row['legacy_id']}", decision,
              {'review':row, 'master':master}, {'status':status, 'family_id':fid}, actor, reason)
    return {'saved':True}


def technical_rows(db, load_id):
    result = []
    for r in db.execute('''SELECT r.*,n.normalized_json,t.decision,t.actor,t.reason FROM raw_records r
       JOIN normalized_records n USING(raw_record_id) LEFT JOIN technical_decisions t USING(raw_record_id)
       WHERE r.load_id=? AND r.validation_status='quarantined' ORDER BY r.excel_row''', (load_id,)):
        row = dict(r)
        row['data'] = json.loads(row.pop('normalized_json'))
        row['eligible'] = row['data'].get('Product ID') in TECHNICAL
        row['decision'] = row['decision'] or 'pending'
        result.append(row)
    return result


def save_technical(db, data):
    actor, reason = credentials(data)
    with db:
        db.execute('BEGIN IMMEDIATE')
        row = next((r for r in technical_rows(db, int(data['load_id'])) if r['raw_record_id'] == int(data['raw_record_id'])), None)
        if not row or not row['eligible']: raise ValueError('Solo los cuatro códigos técnicos admiten exclusión explícita; corrija las otras filas en origen')
        if db.execute('SELECT 1 FROM publications WHERE load_id=?', (data['load_id'],)).fetchone(): raise ValueError('Carga publicada: use una nueva carga para cambiar su alcance')
        decision = data.get('decision')
        if decision not in {'pending','exclude'}: raise ValueError('Decisión inválida')
        db.execute('INSERT INTO technical_decisions VALUES(?,?,?,?) ON CONFLICT(raw_record_id) DO UPDATE SET decision=excluded.decision,actor=excluded.actor,reason=excluded.reason',
                   (row['raw_record_id'], decision, actor, reason))
        audit(db, 'technical_record', row['raw_record_id'], decision, row, data, actor, reason)
    return {'saved':True}


def preview(db, load_id):
    load = db.execute('SELECT * FROM loads WHERE load_id=?', (load_id,)).fetchone()
    if not load: raise ValueError('Carga inexistente')
    load = dict(load)
    current = db.execute('SELECT load_id FROM active_loads WHERE source_id=?', (load['source_id'],)).fetchone()
    active = current[0] if current else None
    technical = technical_rows(db, load_id)
    excluded = sum(r['eligible'] and r['decision'] == 'exclude' for r in technical)
    global_errors = db.execute("SELECT count(*) FROM validation_issues WHERE load_id=? AND raw_record_id IS NULL AND severity='error'", (load_id,)).fetchone()[0]
    accepted = db.execute("SELECT count(*) FROM raw_records WHERE load_id=? AND validation_status='accepted'", (load_id,)).fetchone()[0]
    missing = db.execute('''SELECT count(*) FROM raw_records r JOIN normalized_records n USING(raw_record_id)
      LEFT JOIN legacy_products l ON l.source_id=? AND l.legacy_code=json_extract(n.normalized_json,'$."Product ID"')
      LEFT JOIN product_mappings m USING(legacy_id) WHERE r.load_id=? AND r.validation_status='accepted' AND m.master_id IS NULL''', (load['source_id'], load_id)).fetchone()[0]
    newest = db.execute('SELECT max(p.load_id) FROM publications p JOIN loads l USING(load_id) WHERE l.source_id=?', (load['source_id'],)).fetchone()[0]
    stale = newest is not None and load_id <= newest and active != load_id
    current_codes={r[0] for r in db.execute('SELECT DISTINCT l.legacy_code FROM current_inventory i JOIN legacy_products l USING(legacy_id) WHERE i.source_id=?',(load['source_id'],))}
    incoming_codes={r[0] for r in db.execute('''SELECT DISTINCT json_extract(n.normalized_json,'$."Product ID"') FROM raw_records r
      JOIN normalized_records n USING(raw_record_id) WHERE r.load_id=? AND r.validation_status='accepted' ''',(load_id,))}
    gone=len(current_codes-incoming_codes)
    result = dict(load=load, active_load=active, accepted=accepted, excluded=excluded,
                  unresolved=len(technical)-excluded, global_errors=global_errors, missing_masters=missing,
                  absent_codes=gone, stale=stale, already_published=active==load_id,
                  pending_families=db.execute("SELECT count(*) FROM unified_catalog_reviews WHERE load_id=? AND version=? AND status IN ('pending','rejected')", (load_id,VERSION)).fetchone()[0])
    result['ready'] = accepted > 0 and not (result['unresolved'] or global_errors or missing or stale or active==load_id or load['status']=='rejected')
    result['token'] = digest(result)
    return result


def publish(db, data):
    actor, reason = credentials(data)
    if data.get('full_snapshot') is not True: raise ValueError('Confirme que el archivo es completo para esta fuente')
    with db:
        db.execute('BEGIN IMMEDIATE')
        p = preview(db, int(data['load_id']))
        if p['token'] != data.get('token'): raise ValueError('La previsualización cambió; vuelva a consultarla')
        if not p['ready']: raise ValueError('La carga tiene bloqueos o ya fue publicada')
        load = p['load']; source = load['source_id']; load_id = load['load_id']
        basis = data.get('date_basis','confirmed')
        if basis not in {'confirmed','received_at'}: raise ValueError('Origen de fecha inválido')
        date = load['received_at'] if basis=='received_at' else clean(data.get('snapshot_at'))
        try:
            instant = datetime.fromisoformat(date.replace('Z','+00:00'))
            if instant.tzinfo is None: raise ValueError()
        except ValueError: raise ValueError('Indique una fecha ISO con zona horaria')
        last = db.execute('SELECT snapshot_at,date_basis FROM publications WHERE load_id=?', (p['active_load'],)).fetchone()
        if last and basis=='confirmed' and last['date_basis']=='confirmed' and instant <= datetime.fromisoformat(last['snapshot_at']):
            raise ValueError('La fecha de corte debe ser posterior a la vigente')
        records = db.execute("SELECT r.raw_record_id,n.normalized_json FROM raw_records r JOIN normalized_records n USING(raw_record_id) WHERE r.load_id=? AND r.validation_status='accepted'", (load_id,)).fetchall()
        for raw_id, payload in records:
            n = json.loads(payload)
            db.execute('INSERT INTO sites(source_id,source_site_code,name) VALUES(?,?,?) ON CONFLICT(source_id,source_site_code) DO UPDATE SET name=excluded.name', (source,n['SITEID'],n['SITENAME']))
            site = db.execute('SELECT site_id FROM sites WHERE source_id=? AND source_site_code=?', (source,n['SITEID'])).fetchone()[0]
            legacy = db.execute('SELECT legacy_id FROM legacy_products WHERE source_id=? AND legacy_code=?', (source,n['Product ID'])).fetchone()[0]
            sid = db.execute('''INSERT INTO inventory_snapshots(source_id,load_id,raw_record_id,legacy_id,site_id,stock,cost,replacement_cost,can_rent,can_sell,can_subrent,bin_location,shelf_location,maximum_qty,minimum_qty,reorder_qty)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (source,load_id,raw_id,legacy,site,n.get('Stock'),n.get('Cost'),n.get('Replacement Cost'),n.get('CANRENT'),n.get('CANSELL'),n.get('CANSUBRENT'),n.get('Bin Loaction'),n.get('Shelf Location'),n.get('MAXIMUMQTY'),n.get('MINIMUMQTY'),n.get('REORDERQTY'))).lastrowid
            flags=[]
            for field,mapping in [('AFFECTSAVAILABILITY',{'TRUE':1,'FALSE':0}),('ISFREIGHT',{'FREIGHT':1,'NOTFREIGHT':0}),('ISMISCITEM',{'MISCITEM':1,'NOTMISCITEM':0})]:
                value=n.get(field)
                if value is not None and value not in mapping: raise ValueError('Bandera no reconocida: '+field+'='+str(value))
                flags.append(mapping.get(value))
            db.execute('UPDATE inventory_snapshots SET affects_availability=?,is_freight=?,is_misc_item=? WHERE snapshot_id=?',(*flags,sid))
            db.execute('INSERT INTO snapshot_commercial(snapshot_id,cost,replacement_cost,reported_total_cost,retail_price,low_retail_price,msrp) VALUES(?,?,?,?,?,?,?)', (sid,n.get('Cost'),n.get('Replacement Cost'),n.get('CostoTotal'),n.get('RETAILPRICE'),n.get('LOWRETAILPRICE'),n.get('MSRP')))
            db.execute('INSERT INTO snapshot_classifications SELECT ?,field_name,value_id FROM record_classifications WHERE raw_record_id=?', (sid,raw_id))
        db.execute("UPDATE loads SET status='valid',snapshot_at=? WHERE load_id=?", (instant.isoformat(),load_id))
        db.execute('INSERT INTO active_loads VALUES(?,?) ON CONFLICT(source_id) DO UPDATE SET load_id=excluded.load_id', (source,load_id))
        db.execute('INSERT INTO publications(load_id,actor,reason,snapshot_at,date_basis) VALUES(?,?,?,?,?)', (load_id,actor,reason,instant.isoformat(),basis))
        audit(db,'load',load_id,'publish_full_snapshot',p,{'rows':len(records),'excluded':p['excluded'],'date_basis':basis,'reference_at':instant.isoformat()},actor,reason)
    return {'published':True, 'rows':len(records), 'load_id':load_id,'date_basis':basis,'reference_at':instant.isoformat()}


def manual(db, data):
    actor, reason = credentials(data)
    name = clean(data.get('name')); request = clean(data.get('request_id'))
    if not name or not request: raise ValueError('Nombre e identificador de solicitud obligatorios')
    fingerprint = digest(data)
    with db:
        db.execute('BEGIN IMMEDIATE')
        old = db.execute('SELECT * FROM manual_requests WHERE request_id=?', (request,)).fetchone()
        if old:
            if old['payload_hash'] != fingerprint: raise ValueError('Solicitud reutilizada con datos diferentes')
            return {'master_id':old['master_id'], 'repeated':True}
        family = int(data['family_id']) if data.get('family_id') else None
        if family and not db.execute("SELECT 1 FROM families WHERE family_id=? AND status<>'inactive'", (family,)).fetchone(): raise ValueError('Familia inválida')
        mid = db.execute('''INSERT INTO master_products(standard_name,product_type,model,package_type,serialization,origin,created_by,creation_reason,family_id)
           VALUES(?,?,?,?,?,'manual',?,?,?)''', (name,data.get('product_type'),clean(data.get('model')) or None,data.get('package_type') or None,data.get('serialization') or None,actor,reason,family)).lastrowid
        stock = decimal_text(data.get('stock') or '')
        if data.get('site_id'):
            db.execute('INSERT INTO manual_site_entries(master_id,site_id,stock,created_by,reason) VALUES(?,?,?,?,?)', (mid,int(data['site_id']),stock,actor,reason))
        elif stock is not None: raise ValueError('Una existencia requiere sitio; puede crear el producto sin ambos')
        db.execute('INSERT INTO manual_requests VALUES(?,?,?)', (request,fingerprint,mid))
        audit(db,'master_product',mid,'manual_create',None,data,actor,reason)
        code = db.execute('SELECT master_code FROM master_products WHERE master_id=?', (mid,)).fetchone()[0]
    return {'master_id':mid,'master_code':code,'repeated':False}
