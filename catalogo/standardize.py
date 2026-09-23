"""Estandarización completa sobre SQLite: sitios, nombres, marcas, familias, código maestro y duplicados.

Repetible: se ejecuta tras cada carga. Los códigos estándar ya asignados no cambian, las decisiones de
revisores y los datos manuales prevalecen sobre las reglas, y nada se fusiona ni se borra.
"""
from collections import Counter, defaultdict
import hashlib
import json
from catalogo import std_rules as R

SCHEMA = '''
CREATE TABLE IF NOT EXISTS product_standards(
  master_id INTEGER PRIMARY KEY REFERENCES master_products,
  standard_code TEXT UNIQUE,
  standard_name TEXT,
  manufacturer_id INTEGER REFERENCES manufacturers,
  model TEXT,
  family_id INTEGER REFERENCES families,
  method TEXT NOT NULL,
  operational_status TEXT NOT NULL,
  duplicate_key TEXT,
  duplicate_group TEXT,
  legacy_codes TEXT,
  countries TEXT,
  stock_available REAL,
  sites_with_stock INTEGER,
  load_id INTEGER REFERENCES loads,
  search_text TEXT NOT NULL,
  rules_version TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
CREATE INDEX IF NOT EXISTS product_standards_family ON product_standards(family_id);
CREATE INDEX IF NOT EXISTS product_standards_duplicate ON product_standards(duplicate_group);
CREATE INDEX IF NOT EXISTS product_standards_dupkey ON product_standards(duplicate_key);
CREATE TABLE IF NOT EXISTS standard_code_links(
  link_id INTEGER PRIMARY KEY, source_master_id INTEGER NOT NULL REFERENCES master_products,
  target_master_id INTEGER NOT NULL REFERENCES master_products, retired_code TEXT, legacy_codes_json TEXT NOT NULL,
  actor TEXT NOT NULL, reason TEXT NOT NULL, linked_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  undone_at TEXT);
CREATE TABLE IF NOT EXISTS standardization_runs(
  run_id INTEGER PRIMARY KEY, load_id INTEGER NOT NULL REFERENCES loads, rules_version TEXT NOT NULL,
  summary_json TEXT NOT NULL CHECK(json_valid(summary_json)),
  run_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')));
'''


def _columns(db, table):
    return {r[1] for r in db.execute(f'PRAGMA table_info({table})')}


def setup(db):
    db.executescript(SCHEMA)
    with db:
        for column, ddl in [('site_type', 'TEXT'), ('country_source', 'TEXT'), ('type_source', 'TEXT')]:
            if column not in _columns(db, 'sites'):
                db.execute(f'ALTER TABLE sites ADD COLUMN {column} {ddl}')
        # presence_countries: países donde existe el producto; stock_by_country: stock disponible por país (JSON);
        # duplicate_kind: 'Mismo país' (ficha duplicada) u 'Otro país' (equivalente entre países).
        for column in ('presence_countries', 'stock_by_country', 'duplicate_kind'):
            if column not in _columns(db, 'product_standards'):
                db.execute(f'ALTER TABLE product_standards ADD COLUMN {column} TEXT')
        db.executemany('INSERT OR IGNORE INTO countries(country_code,name) VALUES(?,?)', R.COUNTRIES.items())


def ensure_taxonomy(db, load_id):
    """Crea las categorías y familias de std_rules.TAXONOMY que falten (una base nueva las recibe todas)."""
    setup(db)
    with db:
        if 'status' not in _columns(db, 'families'):
            db.execute("ALTER TABLE families ADD COLUMN status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','approved','inactive'))")
        for family, (category, cat, fam) in R.TAXONOMY.items():
            row = db.execute('SELECT category_id FROM categories WHERE name=? AND parent_id IS NULL', (category,)).fetchone()
            cid = row[0] if row else db.execute("INSERT INTO categories(name,category_code,status) VALUES(?,?,'draft')",
                                                (category, 'CAT-' + cat)).lastrowid
            if not db.execute('SELECT 1 FROM families WHERE category_id=? AND name=?', (cid, family)).fetchone():
                db.execute("INSERT INTO families(category_id,family_code,name,status) VALUES(?,?,?,'draft')",
                           (cid, f'FAM-{cat}-{fam}', family))


def _families(db):
    return {name: fid for fid, name in db.execute('SELECT family_id,name FROM families')}


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _rows(db, load_id):
    rows = []
    for status, payload in db.execute('''SELECT r.validation_status,n.normalized_json FROM raw_records r
            JOIN normalized_records n USING(raw_record_id) WHERE r.load_id=? ORDER BY r.excel_row''', (load_id,)):
        row = json.loads(payload)
        row['_status'] = status
        rows.append(row)
    return rows


def _standardize_sites(db, source_id, rows):
    by_site = defaultdict(list)
    for r in rows:
        if r.get('SITEID'):
            by_site[r['SITEID']].append(r)
    existing = {code: (sid, csrc, tsrc) for sid, code, csrc, tsrc in db.execute(
        'SELECT site_id,source_site_code,country_source,type_source FROM sites WHERE source_id=?', (source_id,))}
    countries = {code: cid for cid, code in db.execute('SELECT country_id,country_code FROM countries')}
    for code, items in by_site.items():
        name = items[0].get('SITENAME') or code
        prefixes = Counter(p for p in (R.code_country(i.get('Product ID')) for i in items) if p)
        prefixed = sum(prefixes.values())
        top, top_n = prefixes.most_common(1)[0] if prefixes else (None, 0)
        country, why = R.site_country(code, name, prefixed / len(items), top, top_n / prefixed if prefixed else 0)
        kind = R.site_type(code, name)
        sid, csrc, tsrc = existing.get(code, (None, None, None))
        if sid is None:
            db.execute('INSERT INTO sites(source_id,source_site_code,name,country_id,country_source,site_type,type_source) VALUES(?,?,?,?,?,?,?)',
                       (source_id, code, name, countries.get(country), why, kind, 'regla'))
            continue
        # Lo asignado a mano por una persona no se sobrescribe.
        if csrc != 'manual':
            db.execute('UPDATE sites SET country_id=?,country_source=? WHERE site_id=?', (countries.get(country), why, sid))
        if tsrc != 'manual':
            db.execute("UPDATE sites SET site_type=?,type_source='regla' WHERE site_id=?", (kind, sid))
        db.execute('UPDATE sites SET name=? WHERE site_id=?', (name, sid))
    return {code: (country_code, kind) for code, country_code, kind in db.execute(
        '''SELECT s.source_site_code,c.country_code,s.site_type FROM sites s LEFT JOIN countries c USING(country_id)
           WHERE s.source_id=?''', (source_id,))}


def _manufacturer(db, brand_key, spelling, source_id, cache):
    if not brand_key:
        return None
    if brand_key not in cache:
        row = db.execute('SELECT manufacturer_id FROM manufacturers WHERE canonical_key=?', (brand_key,)).fetchone()
        canonical = next((v for k, v in R.BRAND_ALIASES.items() if R.key(v) == brand_key), None) or spelling.upper()
        cache[brand_key] = row[0] if row else db.execute(
            'INSERT INTO manufacturers(canonical_name,canonical_key) VALUES(?,?)', (canonical, brand_key)).lastrowid
    mid = cache[brand_key]
    if source_id is not None and R.key(spelling):
        db.execute('''INSERT OR IGNORE INTO manufacturer_aliases(manufacturer_id,source_id,alias_key,original_example,approved_by,approved_at,reason)
                      VALUES(?,?,?,?,'regla std-1',strftime('%Y-%m-%dT%H:%M:%fZ','now'),'Misma marca tras normalizar escritura')''',
                   (mid, source_id, R.key(spelling), spelling))
    return mid


def _next_codes(db):
    counters = defaultdict(int)
    for (code,) in db.execute('SELECT standard_code FROM product_standards WHERE standard_code IS NOT NULL'):
        prefix, _, number = code.rpartition('-')
        counters[prefix] = max(counters[prefix], int(number))
    return counters


def _group_id(dup_key):
    return 'DUP-' + hashlib.sha1(dup_key.encode()).hexdigest()[:6].upper()


def apply(db, load_id, actor='estandarizador'):
    """Estandariza todos los productos de una carga y deja el resultado en product_standards."""
    ensure_taxonomy(db, load_id)
    source_id = db.execute('SELECT source_id FROM loads WHERE load_id=?', (load_id,)).fetchone()[0]
    rows = _rows(db, load_id)
    families = _families(db)
    with db:
        db.execute('BEGIN IMMEDIATE')
        sites = _standardize_sites(db, source_id, rows)
        masters, legacy_ids, current_family, linked = {}, {}, {}, set()
        for code, lid, mid, origin, fam, how in db.execute(
                '''SELECT l.legacy_code,l.legacy_id,p.master_id,m.origin,m.family_id,p.method FROM legacy_products l
                   JOIN product_mappings p USING(legacy_id) JOIN master_products m USING(master_id) WHERE l.source_id=?''', (source_id,)):
            masters[code], legacy_ids[code], current_family[mid] = (mid, origin), lid, fam
            if how == 'reviewed':
                linked.add(code)
        retired = defaultdict(list)  # códigos estándar retirados por vinculación → siguen encontrándose al buscar
        for target, code in db.execute('SELECT target_master_id,retired_code FROM standard_code_links WHERE undone_at IS NULL AND retired_code IS NOT NULL'):
            retired[target].append(code)
        brand_names = {}
        reviews = {code: (status, fid) for code, status, fid in db.execute(
            '''SELECT l.legacy_code,u.status,u.family_id FROM unified_catalog_reviews u JOIN legacy_products l USING(legacy_id)
               WHERE u.load_id=?''', (load_id,))} if db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='unified_catalog_reviews'").fetchone() else {}
        by_code = defaultdict(list)
        for r in rows:
            if r.get('Product ID'):
                by_code[r['Product ID']].append(r)
        # Agrupar por maestro: varios códigos pueden compartir maestro tras una equivalencia aprobada.
        by_master = defaultdict(list)
        for code in sorted(by_code, key=lambda c: (c in linked, c)):
            if code in masters:
                by_master[masters[code][0]].append(code)
        spelling = Counter()
        for code, items in by_code.items():
            if items[0].get('MANUFACTURER'):
                spelling[(R.brand_key(items[0]['MANUFACTURER']), items[0]['MANUFACTURER'])] += 1
        best_spelling = {}
        for (bk, text), n in sorted(spelling.items(), key=lambda kv: -kv[1]):
            best_spelling.setdefault(bk, text)
        cache, counters = {}, _next_codes(db)
        existing = {mid: code for mid, code in db.execute('SELECT master_id,standard_code FROM product_standards')}
        results = []
        for mid, codes in by_master.items():
            first = by_code[codes[0]][0]
            origin = masters[codes[0]][1]
            brand_k = R.brand_key(first.get('MANUFACTURER'))
            maker = _manufacturer(db, brand_k, best_spelling.get(brand_k, first.get('MANUFACTURER') or ''), source_id, cache)
            for code in codes[1:]:  # alias de otros códigos del mismo maestro
                other = by_code[code][0].get('MANUFACTURER')
                if R.brand_key(other):
                    _manufacturer(db, R.brand_key(other), other, source_id, cache)
            if maker and maker not in brand_names:
                brand_names[maker] = db.execute('SELECT canonical_name FROM manufacturers WHERE manufacturer_id=?', (maker,)).fetchone()[0]
            brand = brand_names.get(maker)
            model = R.standard_model(first.get('MODEL'))
            base = R.normalize_name(first.get('Description'))
            name = R.standard_name(first.get('Description'), brand, model)
            status = R.operational_status(first.get('Description'))
            review_status, review_family = reviews.get(codes[0], (None, None))
            if review_status == 'approved_by_reviewer':
                fid, method = review_family, 'Revisor'
            elif review_status == 'rejected':
                fid, method = None, 'Revisar: rechazada por revisor'
            elif origin == 'manual':
                fid = current_family.get(mid)
                method = 'Alta manual' if fid else 'Revisar: sin regla'
            else:
                family, method = R.classify(base, [first.get('Report Group'), first.get('EXCHANGEGROUP')],
                                            first.get('Type'), first.get('Package'))
                fid = families.get(family)
            code = existing.get(mid)  # un producto "no usar" conserva familia pero no recibe código nuevo
            if code is None and fid and status == 'Activo':
                family_name = next(n for n, i in families.items() if i == fid)
                prefix = R.code_prefix(family_name)
                counters[prefix] += 1
                code = f'{prefix}-{counters[prefix]:05d}'
            # El stock nunca se suma entre países: se guarda por país y solo en sitios disponibles.
            by_country, presence, stocked_sites = Counter(), set(), set()
            for c in codes:
                for i in by_code[c]:
                    country, kind = sites.get(i.get('SITEID'), (None, None))
                    if country:
                        presence.add(country)
                    if kind in R.AVAILABLE_SITE_TYPES and _number(i.get('Stock')) > 0:
                        by_country[country or 'Sin país'] += _number(i.get('Stock'))
                        stocked_sites.add(i['SITEID'])
            countries = sorted(by_country)
            dkey = R.duplicate_key(base, brand_k, model) if base and status == 'Activo' else None
            search = R.words(' '.join(filter(None, [name, brand, model, code, ' '.join(codes), ' '.join(retired.get(mid, [])),
                                                    first.get('Description')])))
            results.append([mid, code, name, maker, model, fid, method, status, dkey, ', '.join(codes),
                            ', '.join(countries) or None, sum(by_country.values()), len(stocked_sites), load_id, search,
                            ', '.join(sorted(presence)) or None, json.dumps(dict(sorted(by_country.items())), ensure_ascii=False)])
            if origin == 'import':
                db.execute('UPDATE master_products SET standard_name=?,manufacturer_id=?,model=?,family_id=? WHERE master_id=?',
                           (name or first.get('Description') or codes[0], maker, model, fid, mid))
                if review_status in ('pending', 'approved_by_rule'):
                    db.execute('''UPDATE unified_catalog_reviews SET family_id=?,status=?,reason=? WHERE load_id=? AND legacy_id=?
                                  AND status IN ('pending','approved_by_rule')''',
                               (fid, 'approved_by_rule' if method == 'Alta confianza' else 'pending',
                                f'{R.RULES_VERSION}: {method}', load_id, legacy_ids[codes[0]]))
        new_codes = sum(1 for r in results if r[1] and existing.get(r[0]) is None)
        db.executemany('''INSERT INTO product_standards(master_id,standard_code,standard_name,manufacturer_id,model,family_id,method,
                operational_status,duplicate_key,legacy_codes,countries,stock_available,sites_with_stock,load_id,
                search_text,presence_countries,stock_by_country,rules_version) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
              ON CONFLICT(master_id) DO UPDATE SET standard_code=COALESCE(product_standards.standard_code,excluded.standard_code),
                standard_name=excluded.standard_name,manufacturer_id=excluded.manufacturer_id,model=excluded.model,
                family_id=excluded.family_id,method=excluded.method,operational_status=excluded.operational_status,
                duplicate_key=excluded.duplicate_key,legacy_codes=excluded.legacy_codes,presence_countries=excluded.presence_countries,
                stock_by_country=excluded.stock_by_country,
                countries=excluded.countries,stock_available=excluded.stock_available,sites_with_stock=excluded.sites_with_stock,
                load_id=excluded.load_id,search_text=excluded.search_text,rules_version=excluded.rules_version,
                updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')''', [r + [R.RULES_VERSION] for r in results])
        _refresh_groups(db)
        summary = _summary(db, load_id, rows, new_codes)
        db.execute('INSERT INTO standardization_runs(load_id,rules_version,summary_json) VALUES(?,?,?)',
                   (load_id, R.RULES_VERSION, json.dumps(summary, ensure_ascii=False)))
        db.execute("INSERT INTO audit_events(entity_type,entity_id,action,after_json,actor,reason) VALUES('load',?,'standardize',?,?,?)",
                   (str(load_id), json.dumps(summary, ensure_ascii=False), actor, 'Estandarización ' + R.RULES_VERSION))
    return summary


def _refresh_groups(db):
    """Recalcula grupos de productos iguales (mismo nombre, marca y modelo), incluidas altas manuales.

    'Mismo país': dos fichas del mismo producto conviven en un país → duplicado real a resolver.
    'Otro país': cada país tiene su propio código del mismo producto → equivalente; se puede vincular
    bajo un solo código estándar, pero su inventario sigue separado por país.
    Un producto sin país conocido (p. ej. un alta manual) se trata como posible duplicado de todos.
    """
    members = defaultdict(list)
    for key_, presence in db.execute('SELECT duplicate_key,presence_countries FROM product_standards WHERE duplicate_key IS NOT NULL'):
        members[key_].append({c.strip() for c in (presence or '').split(',') if c.strip()})
    db.execute('UPDATE product_standards SET duplicate_group=NULL,duplicate_kind=NULL')
    updates = []
    for key_, sets in members.items():
        if len(sets) < 2:
            continue
        seen, same = Counter(), any(not s_ for s_ in sets)
        for s_ in sets:
            seen.update(s_)
        same = same or any(n > 1 for n in seen.values())
        updates.append((_group_id(key_), 'Mismo país' if same else 'Otro país', key_))
    db.executemany('UPDATE product_standards SET duplicate_group=?,duplicate_kind=? WHERE duplicate_key=?', updates)


def _short(method):
    return 'Revisar: conflicto' if method.startswith('Revisar: conflicto') else method


def _summary(db, load_id, rows, new_codes):
    products = db.execute('SELECT method,family_id,standard_code,operational_status,duplicate_group FROM product_standards WHERE load_id=?',
                          (load_id,)).fetchall()
    total = len(products) or 1
    sites = db.execute('''SELECT COALESCE(c.country_code,'Sin país'),s.site_type,count(*) FROM sites s LEFT JOIN countries c USING(country_id)
                          WHERE s.source_id=(SELECT source_id FROM loads WHERE load_id=?) GROUP BY 1,2''', (load_id,)).fetchall()
    raw_brands = {r.get('MANUFACTURER') for r in rows if r.get('MANUFACTURER')}
    return {
        'load_id': load_id, 'rules_version': R.RULES_VERSION, 'rows': len(rows),
        'products': len(products),
        'classified': sum(1 for p in products if p[1]),
        'classified_pct': round(100 * sum(1 for p in products if p[1]) / total, 1),
        'methods': dict(Counter(_short(p[0]) for p in products).most_common()),
        'with_code': sum(1 for p in products if p[2]), 'new_codes': new_codes,
        'operational': dict(Counter(p[3] for p in products)),
        'duplicate_groups': len({p[4] for p in products if p[4]}),
        'duplicate_groups_same_country': db.execute("SELECT count(DISTINCT duplicate_group) FROM product_standards WHERE duplicate_kind='Mismo país'").fetchone()[0],
        'duplicate_groups_cross_country': db.execute("SELECT count(DISTINCT duplicate_group) FROM product_standards WHERE duplicate_kind='Otro país'").fetchone()[0],
        'duplicate_products': sum(1 for p in products if p[4]),
        'brands_raw': len(raw_brands),
        'brands_standard': db.execute('SELECT count(DISTINCT manufacturer_id) FROM product_standards WHERE load_id=?', (load_id,)).fetchone()[0],
        'sites_by_country': _sum(sites, 0),
        'sites_by_type': _sum(sites, 1),
        'sites_without_country': sum(s[2] for s in sites if s[0] == 'Sin país'),
    }


def _sum(rows, index):
    out = Counter()
    for r in rows:
        out[r[index] or 'Sin dato'] += r[2]
    return dict(out.most_common())


def latest_summary(db):
    row = db.execute('SELECT summary_json FROM standardization_runs ORDER BY run_id DESC LIMIT 1').fetchone()
    return json.loads(row[0]) if row else None


# ---------------------------------------------------------------- revisión humana
def after_review(db, master_id, decision):
    """Refleja en product_standards la decisión de un revisor y asigna código si corresponde."""
    fid = db.execute('SELECT family_id FROM master_products WHERE master_id=?', (master_id,)).fetchone()[0]
    method = {'approve': 'Revisor', 'reject': 'Revisar: rechazada por revisor', 'pending': 'Revisar: reabierta por revisor'}[decision]
    with db:
        db.execute('UPDATE product_standards SET family_id=?,method=?,updated_at=strftime(\'%Y-%m-%dT%H:%M:%fZ\',\'now\') WHERE master_id=?',
                   (fid, method, master_id))
        _assign_code(db, master_id)


def _assign_code(db, master_id):
    row = db.execute('''SELECT p.standard_code,p.operational_status,f.name FROM product_standards p
                        LEFT JOIN families f USING(family_id) WHERE p.master_id=?''', (master_id,)).fetchone()
    if not row or row[0] or not row[2] or row[1] != 'Activo':
        return row[0] if row else None
    prefix = R.code_prefix(row[2])
    code = f'{prefix}-{_next_codes(db)[prefix] + 1:05d}'
    db.execute('UPDATE product_standards SET standard_code=?,search_text=search_text||\' \'||? WHERE master_id=?',
               (code, R.words(code), master_id))
    return code


def set_site(db, data):
    """Asignación manual de país o tipo de sitio (queda protegida frente a futuras ejecuciones)."""
    site_id = int(data['site_id'])
    before = db.execute('SELECT country_id,site_type FROM sites WHERE site_id=?', (site_id,)).fetchone()
    if not before:
        raise ValueError('Sitio inexistente')
    with db:
        if data.get('country_code'):
            country = db.execute('SELECT country_id FROM countries WHERE country_code=?', (data['country_code'],)).fetchone()
            if not country:
                raise ValueError('País inválido')
            db.execute("UPDATE sites SET country_id=?,country_source='manual' WHERE site_id=?", (country[0], site_id))
        if data.get('site_type'):
            if data['site_type'] not in R.SITE_TYPES:
                raise ValueError('Tipo de sitio inválido')
            db.execute("UPDATE sites SET site_type=?,type_source='manual' WHERE site_id=?", (data['site_type'], site_id))
        db.execute("INSERT INTO audit_events(entity_type,entity_id,action,before_json,after_json,actor,reason) VALUES('site',?,'set_site',?,?,?,?)",
                   (str(site_id), json.dumps(list(before)), json.dumps({k: data.get(k) for k in ('country_code', 'site_type')}),
                    data['actor'], data['reason']))
    return {'saved': True}


def sites(db):
    return [dict(zip(['site_id', 'code', 'name', 'country', 'country_source', 'site_type', 'type_source'], r)) for r in db.execute(
        '''SELECT s.site_id,s.source_site_code,s.name,c.country_code,s.country_source,s.site_type,s.type_source
           FROM sites s LEFT JOIN countries c USING(country_id) ORDER BY c.country_code IS NOT NULL,s.name''')]


# ---------------------------------------------------------------- búsqueda
SEARCH_SQL = '''SELECT p.master_id,p.standard_code,m.master_code,p.standard_name,b.canonical_name,p.model,c.name,f.name,p.method,
  p.operational_status,p.duplicate_group,p.legacy_codes,p.countries,p.stock_available,m.origin,m.product_type,m.package_type,
  p.duplicate_kind,p.presence_countries,p.stock_by_country
  FROM product_standards p JOIN master_products m USING(master_id)
  LEFT JOIN manufacturers b ON b.manufacturer_id=p.manufacturer_id
  LEFT JOIN families f ON f.family_id=p.family_id LEFT JOIN categories c ON c.category_id=f.category_id'''
SEARCH_FIELDS = ['master_id', 'standard_code', 'master_code', 'standard_name', 'brand', 'model', 'category', 'family', 'method',
                 'operational_status', 'duplicate_group', 'legacy_codes', 'countries', 'stock_available', 'origin', 'product_type',
                 'package_type', 'duplicate_kind', 'presence_countries', 'stock_by_country']


def _product(row):
    item = dict(zip(SEARCH_FIELDS, row))
    item['stock_by_country'] = json.loads(item['stock_by_country'] or '{}')
    item.pop('stock_available')  # total interno solo para ordenar: no se muestra una suma entre países
    return item
FILTERS = {
    'classified': 'p.family_id IS NOT NULL', 'review': "(p.method LIKE 'Revisar%' OR p.operational_status<>'Activo')",
    'duplicates': 'p.duplicate_group IS NOT NULL', 'dup_same': "p.duplicate_kind='Mismo país'",
    'dup_cross': "p.duplicate_kind='Otro país'", 'linked': "p.legacy_codes LIKE '%,%'",
    'with_stock': 'p.stock_available>0', 'manual': "m.origin='manual'",
}


def search(db, q='', family_id=None, category_id=None, country=None, status=None, limit=50, offset=0):
    where, args = [], []
    for token in R.words(q).split()[:8]:
        where.append("(' '||p.search_text) LIKE ?")
        args.append(f'% {token}%')
    if family_id:
        where.append('p.family_id=?'); args.append(int(family_id))
    if category_id:
        where.append('f.category_id=?'); args.append(int(category_id))
    if country:
        where.append("(', '||p.countries||',') LIKE ?"); args.append(f'%, {country},%')
    if status in FILTERS:
        where.append(FILTERS[status])
    clause = (' WHERE ' + ' AND '.join(where)) if where else ''
    total = db.execute('SELECT count(*) FROM product_standards p JOIN master_products m USING(master_id) '
                       'LEFT JOIN families f ON f.family_id=p.family_id' + clause, args).fetchone()[0]
    rows = db.execute(SEARCH_SQL + clause + ' ORDER BY p.standard_code IS NULL, p.stock_available DESC, p.standard_name LIMIT ? OFFSET ?',
                      args + [min(int(limit), 200), int(offset)]).fetchall()
    return {'total': total, 'rows': [_product(r) for r in rows]}


def detail(db, master_id):
    row = db.execute(SEARCH_SQL + ' WHERE p.master_id=?', (int(master_id),)).fetchone()
    if not row:
        raise ValueError('Producto inexistente')
    product = _product(row)
    codes = [c.strip() for c in (product['legacy_codes'] or '').split(',') if c.strip()]
    load = db.execute('SELECT load_id FROM product_standards WHERE master_id=?', (int(master_id),)).fetchone()[0]
    stock, originals = [], {}
    if codes and load:
        marks = ','.join('?' * len(codes))
        for payload in db.execute(f'''SELECT n.normalized_json FROM raw_records r JOIN normalized_records n USING(raw_record_id)
                WHERE r.load_id=? AND json_extract(n.normalized_json,'$."Product ID"') IN ({marks})''', [load] + codes):
            r = json.loads(payload[0])
            originals.setdefault(r['Product ID'], {k: r.get(k) for k in ('Description', 'MANUFACTURER', 'MODEL', 'Type', 'Package',
                                                                         'Report Group', 'EXCHANGEGROUP', 'REVENUEGROUP')})
            if r.get('SITEID'):
                site = db.execute('''SELECT s.name,c.country_code,s.site_type FROM sites s LEFT JOIN countries c USING(country_id)
                                     WHERE s.source_site_code=?''', (r['SITEID'],)).fetchone()
                stock.append({'code': r['Product ID'], 'site': site[0] if site else r['SITEID'], 'country': site[1] if site else None,
                              'site_type': site[2] if site else None, 'stock': _number(r.get('Stock'))})
    manual_stock = [dict(zip(['site', 'stock'], r)) for r in db.execute(
        'SELECT s.name,e.stock FROM manual_site_entries e JOIN sites s USING(site_id) WHERE e.master_id=?', (int(master_id),))]
    group = product['duplicate_group']
    similar = search_group(db, group, int(master_id)) if group else []
    history = [dict(zip(['at', 'action', 'actor', 'reason'], r)) for r in db.execute(
        '''SELECT occurred_at,action,actor,reason FROM audit_events WHERE entity_type='master_product' AND entity_id=?
           ORDER BY event_id DESC LIMIT 10''', (str(master_id),))]
    links = [dict(zip(['link_id', 'retired_code', 'codes', 'actor', 'reason', 'at'], (r[0], r[1], json.loads(r[2]), *r[3:]))) for r in db.execute(
        '''SELECT link_id,retired_code,legacy_codes_json,actor,reason,linked_at FROM standard_code_links
           WHERE target_master_id=? AND undone_at IS NULL ORDER BY link_id''', (int(master_id),))]
    return {'product': product, 'originals': originals, 'stock': sorted(stock, key=lambda s: -s['stock']),
            'manual_stock': manual_stock, 'duplicates': similar, 'history': history, 'links': links}


# ---------------------------------------------------------------- vincular equivalentes
def link(db, data):
    """Vincula el producto `source_id` al producto `target_id`: pasan a compartir código estándar.

    Los códigos de origen del producto vinculado quedan como equivalencias del destino; el inventario no se
    toca (sigue por código × sitio, con su país) y el código estándar retirado sigue encontrándose al buscar.
    Es reversible con unlink(). Requiere responsable y motivo.
    """
    from catalogo.operations import credentials
    actor, reason = credentials(data)
    target, source = int(data['target_id']), int(data['source_id'])
    if target == source:
        raise ValueError('Elija dos productos distintos')
    rows = {r[0]: r[1:] for r in db.execute('''SELECT m.master_id,m.origin,m.status,p.standard_code FROM master_products m
                                               JOIN product_standards p USING(master_id) WHERE m.master_id IN (?,?)''', (target, source))}
    if len(rows) != 2:
        raise ValueError('Producto inexistente')
    if rows[source][0] == 'manual':
        raise ValueError('Un alta manual solo puede ser el destino: abra el producto importado y vincule el alta manual a él')
    if 'inactive' in (rows[target][1], rows[source][1]):
        raise ValueError('Uno de los productos ya fue vinculado a otro')
    codes = [c for (c,) in db.execute('''SELECT l.legacy_code FROM product_mappings p JOIN legacy_products l USING(legacy_id)
                                          WHERE p.master_id=?''', (source,))]
    with db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('''UPDATE product_mappings SET master_id=?,method='reviewed',reason=?,decided_by=?,
                      decided_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE master_id=?''', (target, reason, actor, source))
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='unified_catalog_reviews'").fetchone():
            db.execute('UPDATE unified_catalog_reviews SET master_id=? WHERE master_id=?', (target, source))
        db.execute("UPDATE master_products SET status='inactive' WHERE master_id=?", (source,))
        db.execute('DELETE FROM product_standards WHERE master_id=?', (source,))
        link_id = db.execute('''INSERT INTO standard_code_links(source_master_id,target_master_id,retired_code,legacy_codes_json,actor,reason)
                                VALUES(?,?,?,?,?,?)''', (source, target, rows[source][2], json.dumps(codes), actor, reason)).lastrowid
        db.execute("INSERT INTO audit_events(entity_type,entity_id,action,before_json,after_json,actor,reason) VALUES('master_product',?,'link_equivalent',?,?,?,?)",
                   (str(target), json.dumps({'source_master_id': source, 'retired_code': rows[source][2]}),
                    json.dumps({'legacy_codes': codes, 'link_id': link_id}), actor, reason))
    return {'linked': True, 'link_id': link_id, 'codes': codes, 'retired_code': rows[source][2]}


def unlink(db, data):
    """Deshace una vinculación: el producto recupera sus códigos de origen y su código estándar original."""
    from catalogo.operations import credentials
    actor, reason = credentials(data)
    row = db.execute('''SELECT source_master_id,target_master_id,retired_code,legacy_codes_json FROM standard_code_links
                        WHERE link_id=? AND undone_at IS NULL''', (int(data['link_id']),)).fetchone()
    if not row:
        raise ValueError('Vinculación inexistente o ya deshecha')
    source, target, code, codes = row[0], row[1], row[2], json.loads(row[3])
    with db:
        db.execute('BEGIN IMMEDIATE')
        marks = ','.join('?' * len(codes))
        legacy = [lid for (lid,) in db.execute(f'''SELECT l.legacy_id FROM legacy_products l JOIN product_mappings p USING(legacy_id)
                                                  WHERE p.master_id=? AND l.legacy_code IN ({marks})''', [target] + codes)]
        lmarks = ','.join('?' * len(legacy)) or 'NULL'
        db.execute(f'''UPDATE product_mappings SET master_id=?,method='initial',reason=?,decided_by=?,
                       decided_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE legacy_id IN ({lmarks})''', [source, reason, actor] + legacy)
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='unified_catalog_reviews'").fetchone():
            db.execute(f'UPDATE unified_catalog_reviews SET master_id=? WHERE legacy_id IN ({lmarks})', [source] + legacy)
        db.execute("UPDATE master_products SET status='active' WHERE master_id=?", (source,))
        # El código estándar original se restaura; la próxima estandarización completa el resto de los datos.
        db.execute('''INSERT OR REPLACE INTO product_standards(master_id,standard_code,method,operational_status,search_text,rules_version)
                      VALUES(?,?,'Revisar: vínculo deshecho','Activo',?,?)''', (source, code, R.words(' '.join([code or ''] + codes)), R.RULES_VERSION))
        db.execute("UPDATE standard_code_links SET undone_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE link_id=?", (int(data['link_id']),))
        db.execute("INSERT INTO audit_events(entity_type,entity_id,action,after_json,actor,reason) VALUES('master_product',?,'unlink_equivalent',?,?,?)",
                   (str(target), json.dumps({'source_master_id': source, 'restored_code': code, 'legacy_codes': codes}), actor, reason))
    return {'unlinked': True, 'restored_code': code, 'codes': codes}


def search_group(db, group, exclude=None):
    rows = db.execute(SEARCH_SQL + ' WHERE p.duplicate_group=? AND p.master_id<>?', (group, exclude or -1)).fetchall()
    return [_product(r) for r in rows]


# ---------------------------------------------------------------- productos nuevos
def propose(db, data):
    """Vista previa de un alta: nombre estándar, marca canónica, familia sugerida, similares y duplicados exactos."""
    raw_name = (data.get('name') or '').strip()
    if not raw_name:
        raise ValueError('Escriba el nombre del producto')
    bk = R.brand_key(data.get('brand'))
    row = db.execute('SELECT canonical_name FROM manufacturers WHERE canonical_key=?', (bk,)).fetchone() if bk else None
    brand = row[0] if row else (next((v for k, v in R.BRAND_ALIASES.items() if R.key(v) == bk), None) or
                                (data.get('brand') or '').strip().upper() or None) if bk else None
    model = R.standard_model(data.get('model'))
    base = R.normalize_name(raw_name)
    if base is None:
        raise ValueError('El nombre no tiene texto útil')
    family, method = R.classify(base, (), data.get('product_type'), data.get('package_type'))
    families = _families(db)
    dkey = R.duplicate_key(base, bk, model)
    exact = [_product(r) for r in db.execute(SEARCH_SQL + ' WHERE p.duplicate_key=?', (dkey,))]
    similar = search(db, ' '.join(R.words(base).split()[:3]), limit=8)['rows']
    return {'standard_name': R.standard_name(raw_name, brand, model), 'brand': brand, 'model': model,
            'family': family, 'family_id': families.get(family), 'method': method,
            'status': R.operational_status(raw_name), 'exact_duplicates': exact,
            'similar': [s for s in similar if s['master_id'] not in {e['master_id'] for e in exact}]}


def create(db, data):
    """Alta manual estandarizada: busca duplicados, crea el maestro auditado y le asigna código estándar."""
    from catalogo import operations as op
    proposal = propose(db, data)
    if proposal['exact_duplicates'] and not data.get('confirm_duplicate'):
        codes = ', '.join(d['standard_code'] or d['master_code'] for d in proposal['exact_duplicates'][:3])
        raise ValueError(f'Ya existe un producto con el mismo nombre, marca y modelo ({codes}). '
                         'Úselo o confirme que es distinto.')
    if data.get('product_type') not in ('ITEM', 'LABOR', 'PARTS', 'MISCCHARGE'):
        raise ValueError('Tipo de producto inválido')
    family_id = int(data['family_id']) if data.get('family_id') else proposal['family_id']
    payload = {k: v for k, v in data.items() if k not in ('brand', 'confirm_duplicate')}
    payload.update(name=proposal['standard_name'], model=proposal['model'] or '', family_id=family_id)
    result = op.manual(db, payload)
    mid = result['master_id']
    with db:
        maker = _manufacturer(db, R.brand_key(data.get('brand')), proposal['brand'] or '', None, {}) if proposal['brand'] else None
        db.execute('UPDATE master_products SET manufacturer_id=? WHERE master_id=?', (maker, mid))
        method = 'Alta manual' if family_id else 'Revisar: sin regla'
        base = R.normalize_name(data['name'])
        search_text = R.words(' '.join(filter(None, [proposal['standard_name'], proposal['brand'], proposal['model']])))
        country, stock = None, {}
        if data.get('site_id'):
            site = db.execute('''SELECT c.country_code,s.site_type FROM sites s LEFT JOIN countries c USING(country_id)
                                 WHERE s.site_id=?''', (int(data['site_id']),)).fetchone()
            country = site[0] if site else None
            if site and data.get('stock') and site[1] in R.AVAILABLE_SITE_TYPES and _number(data['stock']) > 0:
                stock = {country or 'Sin país': _number(data['stock'])}
        db.execute('''INSERT OR IGNORE INTO product_standards(master_id,standard_name,manufacturer_id,model,family_id,method,
                      operational_status,duplicate_key,legacy_codes,countries,stock_available,search_text,presence_countries,
                      stock_by_country,rules_version) VALUES(?,?,?,?,?,?,?,?,NULL,?,?,?,?,?,?)''',
                   (mid, proposal['standard_name'], maker, proposal['model'], family_id, method, proposal['status'],
                    R.duplicate_key(base, R.brand_key(data.get('brand')), proposal['model']), ', '.join(stock) or None,
                    sum(stock.values()), search_text, country, json.dumps(stock, ensure_ascii=False), R.RULES_VERSION))
        code = _assign_code(db, mid)
        _refresh_groups(db)
    code = db.execute('SELECT standard_code FROM product_standards WHERE master_id=?', (mid,)).fetchone()[0]
    return dict(result, standard_code=code, standard_name=proposal['standard_name'])
