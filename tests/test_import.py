import tempfile
import unittest
from pathlib import Path
import pandas as pd
from catalogo.import_excel import connect, stage_frame, normalize, decimal_text


def row(**changes):
    result = {'Product ID':'00123','Description':' Cable  20 m ','Type':'ITEM',
              'ITEMCATEGORY':'NONSERIAL','Package':'ITEM','SITEID':'S1','SITENAME':'Sitio 1',
              'MANUFACTURER':'Marca','MODEL':'AB-20/C','Stock':'1.234,50','Cost':'0,00',
              'Replacement Cost':'','CANRENT':'RENTABLE','CANSELL':'NOTSELLABLE','CANSUBRENT':'SUBRENT'}
    result.update(changes)
    return result


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.db = connect(Path(self.folder.name)/'test.sqlite3')

    def tearDown(self):
        self.db.close()
        self.folder.cleanup()

    def stage(self,rows,digest='a'):
        return stage_frame(self.db,pd.DataFrame(rows),'RLA_Productos','prueba.xlsx',digest*64)

    def test_decimal_and_identity(self):
        n,issues = normalize(row())
        self.assertEqual(n['Product ID'],'00123')
        self.assertEqual(n['MODEL'],'AB-20/C')
        self.assertEqual(n['Stock'],'1234.50')
        self.assertEqual(n['Cost'],'0.00')
        self.assertIsNone(n['Replacement Cost'])
        self.assertEqual(n['Description'],'Cable 20 m')
        self.assertEqual(issues,[])
        with self.assertRaises(ValueError): decimal_text('1,234')

    def test_idempotent_load(self):
        first = self.stage([row()])
        again = self.stage([row()])
        self.assertEqual(first['load_id'],again['load_id'])
        self.assertTrue(again['repeated'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM raw_records').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM master_products').fetchone()[0],0)
        self.assertFalse(first['published'])

    def test_missing_site_preserves_all_rows_and_active_load(self):
        self.db.execute("INSERT INTO loads(source_id,filename,sha256,status,row_count) VALUES(1,'anterior',?,'valid',1)",('z'*64,))
        self.db.execute('INSERT INTO active_loads VALUES(1,1)')
        self.db.commit()
        result = self.stage([row(),row(**{'Product ID':'2','SITEID':''})])
        self.assertEqual(result['row_status'],{'accepted':1,'quarantined':1})
        self.assertFalse(result['ready_for_publication'])
        self.assertEqual(self.db.execute('SELECT load_id FROM active_loads').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM normalized_records').fetchone()[0],2)

    def test_duplicates_quarantine_every_occurrence(self):
        result = self.stage([row(),row()])
        self.assertEqual(result['row_status'],{'quarantined':2})

    def test_conflicting_identity_across_sites(self):
        result = self.stage([row(),row(**{'SITEID':'S2','MODEL':'DISTINTO'})])
        self.assertEqual(result['row_status'],{'quarantined':2})

    def test_missing_schema_and_empty_file(self):
        self.assertFalse(self.stage([{'Product ID':'1'}])['ready_for_publication'])
        self.assertFalse(self.stage([],digest='b')['ready_for_publication'])

    def test_negative_values_are_not_silently_corrected(self):
        n,issues = normalize(row(Stock='-2,00',MODEL='N/A'))
        self.assertEqual(n['Stock'],'-2.00')
        self.assertEqual(n['MODEL'],'N/A')
        self.assertTrue(all(i[0]=='warning' for i in issues))
        self.assertEqual(len(issues),2)


if __name__ == '__main__': unittest.main()
