"""Ensayo integral en una copia temporal; no publica ni crea productos de prueba en la base real."""
from contextlib import closing
import json
from pathlib import Path
import tempfile
from db import operations as op


def main():
    with tempfile.TemporaryDirectory() as folder:
        with closing(op.connect()) as source, closing(op.connect(Path(folder)/'verification.sqlite3')) as db:
            source.backup(db); op.setup(db)
            who={'actor':'prueba en copia temporal','reason':'Validar flujo sin modificar la base operativa'}
            for row in op.technical_rows(db,1):
                op.save_technical(db,dict(who,load_id=1,raw_record_id=row['raw_record_id'],decision='exclude'))
            publication=op.publish(db,dict(who,load_id=1,token=op.preview(db,1)['token'],snapshot_at='2026-09-22T00:00:00Z',full_snapshot=True))
            assert publication['rows']==57007
            assert db.execute('SELECT count(*) FROM current_inventory').fetchone()[0]==57007
            assert db.execute('SELECT count(*) FROM snapshot_classifications').fetchone()[0]>0
            assert db.execute('SELECT count(*) FROM snapshot_commercial').fetchone()[0]==57007
            site=db.execute('SELECT site_id FROM sites LIMIT 1').fetchone()[0]
            manual=op.manual(db,dict(who,name='Solo prueba temporal',product_type='ITEM',request_id='test-full',site_id=site,stock='1.00'))
            assert db.execute('SELECT 1 FROM current_catalog WHERE master_id=?',(manual['master_id'],)).fetchone()
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert not db.execute('PRAGMA foreign_key_check').fetchall()
            result={'scope':'copia temporal eliminada al terminar','publication_rows':publication['rows'],
              'classification_links':db.execute('SELECT count(*) FROM snapshot_classifications').fetchone()[0],
              'sites':db.execute('SELECT count(*) FROM sites').fetchone()[0],
              'manual_create':'ok','integrity':'ok','foreign_keys':'ok',
              'real_database_published':bool(source.execute('SELECT count(*) FROM active_loads').fetchone()[0])}
    Path('outputs/catalogo/verificacion_operaciones.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True))


if __name__=='__main__': main()
