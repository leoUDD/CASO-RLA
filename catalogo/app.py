"""Aplicación local: python -m catalogo. Solo escucha en 127.0.0.1.

Flujo: cargar Excel (manual) → tratamiento → estandarización → exportación a SQLite (automáticos) →
buscar y crear productos (manual). Revisión de clasificaciones, sitios y publicación son opcionales.
Todo queda en la base operativa con auditoría; la exportación se regenera tras cada cambio.
"""
import argparse
import base64
from collections import Counter
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import tempfile
import threading
from urllib.parse import urlparse, parse_qs

from catalogo import operations as op
from catalogo.build_catalog import build
from catalogo import standardize as std
from catalogo import std_rules as R
from catalogo.export_catalog import export, info as export_info
from catalogo.import_excel import import_excel, connect as create_database

LOCK = threading.Lock()  # una escritura a la vez; SQLite además serializa con BEGIN IMMEDIATE
EXPORT_NAME = 'catalogo_estandarizado.sqlite3'
DEFAULT_ACTOR = 'Usuario RLA'


def export_path(dbpath):
    return Path(dbpath).parent / 'exports' / EXPORT_NAME


def refresh_export(db, dbpath):
    """Paso automático: deja la base SQLite exportada al día con el catálogo operativo."""
    if not db.execute('SELECT 1 FROM product_standards LIMIT 1').fetchone():
        return None
    return export(db, export_path(dbpath))


def who(data, reason):
    """Responsable y motivo: opcionales en los pasos del flujo (se registran valores por defecto)."""
    return dict(data, actor=op.clean(data.get('actor')) or DEFAULT_ACTOR, reason=op.clean(data.get('reason')) or reason)


def latest_load(db):
    row = db.execute('SELECT max(load_id) FROM loads').fetchone()
    return row[0] if row else None


def state(db, load_id, dbpath):
    loads = [dict(r) for r in db.execute('SELECT l.*,s.name source FROM loads l JOIN sources s USING(source_id) ORDER BY load_id DESC')]
    base = {'loads': loads, 'load_id': load_id, 'std': std.latest_summary(db), 'sites': std.sites(db),
            'export': export_info(export_path(dbpath)),
            'countries': [dict(r) for r in db.execute('SELECT country_code,name FROM countries ORDER BY name')],
            'site_types': R.SITE_TYPES,
            'categories': [dict(r) for r in db.execute('SELECT category_id,name FROM categories ORDER BY name')],
            'families': [dict(r) for r in db.execute('SELECT f.*,c.name category FROM families f JOIN categories c USING(category_id) ORDER BY c.name,f.name')],
            'manual_products': [dict(r) for r in db.execute(
                '''SELECT m.master_code,p.standard_code,m.standard_name FROM master_products m LEFT JOIN product_standards p USING(master_id)
                   WHERE m.origin='manual' ORDER BY m.master_id DESC LIMIT 20''')]}
    if not load_id:
        return dict(base, rows=[], sample_ids=[], counts={}, groups={}, technical=[], preview=None, issues=[])
    rows = op.review_rows(db, load_id)
    for row in rows:
        row['group'] = op.pending_group(row)
    return dict(base, rows=rows,
                sample_ids=[r[0] for r in db.execute('SELECT legacy_id FROM quality_samples WHERE load_id=?', (load_id,))],
                counts=dict(Counter(r['status'] for r in rows)),
                groups=dict(Counter(r['group'] for r in rows if r['status'] == 'pending')),
                technical=op.technical_rows(db, load_id), preview=op.preview(db, load_id),
                issues=[dict(r) for r in db.execute(
                    '''SELECT severity,field,code,count(*) n FROM validation_issues WHERE load_id=?
                       GROUP BY severity,field,code ORDER BY severity,n DESC''', (load_id,))])


def run_pipeline(db, dbpath, path, source, actor, reason):
    """Excel → tratamiento → taxonomía y maestros → estandarización → exportación SQLite. Nunca publica solo."""
    result = import_excel(path, dbpath, source)
    load_id = result['load_id']
    std.ensure_taxonomy(db, load_id)
    db.row_factory = None
    build(db, load_id)  # también recupera una preparación interrumpida
    db.row_factory = op.sqlite3.Row
    op.ensure_sample(db, load_id)
    summary = std.apply(db, load_id, actor)
    if not result['repeated']:
        with db:
            op.audit(db, 'load', load_id, 'upload_full_file', None, {'source': source, 'filename': path.name}, actor, reason)
    return {'import': result, 'standardization': summary, 'export': refresh_export(db, dbpath)}


def handler(dbpath, token, port):
    backups = Path(dbpath).parent / 'backups'
    with closing(op.connect(dbpath)) as db:
        std.setup(db)

    class Handler(BaseHTTPRequestHandler):
        def send(self, code, body, mime='application/json', filename=None):
            data = body if isinstance(body, bytes) else (
                json.dumps(body, ensure_ascii=False).encode() if mime == 'application/json' else body.encode())
            self.send_response(code)
            self.send_header('Content-Type', mime + ('; charset=utf-8' if mime.startswith(('text', 'application/json')) else ''))
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            if filename:
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers(); self.wfile.write(data)

        def local(self):
            return self.headers.get('Host') == f'127.0.0.1:{port}'

        def do_GET(self):
            if not self.local(): return self.send(403, {'error': 'Host no autorizado'})
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                if url.path == '/':
                    return self.send(200, Path(__file__).with_name('app.html').read_text(encoding='utf-8').replace('__TOKEN__', token), 'text/html')
                with closing(op.connect(dbpath)) as db:
                    if url.path == '/api/state':
                        return self.send(200, state(db, int(q['load']) if q.get('load') else latest_load(db), dbpath))
                    if url.path == '/api/search':
                        return self.send(200, std.search(db, q.get('q', ''), q.get('family'), q.get('category'), q.get('country'),
                                                         q.get('status'), q.get('limit', 50), q.get('offset', 0)))
                    if url.path == '/api/product':
                        return self.send(200, std.detail(db, int(q['id'])))
                    if url.path == '/api/download':  # descarga de la base SQLite exportada
                        target = export_path(dbpath)
                        if not target.is_file(): raise ValueError('Todavía no hay exportación: cargue un archivo')
                        return self.send(200, target.read_bytes(), 'application/octet-stream', target.name)
                return self.send(404, {'error': 'Ruta inexistente'})
            except (ValueError, KeyError) as exc: self.send(400, {'error': str(exc)})
            except Exception as exc:
                self.log_error('%s', exc); self.send(500, {'error': 'Error interno; consulte el registro del servidor'})

        def do_POST(self):
            if not self.local() or self.headers.get('X-Catalog-Token') != token or self.headers.get('Origin') not in {None, f'http://127.0.0.1:{port}'}:
                return self.send(403, {'error': 'Solicitud no autorizada'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if length <= 0 or length > 100 * 1024 * 1024: raise ValueError('Solicitud vacía o mayor a 100 MB')
                data = json.loads(self.rfile.read(length))
                if self.path == '/api/propose':  # solo lectura
                    with closing(op.connect(dbpath)) as db:
                        return self.send(200, std.propose(db, data))
                with LOCK, closing(op.connect(dbpath)) as db:
                    if self.path == '/api/import':  # paso manual; todo lo que sigue es automático
                        data = who(data, 'Carga de archivo de productos')
                        source = op.clean(data.get('source')) or 'RLA_Productos'
                        filename = Path(data['filename']).name
                        if Path(filename).suffix.lower() != '.xlsx': raise ValueError('Seleccione un archivo XLSX')
                        content = base64.b64decode(data['content'], validate=True)
                        op.backup(db, backups)
                        with tempfile.TemporaryDirectory() as folder:
                            path = Path(folder) / filename; path.write_bytes(content)
                            result = run_pipeline(db, dbpath, path, source, data['actor'], data['reason'])
                    elif self.path == '/api/manual':  # alta manual → se re-exporta sola
                        result = std.create(db, who(data, 'Alta de producto nuevo'))
                        result['export'] = refresh_export(db, dbpath)
                    elif self.path == '/api/standardize':
                        data = who(data, 'Re-ejecución de la estandarización')
                        load_id = int(data.get('load_id') or latest_load(db) or 0)
                        if not load_id: raise ValueError('Primero cargue un archivo')
                        op.backup(db, backups)
                        result = dict(std.apply(db, load_id, data['actor']), export=refresh_export(db, dbpath))
                    elif self.path == '/api/sites':
                        data = who(data, 'Sitio confirmado por responsable')
                        changes = data.get('changes') or []
                        if not changes: raise ValueError('No hay cambios de sitios')
                        for change in changes:
                            std.set_site(db, dict(change, actor=data['actor'], reason=data['reason']))
                        load_id = latest_load(db)
                        result = {'saved': len(changes), 'standardization': std.apply(db, load_id, data['actor']) if load_id else None,
                                  'export': refresh_export(db, dbpath)}
                    elif self.path in ('/api/link', '/api/unlink'):  # equivalentes: requiere responsable y motivo
                        result = (std.link if self.path == '/api/link' else std.unlink)(db, data)
                        load_id = latest_load(db)
                        if load_id:
                            std.apply(db, load_id, data['actor'])
                        result['export'] = refresh_export(db, dbpath)
                    elif self.path == '/api/review':  # opcional: requiere responsable y motivo explícitos
                        result = op.save_review(db, data)
                        mid = db.execute('SELECT master_id FROM unified_catalog_reviews WHERE load_id=? AND legacy_id=?',
                                         (int(data['load_id']), int(data['legacy_id']))).fetchone()[0]
                        std.after_review(db, mid, data['decision'])
                        result['export'] = refresh_export(db, dbpath)
                    else:
                        actions = {'/api/technical': op.save_technical, '/api/publish': op.publish}
                        action = actions.get(self.path)
                        if not action: return self.send(404, {'error': 'Ruta inexistente'})
                        if self.path == '/api/publish': op.backup(db, backups)
                        result = action(db, data)
                self.send(200, result)
            except (ValueError, KeyError, TypeError, op.sqlite3.IntegrityError) as exc: self.send(400, {'error': str(exc)})
            except Exception as exc:
                self.log_error('%s', exc); self.send(500, {'error': 'Error interno; operación interrumpida. Consulte el registro del servidor'})
    return Handler


def prepare(dbpath):
    """Crea la base si no existe y aplica las tablas operativas y de estandarización."""
    dbpath = Path(dbpath)
    if not dbpath.is_file():
        dbpath.parent.mkdir(parents=True, exist_ok=True)
        create_database(dbpath).close()
        print(f'Base nueva creada en {dbpath}. Cargue un Excel desde la pestaña "1. Cargar".', flush=True)
    with closing(op.connect(dbpath)) as db:
        saved = op.backup(db, dbpath.parent / 'backups'); op.setup(db); std.setup(db)
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='unified_catalog_reviews'").fetchone():
            for (load_id,) in db.execute('SELECT DISTINCT load_id FROM unified_catalog_reviews').fetchall(): op.ensure_sample(db, load_id)
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise ValueError('Integridad inválida')
        load_id = latest_load(db)
        # Base que nunca se estandarizó, o estandarizada con una versión sin stock por país: se recalcula al iniciar.
        outdated = db.execute('SELECT 1 FROM product_standards WHERE stock_by_country IS NULL AND legacy_codes IS NOT NULL LIMIT 1').fetchone()
        if load_id and (not std.latest_summary(db) or outdated):
            print(f'Estandarizando la carga {load_id}…', flush=True)
            std.apply(db, load_id, 'inicio de la aplicación')
            refresh_export(db, dbpath)
        elif load_id and not export_path(dbpath).is_file():
            refresh_export(db, dbpath)
    return saved


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--db', default=str(op.DEFAULT_DB)); parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    saved = prepare(args.db)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler(args.db, secrets.token_urlsafe(32), args.port))
    print(f'Catálogo: http://127.0.0.1:{args.port}/ | respaldo {saved}', flush=True)
    server.serve_forever()


if __name__ == '__main__': main()
