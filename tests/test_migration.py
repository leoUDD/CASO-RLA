import sqlite3
from pathlib import Path
import unittest
from catalogo.migrate_v4 import apply_migration


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.executescript(Path(__file__).resolve().parents[1].joinpath('catalogo', 'sql', 'schema.sql').read_text(encoding='utf-8'))

    def tearDown(self):self.db.close()

    def test_preserves_labels_and_is_idempotent(self):
        self.db.execute("INSERT INTO loads(source_id,filename,sha256,row_count) VALUES(1,'test',?,1)",('a'*64,))
        self.db.execute('INSERT INTO raw_records(load_id,excel_row,raw_json) VALUES(1,2,?)',('{"Report Group":"CABLES","TAXGROUP":"0%"}',))
        self.db.commit()
        self.assertTrue(apply_migration(self.db))
        self.assertEqual(self.db.execute('SELECT count(*) FROM record_classifications').fetchone()[0],2)
        self.assertFalse(apply_migration(self.db))
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_failure_rolls_back_ddl(self):
        self.db.execute('CREATE TABLE countries(collision TEXT)')
        self.db.commit()
        with self.assertRaises(sqlite3.OperationalError):apply_migration(self.db)
        self.assertIsNone(self.db.execute("SELECT 1 FROM sqlite_master WHERE name='manufacturers'").fetchone())
        self.assertIsNone(self.db.execute('SELECT 1 FROM schema_version WHERE version=4').fetchone())

    def test_typed_attribute_and_country_fk(self):
        apply_migration(self.db)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO sites(source_id,source_site_code,name,country_id) VALUES(1,'S','Sitio',999)")
        self.db.execute("INSERT INTO master_products(standard_name,product_type,origin,created_by,creation_reason) VALUES('Cable','ITEM','manual','Prueba','Test')")
        self.db.execute("INSERT INTO attribute_definitions(code,name,data_type) VALUES('length','Longitud','decimal')")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO product_attribute_values(master_id,attribute_id,value_text,review_status,author,updated_at) VALUES(1,1,'texto','draft','Prueba','2026-09-22')")


if __name__=='__main__':unittest.main()
