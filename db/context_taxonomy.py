"""Revisión multicolumna de pendientes; solo genera propuestas."""
from collections import Counter
from contextlib import closing
from datetime import datetime,timezone
import html,json,re,sqlite3
from pathlib import Path
from db.matching import products
from db.import_excel import search_key

FIELDS=['DEPARTMENT','REVENUEGROUP','EXCHANGEGROUP','INVENTORYGROUP','Report Group']
CATEGORIES={'AUDIO':'Audio','VIDEO':'Video','ILUMINACION':'Iluminación','ELECTRICIDAD':'Energía',
 'INFORMATICA':'Informática y redes','COMPUTACION':'Informática y redes','CABLE':'Conectividad',
 'CABLES':'Conectividad','TRADUCCION SIMULTANEA':'Interpretación y comunicaciones'}

def evaluate(p):
    evidence=[{'field':f,'value':p.get(f)} for f in FIELDS]
    d=p['description_key']; dep=search_key(p.get('DEPARTMENT') or ''); rev=search_key(p.get('REVENUEGROUP') or '')
    ex=search_key(p.get('EXCHANGEGROUP') or ''); inv=search_key(p.get('INVENTORYGROUP') or '')
    report=search_key(p.get('Report Group') or '')
    cats={CATEGORIES[x] for x in [dep,rev] if x in CATEGORIES}
    category=next(iter(cats)) if len(cats)==1 else None
    alerts=[]
    if len(cats)>1: alerts.append('Department y RevenueGroup sugieren categorias distintas')
    if rev and rev not in CATEGORIES: alerts.append('RevenueGroup sin equivalencia especifica: se conserva como contexto')
    family=None; reason='Solo contexto general; falta evidencia para elegir familia'
    protected=p['quarantined'] or p.get('Type')!='ITEM' or p.get('Package')=='PACKAGE' or bool(re.search(r'PROBAR|NO USAR|FICHA MALA|ITEM MISSING',d))
    if protected: reason='Conservar revision por paquete, tipo, cuarentena o advertencia operacional'
    elif len(cats)>1: reason='Contradiccion entre clasificaciones generales: no asignar familia'
    elif re.match(r'^(CHICOTE|EXTENSION|CORDON|COPLA)\b',d) and ('CABLE' in ex or report=='CABLES' or dep in ['CABLE','CABLES']):
        family='Cables y adaptadores'; reason='Descripcion de conexion y grupo/department de cables'
    elif re.match(r'^(TABLERO|ZAPATILLA|ZAPATILLAS)\b',d) and (dep in ['ELECTRICIDAD','CABLE','CABLES'] or ex=='CABLES DE ENERGIA' or inv=='TABLERO ELECTRICO'):
        family='Distribución eléctrica';reason='Descripcion de distribucion electrica respaldada por grupo electrico/cableado'
    elif re.match(r'^TELON\b',d) and (dep=='VIDEO' or rev=='VIDEO'):
        family='Pantallas de proyección';reason='Descripcion de telon y contexto Video; grupo Proyectores demasiado amplio'
    elif re.match(r'^(VIDEOPROYECTOR|PROYECTOR)\b',d) and (dep=='VIDEO' or rev=='VIDEO'):
        family='Proyectores';reason='Equipo principal identificado y contexto Video; un lente incluido no lo convierte en accesorio'
    elif re.match(r'^(PARANTE|CARGADOR)\b',d) and (dep=='AUDIO' or rev=='AUDIO') and ('MICROFONO' in ex or 'MICROFONO' in report or 'MICROFONO' in d):
        family='Accesorios de audio';reason='Descripcion de accesorio y contexto de microfonia'
    elif re.match(r'^MICROFONO.*DEBATE',d) and (dep=='AUDIO' or rev=='AUDIO' or report=='MIC DEBATE'):
        family='Debate y votación';reason='Funcion debate explicita; conectividad y departamento se conservan como atributos/contexto'
    elif re.match(r'^(CONVERSOR|CONVERTIDOR)\b',d) and dep=='VIDEO' and re.search(r'VGA|HDMI|SDI',d):
        family='Procesamiento y distribución de video';reason='Conversion de señal explicita y contexto Video'
    if inv: alerts.append('InventoryGroup disponible: '+inv)
    if family: status='familia propuesta'
    elif category: status='solo categoria'
    else: status='pendiente'
    return {'family':family,'category':category,'status':status,'reason':reason,'alerts':alerts,'evidence':evidence}

def main():
    original=json.loads(Path('outputs/estandarizacion/revision_condicionada.json').read_text(encoding='utf-8'))
    pending=[r for r in original['rows'] if r['status']=='pendiente']
    with closing(sqlite3.connect('data/rla_modelo_v4.sqlite3')) as db:
        db.execute('PRAGMA foreign_keys=ON'); items=products(db,1)
        backup=Path('data/backups')/('rla_pre_context_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.sqlite3')
        with closing(sqlite3.connect(backup)) as archive: db.backup(archive)
        families={n:(i,c) for i,n,c in db.execute('SELECT f.family_id,f.name,c.name FROM families f JOIN categories c USING(category_id)')}
        categories=dict(db.execute('SELECT name,category_id FROM categories'))
        rows=[]; inserted=0
        with db:
            db.execute("INSERT OR IGNORE INTO standardization_rules(rule_key,version,input_field,condition_json,output_field,status) VALUES('context-pending','context-1','description+five_groups+type+package',?,'family_or_category','draft')",(json.dumps({'implementation':'db/context_taxonomy.py','scope':'pendientes conditional-1','no_majority_vote':True}),))
            rule=db.execute("SELECT rule_id FROM standardization_rules WHERE rule_key='context-pending' AND version='context-1'").fetchone()[0]
            for previous in pending:
                p=items[previous['code']];r=dict(code=p['code'],description=p['Description'],row=p['rows'][0],previous_reason=previous['reason'],**evaluate(p))
                if r['family']:
                    cat=families[r['family']][1]
                    if r['category'] and r['category']!=cat:r['alerts'].append('Categoria propuesta por funcion difiere del contexto: '+r['category'])
                    r['category']=cat
                raw_id=db.execute('SELECT raw_record_id FROM raw_records WHERE load_id=1 AND excel_row=?',(r['row'],)).fetchone()[0]
                target='family_id' if r['family'] else 'category_id'
                value=str(families[r['family']][0]) if r['family'] else str(categories[r['category']]) if r['category'] else None
                cursor=db.execute("INSERT OR IGNORE INTO field_standardization_proposals(raw_record_id,rule_id,target_field,proposed_value,status,reason) VALUES(?,?,?,?,'pending',?)",(raw_id,rule,target,value,json.dumps(r,ensure_ascii=False)))
                inserted+=cursor.rowcount;rows.append(r)
            if inserted:db.execute("INSERT INTO audit_events(entity_type,entity_id,action,after_json,actor,reason) VALUES('standardization_rule',?,'context_proposals',?,'context_taxonomy','Propuestas multicolumna sin aprobacion')",(str(rule),json.dumps({'inserted':inserted})))
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    summary={'reviewed':len(rows),'status':dict(Counter(r['status'] for r in rows)),
             'inventorygroup_present':sum(bool(items[r['code']].get('INVENTORYGROUP')) for r in rows),
             'inserted':inserted,'catalog_changed':False,'version':'context-1'}
    out=Path('outputs/estandarizacion');(out/'revision_contexto.json').write_text(json.dumps({'summary':summary,'rows':rows},ensure_ascii=False,indent=2),encoding='utf-8')
    esc=lambda v:html.escape(str(v))
    parts=['<!doctype html><html lang="es"><meta charset="utf-8"><title>RLA · Revisión multicolumna</title><style>body{font:16px/1.5 system-ui;color:#243943;margin:30px}table{border-collapse:collapse;width:100%}td,th{padding:12px;border-bottom:1px solid #ccd8dd;text-align:left;vertical-align:top}th{position:sticky;top:0;background:#edf3f5}h1{font-size:28px}</style><h1>Revisión multicolumna de pendientes</h1><p>Fuente: Lista_Productos.xlsx, carga 1. Se reevalúan únicamente los pendientes de conditional-1. Todo sigue pendiente de aprobación; no se asignaron familias al catálogo.</p><p>'+esc(summary['status'])+'</p><p>Categoria sola no significa familia resuelta. Las etiquetas contables desconocidas no se interpretan y no se decide por mayoria. Las nuevas propuestas complementan las anteriores, que permanecen como historial.</p><table><tr><th>Código y descripción</th><th>Propuesta</th><th>Evidencia</th><th>Motivo y alertas</th></tr>']
    for r in rows:parts.append('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in [r['code']+' / '+r['description']+' (fila '+str(r['row'])+')',(r['category'] or 'Sin categoria')+' / '+(r['family'] or 'Familia pendiente'),' · '.join(e['field']+': '+str(e['value'] or 'vacío') for e in r['evidence']),r['reason']+' · '+' · '.join(r['alerts'])])+'</tr>')
    parts.append('</table></html>');(out/'revision_contexto.html').write_text(''.join(parts),encoding='utf-8');print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
