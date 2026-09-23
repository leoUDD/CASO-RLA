"""Aplicación local: python -m db.catalog_app. Solo escucha en 127.0.0.1."""
import argparse
import base64
from contextlib import closing
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import secrets
import tempfile
from urllib.parse import urlparse, parse_qs

from db import operations as op
from db.import_excel import import_excel


def state(db, load_id):
    rows = op.review_rows(db,load_id)
    for row in rows: row['group'] = op.pending_group(row)
    return {'rows':rows, 'sample_ids':[r[0] for r in db.execute('SELECT legacy_id FROM quality_samples WHERE load_id=?',(load_id,))],
      'counts':dict(op.Counter(r['status'] for r in rows)),
      'groups':dict(op.Counter(r['group'] for r in rows if r['status']=='pending')),
      'families':[dict(r) for r in db.execute('SELECT f.*,c.name category FROM families f JOIN categories c USING(category_id) ORDER BY c.name,f.name')],
      'sites':[dict(r) for r in db.execute('SELECT * FROM sites ORDER BY name')],
      'loads':[dict(r) for r in db.execute('SELECT l.*,s.name source FROM loads l JOIN sources s USING(source_id) ORDER BY load_id DESC')],
      'technical':op.technical_rows(db,load_id), 'preview':op.preview(db,load_id),
      'manual_products':[dict(r) for r in db.execute("SELECT master_code,standard_name FROM master_products WHERE origin='manual' ORDER BY master_id DESC LIMIT 20")]}


def handler(dbpath, token, port):
    class Handler(BaseHTTPRequestHandler):
        def send(self, code, body, mime='application/json'):
            data = json.dumps(body,ensure_ascii=False).encode() if mime=='application/json' else body.encode()
            self.send_response(code)
            self.send_header('Content-Type',mime+'; charset=utf-8')
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers(); self.wfile.write(data)

        def local(self):
            return self.headers.get('Host') == f'127.0.0.1:{port}'

        def do_GET(self):
            if not self.local(): return self.send(403,{'error':'Host no autorizado'})
            url = urlparse(self.path)
            try:
                if url.path=='/':
                    return self.send(200,Path(__file__).with_name('catalog_app.html').read_text(encoding='utf-8').replace('__TOKEN__',token),'text/html')
                if url.path=='/api/state':
                    with closing(op.connect(dbpath)) as db:
                        load = int(parse_qs(url.query).get('load',['1'])[0])
                        return self.send(200,state(db,load))
                return self.send(404,{'error':'Ruta inexistente'})
            except (ValueError,KeyError) as exc: self.send(400,{'error':str(exc)})
            except Exception as exc:
                self.log_error('%s',exc); self.send(500,{'error':'Error interno; consulte el registro del servidor'})

        def do_POST(self):
            if not self.local() or self.headers.get('X-Catalog-Token') != token or self.headers.get('Origin') not in {None,f'http://127.0.0.1:{port}'}:
                return self.send(403,{'error':'Solicitud no autorizada'})
            try:
                length = int(self.headers.get('Content-Length','0'))
                if length <= 0 or length > 100*1024*1024: raise ValueError('Solicitud vacía o mayor a 100 MB')
                data = json.loads(self.rfile.read(length))
                with closing(op.connect(dbpath)) as db:
                    if self.path=='/api/import':
                        op.credentials(data)
                        if data.get('full_snapshot') is not True: raise ValueError('Confirme archivo completo de la fuente')
                        source = op.clean(data.get('source'))
                        if not source: raise ValueError('Fuente obligatoria')
                        filename = Path(data['filename']).name
                        if Path(filename).suffix.lower()!='.xlsx': raise ValueError('Seleccione un archivo XLSX')
                        content = base64.b64decode(data['content'], validate=True)
                        op.backup(db,Path(dbpath).parent/'backups')
                        with tempfile.TemporaryDirectory() as folder:
                            path = Path(folder)/filename; path.write_bytes(content)
                            result = import_excel(path,dbpath,source)
                        # También recupera una preparación interrumpida tras importar.
                        db.row_factory = None
                        op.build(db,result['load_id'])
                        db.row_factory = op.sqlite3.Row
                        op.ensure_sample(db,result['load_id'])
                        if not result['repeated']:
                            with db: op.audit(db,'load',result['load_id'],'upload_full_file',None,{'source':source,'filename':filename},data['actor'],data['reason'])
                    else:
                        actions = {'/api/review':op.save_review,'/api/technical':op.save_technical,'/api/manual':op.manual,'/api/publish':op.publish}
                        action = actions.get(self.path)
                        if not action: return self.send(404,{'error':'Ruta inexistente'})
                        if self.path=='/api/publish': op.backup(db,Path(dbpath).parent/'backups')
                        result = action(db,data)
                self.send(200,result)
            except (ValueError,KeyError,TypeError,op.sqlite3.IntegrityError) as exc: self.send(400,{'error':str(exc)})
            except Exception as exc:
                self.log_error('%s',exc); self.send(500,{'error':'Error interno; operación interrumpida. Consulte el registro del servidor'})
    return Handler


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--db',default=str(op.DEFAULT_DB)); parser.add_argument('--port',type=int,default=8766)
    args=parser.parse_args()
    if not Path(args.db).is_file(): raise ValueError('Base de datos inexistente')
    with closing(op.connect(args.db)) as db:
        saved=op.backup(db); op.setup(db)
        for (load_id,) in db.execute('SELECT DISTINCT load_id FROM unified_catalog_reviews').fetchall(): op.ensure_sample(db,load_id)
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('Integridad inválida')
    server=HTTPServer(('127.0.0.1',args.port),handler(args.db,secrets.token_urlsafe(32),args.port))
    print(f'Catálogo: http://127.0.0.1:{args.port}/ | respaldo {saved}',flush=True)
    server.serve_forever()


if __name__=='__main__': main()
