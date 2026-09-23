import unittest
import tempfile
from pathlib import Path
import pandas as pd
from catalogo.import_excel import connect,stage_frame
from test_import import row


class RelationalImportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=connect(Path(self.temp.name)/'new.sqlite3')

    def tearDown(self):
        self.db.close();self.temp.cleanup()

    def stage(self,rows,digest,source='RLA_Productos'):
        return stage_frame(self.db,pd.DataFrame(rows),source,'nuevo.xlsx',digest*64,'Lista de productos')

    def test_successive_loads_reuse_labels_and_preserve_old_links(self):
        a=self.stage([row(**{'Report Group':'CABLES'})],'a')
        b=self.stage([row(**{'Report Group':'CABLES'}),row(**{'Product ID':'2','Report Group':'MICROFONOS'})],'b')
        self.assertEqual((a['classification_links'],b['classification_links']),(1,2))
        self.assertEqual(self.db.execute('SELECT count(*) FROM classification_values').fetchone()[0],2)
        self.assertEqual(self.db.execute('SELECT count(*) FROM record_classifications').fetchone()[0],3)
        self.assertTrue(self.stage([row()],'b')['repeated'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM record_classifications').fetchone()[0],3)
        self.assertEqual(self.db.execute('SELECT count(*) FROM active_loads').fetchone()[0],0)
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_source_scoping_and_quarantine_evidence(self):
        self.stage([row(**{'SITEID':'','Report Group':'CABLES'})],'a')
        self.stage([row(**{'Report Group':'CABLES'})],'b','Otra')
        self.assertEqual(self.db.execute('SELECT count(*) FROM classification_values').fetchone()[0],2)
        self.assertEqual(self.db.execute('SELECT count(*) FROM record_classifications').fetchone()[0],2)

    def test_failure_rolls_back_new_load_and_labels(self):
        self.db.executescript("CREATE TRIGGER simulate_failure BEFORE INSERT ON record_classifications BEGIN SELECT RAISE(ABORT,'test'); END;")
        with self.assertRaises(Exception):self.stage([row(**{'Report Group':'CABLES'})],'a')
        for table in ['loads','raw_records','normalized_records','classification_values']:
            self.assertEqual(self.db.execute(f'SELECT count(*) FROM {table}').fetchone()[0],0)

    def test_manual_and_approved_data_survive(self):
        self.db.execute("INSERT INTO manufacturers(canonical_name,canonical_key) VALUES('SHURE','SHURE')")
        self.db.execute("INSERT INTO master_products(standard_name,product_type,origin,created_by,creation_reason,manufacturer_id) VALUES('Manual','ITEM','manual','Revisor','Alta',1)")
        self.db.commit()
        self.stage([row(**{'MANUFACTURER':'Otro','Report Group':'CABLES'})],'a')
        self.assertEqual(self.db.execute('SELECT standard_name,manufacturer_id FROM master_products').fetchone(),('Manual',1))
        self.assertEqual(self.db.execute('SELECT count(*) FROM manufacturers').fetchone()[0],1)


if __name__=='__main__':unittest.main()
