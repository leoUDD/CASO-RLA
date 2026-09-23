import json
from pathlib import Path
import tempfile
import base64
import io
import threading
from http.server import HTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import unittest

import pandas as pd
from db.import_excel import connect, stage_frame
from db.seed_taxonomy import seed
from db.build_catalog import build
from db import operations as op


def record(code='A', **extra):
    r={'Product ID':code,'Description':'Proyector de sala','Type':'ITEM','Package':'ITEM',
       'ITEMCATEGORY':'SERIAL','SITEID':'S1','SITENAME':'Sala','Stock':'2.00',
       'Cost':'3.00','Replacement Cost':'4.00','MANUFACTURER':'','MODEL':'',
       'CANRENT':'RENTABLE','CANSELL':'SELLABLE','CANSUBRENT':'SUBRENT',
       'AFFECTSAVAILABILITY':'TRUE','ISFREIGHT':'NOTFREIGHT','Report Group':'PROYECTORES'}
    r.update(extra); return r


class OperationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.db=connect(Path(self.tmp.name)/'test.sqlite3')
        stage_frame(self.db,pd.DataFrame([record()]),'RLA_Productos','a.xlsx','a'*64)
        seed(self.db,json.loads(Path('outputs/estandarizacion/propuesta.json').read_text(encoding='utf-8')))
        build(self.db,1); self.db.row_factory=op.sqlite3.Row; op.setup(self.db)
        self.who={'actor':'test','reason':'Prueba transaccional'}
    def tearDown(self): self.db.close(); self.tmp.cleanup()
    def publish(self,load=1,date='2026-09-22T18:00:00-03:00'):
        return op.publish(self.db,dict(self.who,load_id=load,token=op.preview(self.db,load)['token'],snapshot_at=date,full_snapshot=True))
    def stage(self,rows,source='RLA_Productos',letter='b'):
        result=stage_frame(self.db,pd.DataFrame(rows),source,'next.xlsx',letter*64)
        self.db.row_factory=None; build(self.db,result['load_id']); self.db.row_factory=op.sqlite3.Row
        return result['load_id']
    def test_review_persists_and_stale_write_rejected(self):
        row=op.review_rows(self.db,1)[0]; family=self.db.execute('SELECT family_id FROM families LIMIT 1').fetchone()[0]
        data=dict(self.who,load_id=1,legacy_id=row['legacy_id'],revision=row['revision'],family_id=family,decision='approve')
        op.save_review(self.db,data)
        self.assertEqual(self.db.execute('SELECT family_id FROM master_products').fetchone()[0],family)
        with self.assertRaises(ValueError): op.save_review(self.db,data)
        row=op.review_rows(self.db,1)[0]
        op.save_review(self.db,dict(data,revision=row['revision'],decision='reject'))
        self.assertIsNone(self.db.execute('SELECT family_id FROM master_products').fetchone()[0])
    def test_manual_idempotence_and_rollback(self):
        data=dict(self.who,name='Producto manual',product_type='ITEM',request_id='one')
        a=op.manual(self.db,data); b=op.manual(self.db,data)
        self.assertEqual(a['master_id'],b['master_id']); self.assertTrue(b['repeated'])
        with self.assertRaises(ValueError): op.manual(self.db,dict(data,name='Cambio'))
        before=self.db.execute('SELECT count(*) FROM master_products').fetchone()[0]
        with self.assertRaises(ValueError): op.manual(self.db,dict(data,request_id='two',stock='12'))
        self.assertEqual(before,self.db.execute('SELECT count(*) FROM master_products').fetchone()[0])
    def test_publish_and_reimport_do_not_reactivate(self):
        self.publish(); self.assertEqual(self.db.execute('SELECT stock FROM current_inventory').fetchone()[0],'2.00')
        self.assertEqual(self.db.execute('SELECT affects_availability FROM current_inventory').fetchone()[0],1)
        with self.assertRaises(ValueError): self.publish()
        load=self.stage([record('B')]); self.publish(load,'2026-09-23T18:00:00-03:00')
        self.assertTrue(op.preview(self.db,1)['stale'])
        with self.assertRaises(ValueError): self.publish(1,'2026-09-24T18:00:00-03:00')
        self.assertEqual(self.db.execute('SELECT count(*) FROM inventory_snapshots').fetchone()[0],2)
        self.assertEqual(self.db.execute('SELECT count(*) FROM current_inventory').fetchone()[0],1)
    def test_sources_and_manual_survive(self):
        m=op.manual(self.db,dict(self.who,name='Manual',product_type='ITEM',request_id='m'))
        self.publish(); other=self.stage([record('C')],source='Other'); self.publish(other)
        new=self.stage([record('B')],letter='c'); self.assertEqual(op.preview(self.db,new)['absent_codes'],1)
        self.publish(new,'2026-09-23T18:00:00-03:00')
        self.assertEqual(self.db.execute('SELECT count(*) FROM current_inventory').fetchone()[0],2)
        self.assertTrue(self.db.execute('SELECT 1 FROM current_catalog WHERE master_id=?',(m['master_id'],)).fetchone())
    def test_quarantine_explicit_exclusion(self):
        load=self.stage([record('B'),record('DEFAULTITEM',SITEID='',SITENAME='')])
        self.assertFalse(op.preview(self.db,load)['ready'])
        row=op.technical_rows(self.db,load)[0]
        op.save_technical(self.db,dict(self.who,load_id=load,raw_record_id=row['raw_record_id'],decision='exclude'))
        self.assertTrue(op.preview(self.db,load)['ready']); self.publish(load)
        self.assertEqual(self.db.execute('SELECT count(*) FROM current_inventory').fetchone()[0],1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM raw_records WHERE validation_status='quarantined'").fetchone()[0],1)
        with self.assertRaises(ValueError): op.save_technical(self.db,dict(self.who,load_id=load,raw_record_id=row['raw_record_id'],decision='pending'))
    def test_cannot_exclude_arbitrary_bad_row(self):
        load=self.stage([record('BROKEN',SITEID='')]); row=op.technical_rows(self.db,load)[0]
        with self.assertRaises(ValueError): op.save_technical(self.db,dict(self.who,load_id=load,raw_record_id=row['raw_record_id'],decision='exclude'))
    def test_publish_rolls_back_entire_load_on_unknown_flag(self):
        load=self.stage([record('B'),record('C',ISFREIGHT='UNKNOWN')])
        with self.assertRaises(ValueError): self.publish(load)
        self.assertEqual(self.db.execute('SELECT count(*) FROM inventory_snapshots').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM sites').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM active_loads').fetchone()[0],0)
    def test_missing_actor_and_stale_preview(self):
        p=op.preview(self.db,1)
        with self.assertRaises(ValueError): op.publish(self.db,dict(self.who,load_id=1,token=p['token'],full_snapshot=True,snapshot_at='2026-09-22'))
        with self.assertRaises(ValueError): op.manual(self.db,dict(self.who,actor='',name='A',product_type='ITEM',request_id='x'))
        with self.assertRaises(ValueError): op.publish(self.db,dict(self.who,load_id=1,token='stale',full_snapshot=True,snapshot_at='2026-09-22T00:00:00Z'))
    def test_provisional_uses_original_upload_date(self):
        received=self.db.execute('SELECT received_at FROM loads WHERE load_id=1').fetchone()[0]
        result=op.publish(self.db,dict(self.who,load_id=1,token=op.preview(self.db,1)['token'],full_snapshot=True,date_basis='received_at',snapshot_at='1990-01-01T00:00:00Z'))
        self.assertEqual(result['reference_at'],op.datetime.fromisoformat(received.replace('Z','+00:00')).isoformat())
        self.assertEqual(self.db.execute('SELECT date_basis FROM publications').fetchone()[0],'received_at')
        op.setup(self.db)
        self.assertEqual(self.db.execute('SELECT date_basis FROM publications').fetchone()[0],'received_at')
    def test_sample_does_not_shrink_after_review(self):
        with self.db: self.db.execute("UPDATE unified_catalog_reviews SET status='approved_by_rule'")
        op.ensure_sample(self.db,1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM quality_samples').fetchone()[0],1)
        with self.db: self.db.execute("UPDATE unified_catalog_reviews SET status='pending'")
        op.ensure_sample(self.db,1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM quality_samples').fetchone()[0],1)

    def test_http_upload_and_csrf(self):
        from db.catalog_app import handler
        path=Path(self.tmp.name)/'test.sqlite3'
        server=HTTPServer(('127.0.0.1',0),handler(path,'test-token',0))
        port=server.server_address[1]; server.RequestHandlerClass=handler(path,'test-token',port)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            url=f'http://127.0.0.1:{port}'
            with urlopen(url+'/api/state?load=1') as response:
                self.assertEqual(len(json.load(response)['rows']),1)
            req=Request(url+'/api/manual',data=b'{}',headers={'Content-Type':'application/json'},method='POST')
            with self.assertRaises(HTTPError) as rejected:urlopen(req)
            self.assertEqual(rejected.exception.code,403)
            content=io.BytesIO()
            pd.DataFrame([record('NEW')]).to_excel(content,sheet_name='Lista de productos',index=False)
            payload=dict(self.who,filename='full.xlsx',content=base64.b64encode(content.getvalue()).decode(),source='RLA_Productos',full_snapshot=True)
            def upload():
                req=Request(url+'/api/import',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','X-Catalog-Token':'test-token'},method='POST')
                with urlopen(req) as response:return json.load(response)
            first=upload(); again=upload()
            self.assertEqual(first['import']['load_id'],again['import']['load_id']);self.assertTrue(again['import']['repeated'])
            self.assertEqual(again['standardization']['new_codes'],0)
            self.assertEqual(self.db.execute('SELECT count(*) FROM active_loads').fetchone()[0],0)
        finally: server.shutdown();server.server_close();worker.join()


if __name__=='__main__': unittest.main()
