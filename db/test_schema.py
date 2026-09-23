"""Pruebas de reglas de negocio en memoria, sin alterar la base del proyecto."""
import sqlite3
import unittest
from pathlib import Path


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.executescript(Path(__file__).with_name('schema.sql').read_text(encoding='utf-8'))
        self.db.execute("INSERT INTO sources(name) VALUES('Otra_fuente')")

    def tearDown(self):
        self.db.close()

    def load(self, source=1, digest='a', status='valid'):
        return self.db.execute('INSERT INTO loads(source_id,filename,sha256,status,row_count) VALUES(?,?,?,?,?)',
                               (source,'archivo.xlsx',digest*64,status,1)).lastrowid

    def master(self, origin='manual'):
        return self.db.execute("INSERT INTO master_products(standard_name,product_type,origin,created_by,creation_reason) VALUES('Equipo','ITEM',?,'Prueba','Alta de prueba')",(origin,)).lastrowid

    def test_pending_load_cannot_replace_valid(self):
        first = self.load()
        pending = self.load(digest='b',status='pending')
        self.db.execute('INSERT INTO active_loads VALUES(1,?)',(first,))
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute('UPDATE active_loads SET load_id=? WHERE source_id=1',(pending,))
        self.assertEqual(self.db.execute('SELECT load_id FROM active_loads').fetchone()[0],first)

    def test_hash_is_unique_per_source(self):
        self.load()
        with self.assertRaises(sqlite3.IntegrityError):
            self.load()
        self.load(source=2)

    def test_source_cannot_activate_another_sources_load(self):
        other = self.load(source=2)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute('INSERT INTO active_loads VALUES(1,?)',(other,))

    def test_manual_product_survives_snapshot_change(self):
        manual = self.master()
        first = self.load()
        second = self.load(digest='b')
        self.db.execute('INSERT INTO active_loads VALUES(1,?)',(first,))
        self.db.execute('UPDATE active_loads SET load_id=?',(second,))
        self.assertEqual(self.db.execute('SELECT master_id,master_code FROM current_catalog').fetchone(),
                         (manual,'PRD-000001'))
        self.assertEqual(self.db.execute('SELECT count(*) FROM current_inventory').fetchone()[0],0)

    def test_snapshot_history_and_manual_overlap(self):
        first = self.load()
        master = self.master()
        self.db.execute("INSERT INTO legacy_products VALUES(1,1,'00123')")
        self.db.execute("INSERT INTO product_mappings(legacy_id,master_id,method,reason,decided_by) VALUES(1,?,'reviewed','Coincidencia revisada','Prueba')",(master,))
        self.db.execute("INSERT INTO sites VALUES(1,1,'ST01','Sitio de prueba')")
        self.db.execute("INSERT INTO raw_records(raw_record_id,load_id,excel_row,raw_json) VALUES(1,?,2,'{}')",(first,))
        self.db.execute("INSERT INTO inventory_snapshots(source_id,load_id,raw_record_id,legacy_id,site_id,stock) VALUES(1,?,1,1,1,'5.00')",(first,))
        self.db.execute('INSERT INTO active_loads VALUES(1,?)',(first,))
        self.db.execute("INSERT INTO manual_site_entries(master_id,site_id,stock,created_by,reason) VALUES(?,1,'5.00','Prueba','Alta manual')",(master,))
        self.assertEqual(self.db.execute('SELECT count(*) FROM manual_import_overlaps').fetchone()[0],1)
        second = self.load(digest='b')
        self.db.execute('UPDATE active_loads SET load_id=?',(second,))
        self.assertEqual(self.db.execute('SELECT count(*) FROM current_inventory').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM inventory_snapshots').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM manual_site_entries').fetchone()[0],1)
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(),[])


if __name__ == '__main__':
    unittest.main()
