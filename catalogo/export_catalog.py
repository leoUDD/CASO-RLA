"""Exporta el catálogo estandarizado a una base SQLite independiente, lista para BI, R2 u otras herramientas.

Uso: python -m catalogo.export_catalog [--db data/rla_modelo_v4.sqlite3] [--out data/exports/catalogo.sqlite3]
La base operativa conserva historial, auditoría y staging; esta exportación es una fotografía limpia y relacional.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from catalogo import std_rules as R

SCHEMA = '''
PRAGMA foreign_keys=ON;
CREATE TABLE metadatos(clave TEXT PRIMARY KEY, valor TEXT);
CREATE TABLE categorias(categoria_id INTEGER PRIMARY KEY, nombre TEXT NOT NULL UNIQUE, codigo TEXT);
CREATE TABLE familias(familia_id INTEGER PRIMARY KEY, categoria_id INTEGER NOT NULL REFERENCES categorias,
  nombre TEXT NOT NULL, prefijo_codigo TEXT, UNIQUE(categoria_id,nombre));
CREATE TABLE marcas(marca_id INTEGER PRIMARY KEY, nombre TEXT NOT NULL, clave TEXT NOT NULL UNIQUE);
CREATE TABLE marca_alias(marca_id INTEGER NOT NULL REFERENCES marcas, escritura_original TEXT NOT NULL, fuente TEXT,
  PRIMARY KEY(marca_id,escritura_original));
CREATE TABLE paises(codigo TEXT PRIMARY KEY, nombre TEXT NOT NULL);
CREATE TABLE sitios(sitio_id INTEGER PRIMARY KEY, fuente TEXT NOT NULL, codigo_sitio TEXT NOT NULL, nombre TEXT NOT NULL,
  pais TEXT REFERENCES paises, origen_pais TEXT, tipo_sitio TEXT, disponible INTEGER NOT NULL CHECK(disponible IN (0,1)),
  UNIQUE(fuente,codigo_sitio));
CREATE TABLE productos(producto_id INTEGER PRIMARY KEY, codigo_estandar TEXT UNIQUE, codigo_maestro TEXT NOT NULL UNIQUE,
  nombre_estandar TEXT, marca_id INTEGER REFERENCES marcas, modelo TEXT, familia_id INTEGER REFERENCES familias,
  tipo TEXT, paquete TEXT, serializacion TEXT, origen TEXT NOT NULL, estado_operativo TEXT NOT NULL,
  metodo_clasificacion TEXT NOT NULL, grupo_duplicado TEXT, tipo_duplicado TEXT, paises_presencia TEXT, stock_por_pais TEXT);
CREATE TABLE stock_disponible_por_pais(producto_id INTEGER NOT NULL REFERENCES productos, pais TEXT NOT NULL, stock REAL NOT NULL,
  PRIMARY KEY(producto_id,pais));
CREATE TABLE codigos_estandar_retirados(codigo_retirado TEXT PRIMARY KEY, producto_id INTEGER NOT NULL REFERENCES productos,
  codigos_origen TEXT NOT NULL, vinculado_por TEXT NOT NULL, motivo TEXT NOT NULL, vinculado_en TEXT NOT NULL);
CREATE TABLE codigos_origen(fuente TEXT NOT NULL, codigo_origen TEXT NOT NULL, producto_id INTEGER NOT NULL REFERENCES productos,
  descripcion_original TEXT, PRIMARY KEY(fuente,codigo_origen));
CREATE TABLE inventario(producto_id INTEGER NOT NULL REFERENCES productos, sitio_id INTEGER NOT NULL REFERENCES sitios,
  codigo_origen TEXT NOT NULL, stock REAL, costo REAL, costo_reposicion REAL, carga_id INTEGER NOT NULL,
  PRIMARY KEY(codigo_origen,sitio_id,carga_id));
CREATE INDEX productos_familia ON productos(familia_id);
CREATE INDEX inventario_sitio ON inventario(sitio_id);
CREATE VIEW v_catalogo AS
  SELECT p.codigo_estandar,p.codigo_maestro,p.nombre_estandar,m.nombre AS marca,p.modelo,c.nombre AS categoria,
         f.nombre AS familia,p.tipo,p.paquete,p.estado_operativo,p.metodo_clasificacion,p.grupo_duplicado,p.tipo_duplicado,
         p.paises_presencia,p.stock_por_pais,
         (SELECT group_concat(codigo_origen,', ') FROM codigos_origen o WHERE o.producto_id=p.producto_id) AS codigos_origen
  FROM productos p LEFT JOIN marcas m USING(marca_id) LEFT JOIN familias f USING(familia_id) LEFT JOIN categorias c USING(categoria_id);
CREATE VIEW v_stock_por_pais AS
  SELECT p.codigo_estandar,p.nombre_estandar,s.pais,s.tipo_sitio,sum(i.stock) AS stock
  FROM inventario i JOIN productos p USING(producto_id) JOIN sitios s USING(sitio_id) GROUP BY 1,2,3,4;
'''


def export(db, out_path):
    """Escribe una base SQLite nueva en out_path (se reemplaza si existe). Devuelve un resumen."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix('.tmp')
    tmp.unlink(missing_ok=True)
    load = db.execute('SELECT max(load_id) FROM product_standards').fetchone()[0]
    load_info = db.execute('SELECT l.filename,l.sha256,l.received_at,s.name FROM loads l JOIN sources s USING(source_id) WHERE load_id=?',
                           (load,)).fetchone() if load else None
    with closing(sqlite3.connect(tmp)) as out:
        out.executescript(SCHEMA)
        with out:
            meta = {'exportado_en': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'version_reglas': R.RULES_VERSION,
                    'carga_id': load, 'archivo': load_info[0] if load_info else None,
                    'sha256_archivo': load_info[1] if load_info else None, 'fuente': load_info[3] if load_info else None,
                    'inventario': 'Stock observado en la última carga estandarizada; no reemplaza la publicación formal.'}
            out.executemany('INSERT INTO metadatos VALUES(?,?)', [(k, None if v is None else str(v)) for k, v in meta.items()])
            prefixes = {f: R.code_prefix(f) for f in R.TAXONOMY}
            out.executemany('INSERT INTO categorias VALUES(?,?,?)', db.execute('SELECT category_id,name,category_code FROM categories').fetchall())
            out.executemany('INSERT INTO familias VALUES(?,?,?,?)',
                            [(fid, cid, name, prefixes.get(name)) for fid, cid, name in db.execute('SELECT family_id,category_id,name FROM families')])
            out.executemany('INSERT INTO marcas VALUES(?,?,?)', db.execute('SELECT manufacturer_id,canonical_name,canonical_key FROM manufacturers').fetchall())
            out.executemany('INSERT OR IGNORE INTO marca_alias VALUES(?,?,?)', db.execute(
                'SELECT a.manufacturer_id,a.original_example,s.name FROM manufacturer_aliases a JOIN sources s USING(source_id) WHERE a.original_example IS NOT NULL').fetchall())
            out.executemany('INSERT INTO paises VALUES(?,?)', db.execute('SELECT country_code,name FROM countries').fetchall())
            out.executemany('INSERT INTO sitios VALUES(?,?,?,?,?,?,?,?)', [
                (sid, src, code, name, country, csrc, kind, int(kind in R.AVAILABLE_SITE_TYPES)) for sid, src, code, name, country, csrc, kind in db.execute(
                    '''SELECT s.site_id,f.name,s.source_site_code,s.name,c.country_code,s.country_source,s.site_type
                       FROM sites s JOIN sources f USING(source_id) LEFT JOIN countries c USING(country_id)''')])
            products = db.execute(
                '''SELECT p.master_id,p.standard_code,m.master_code,p.standard_name,p.manufacturer_id,p.model,p.family_id,
                          m.product_type,m.package_type,m.serialization,m.origin,p.operational_status,p.method,p.duplicate_group,
                          p.duplicate_kind,p.presence_countries,p.stock_by_country
                   FROM product_standards p JOIN master_products m USING(master_id)''').fetchall()
            stock_rows = []
            for row in products:
                by_country = json.loads(row[16] or '{}')
                stock_rows.extend((row[0], country, qty) for country, qty in by_country.items())
            out.executemany('INSERT INTO productos VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', [
                tuple(row)[:16] + (' · '.join(f'{c}: {q:g}' for c, q in json.loads(row[16] or '{}').items()) or None,) for row in products])
            out.executemany('INSERT INTO stock_disponible_por_pais VALUES(?,?,?)', stock_rows)
            out.executemany('INSERT INTO codigos_estandar_retirados VALUES(?,?,?,?,?,?)', [
                (code, target, ', '.join(json.loads(codes)), actor, reason, at) for code, target, codes, actor, reason, at in db.execute(
                    '''SELECT retired_code,target_master_id,legacy_codes_json,actor,reason,linked_at FROM standard_code_links
                       WHERE undone_at IS NULL AND retired_code IS NOT NULL''')])
            originals = {}
            if load:
                for payload in db.execute('''SELECT n.normalized_json FROM raw_records r JOIN normalized_records n USING(raw_record_id)
                                             WHERE r.load_id=?''', (load,)):
                    r = json.loads(payload[0])
                    originals.setdefault(r.get('Product ID'), r)
            out.executemany('INSERT INTO codigos_origen VALUES(?,?,?,?)', [
                (src, code, mid, (originals.get(code) or {}).get('Description')) for src, code, mid in db.execute(
                    '''SELECT s.name,l.legacy_code,p.master_id FROM legacy_products l JOIN sources s USING(source_id)
                       JOIN product_mappings p USING(legacy_id) JOIN product_standards USING(master_id)''')])
            if load:
                source = db.execute('SELECT source_id FROM loads WHERE load_id=?', (load,)).fetchone()[0]
                site_ids = {code: sid for sid, code in db.execute('SELECT site_id,source_site_code FROM sites WHERE source_id=?', (source,))}
                masters = {code: mid for code, mid in db.execute(
                    '''SELECT l.legacy_code,p.master_id FROM legacy_products l JOIN product_mappings p USING(legacy_id)
                       WHERE l.source_id=?''', (source,))}
                rows = []
                for payload in db.execute('''SELECT n.normalized_json FROM raw_records r JOIN normalized_records n USING(raw_record_id)
                                             WHERE r.load_id=? AND r.validation_status='accepted' ''', (load,)):
                    r = json.loads(payload[0])
                    code, site = r.get('Product ID'), r.get('SITEID')
                    if code in masters and site in site_ids:
                        rows.append((masters[code], site_ids[site], code, _num(r.get('Stock')), _num(r.get('Cost')),
                                     _num(r.get('Replacement Cost')), load))
                out.executemany('INSERT INTO inventario VALUES(?,?,?,?,?,?,?)', rows)
        counts = {t: out.execute(f'SELECT count(*) FROM {t}').fetchone()[0]
                  for t in ('productos', 'codigos_origen', 'marcas', 'familias', 'sitios', 'inventario')}
        assert out.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not out.execute('PRAGMA foreign_key_check').fetchall()
    tmp.replace(out_path)
    return {'path': str(out_path), 'tables': counts, 'load_id': load}


def info(path):
    """Metadatos y conteos de una exportación existente, o None si todavía no hay."""
    path = Path(path)
    if not path.is_file():
        return None
    with closing(sqlite3.connect(f'file:{path}?mode=ro', uri=True)) as out:
        meta = dict(out.execute('SELECT clave,valor FROM metadatos'))
        tables = {t: out.execute(f'SELECT count(*) FROM {t}').fetchone()[0]
                  for t in ('productos', 'codigos_origen', 'marcas', 'familias', 'sitios', 'inventario')}
    return {'path': str(path), 'size_kb': path.stat().st_size // 1024, 'exported_at': meta.get('exportado_en'),
            'load_id': meta.get('carga_id'), 'file': meta.get('archivo'), 'tables': tables}


def _num(value):
    try:
        return float(value) if value not in (None, '') else None
    except ValueError:
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default='data/rla_modelo_v4.sqlite3')
    parser.add_argument('--out', default='data/exports/catalogo_estandarizado.sqlite3')
    args = parser.parse_args()
    with closing(sqlite3.connect(args.db)) as db:
        print(json.dumps(export(db, args.out), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
