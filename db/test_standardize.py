from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import pandas as pd
from db import operations as op, standardize as std, std_rules as R
from db.build_catalog import build
from db.export_catalog import export
from db.import_excel import connect, stage_frame


def record(code, description, site='CD SANTIAGO', site_name='CD Santiago', **extra):
    r = {'Product ID': code, 'Description': description, 'Type': 'ITEM', 'Package': 'ITEM', 'ITEMCATEGORY': 'SERIAL',
         'SITEID': site, 'SITENAME': site_name, 'Stock': '2,00', 'Cost': '3,00', 'Replacement Cost': '4,00',
         'MANUFACTURER': '', 'MODEL': '', 'CANRENT': 'RENTABLE', 'CANSELL': 'SELLABLE', 'CANSUBRENT': 'SUBRENT',
         'AFFECTSAVAILABILITY': 'TRUE', 'ISFREIGHT': 'NOTFREIGHT'}
    r.update(extra)
    return r


ROWS = [
    record('10063', 'Microfono Alambrico Dinámico', MANUFACTURER='SHURE', MODEL='SM-58', **{'Report Group': 'MICROFONOS'}),
    record('10208', 'Cable BNC M-M 30 metros'),
    record('10209', 'Cable BNC M-M 20 metros'),
    record('CO PRY01', 'Proyector 6.000 Ansilumenes / Formato 4:3 / XGA LCD (CO)', 'CD BOGOTA', 'CD Bogota', MANUFACTURER='NEC', MODEL='PA-600X'),
    record('11133', 'Proyector 6.000 Ansilumenes / Formato 4:3 / XGA LCD', MANUFACTURER='N.E.C', MODEL='PA 600X'),
    record('11134', 'NO USAR Proyector viejo'),
    record('11135', 'Parlante activo', 'BOTAR CHILE', 'Botar Chile', Stock='5,00', MANUFACTURER='BOSE'),
    record('11135', 'Parlante activo', 'H. W', 'H. W', Stock='7,00', MANUFACTURER='BOSE'),
    record('11136', 'Objeto sin regla conocida'),
]


class StandardizeRulesTests(unittest.TestCase):
    def test_names(self):
        self.assertEqual(R.normalize_name('Cable BNC M-M 30 metros'), 'Cable BNC macho-macho 30 m')
        self.assertEqual(R.normalize_name('TV de 42¨'), 'TV de 42 in')
        self.assertEqual(R.normalize_name('Panel LED 50X50 Pixel 2.9 D2V (CL)'), 'Panel LED 50X50 Pixel 2.9 D2V')
        self.assertEqual(R.normalize_name('NO USARProyector LCD 5000 ansilúmenes'), 'Proyector LCD 5000 ANSI lm')
        self.assertIsNone(R.normalize_name('.'))
        self.assertEqual(R.standard_name('Micrófono de mano', 'SHURE', 'SM58'), 'Micrófono de mano SHURE SM58')
        self.assertEqual(R.standard_name('Micrófono SHURE SM58', 'SHURE', 'SM58'), 'Micrófono SHURE SM58')

    def test_brands_sites_and_families(self):
        self.assertEqual(R.brand_key('DA - LITE'), R.brand_key('DALITE'))
        self.assertEqual(R.brand_key('Black Magic'), R.brand_key('BLACKMAGIC DESIGN'))
        self.assertIsNone(R.brand_key('GENÉRICO')); self.assertIsNone(R.brand_key('S/M'))
        self.assertEqual(R.site_country('CD BOGOTA', 'CD Bogota')[0], 'CO')
        self.assertEqual(R.site_country('X', 'Hotel X', 0.5, 'PE', 0.9), ('PE', 'prefijo de códigos'))
        self.assertEqual(R.site_country('H. W', 'H. W')[0], None)
        self.assertEqual(R.site_type('INVENTARIO 2023', 'INV 2023 (Ghost)'), 'Ajuste / no ubicado')
        self.assertEqual(R.site_type('BOTAR CHILE', 'Botar Chile'), 'Descarte / baja')
        self.assertEqual(R.classify('Micrófono inalámbrico', ['MICROFONOS']), ('Micrófonos', 'Alta confianza'))
        self.assertEqual(R.classify('Adaptador HDMI a VGA', ['ACCESORIOS DE VIDEO']), ('Cables y adaptadores', 'Por nombre (etiqueta genérica)'))
        self.assertEqual(R.classify('Sistema de amplificación salón'), ('Paquetes y soluciones', 'Por nombre'))
        self.assertEqual(R.classify('Objeto raro')[1], 'Revisar: sin regla')


class StandardizeDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 't.sqlite3'
        self.db = connect(self.path)
        self.load = stage_frame(self.db, pd.DataFrame(ROWS), 'RLA_Productos', 'a.xlsx', 'a' * 64)['load_id']
        std.ensure_taxonomy(self.db, self.load)
        build(self.db, self.load)
        self.db.row_factory = op.sqlite3.Row
        op.setup(self.db)
        self.summary = std.apply(self.db, self.load)
        self.who = {'actor': 'test', 'reason': 'Prueba'}

    def tearDown(self):
        self.db.close(); self.tmp.cleanup()

    def product(self, code):
        return dict(self.db.execute('''SELECT p.*,f.name family,b.canonical_name brand FROM product_standards p
            LEFT JOIN families f USING(family_id) LEFT JOIN manufacturers b USING(manufacturer_id)
            WHERE (', '||p.legacy_codes||',') LIKE ?''', (f'%, {code},%',)).fetchone())

    def test_full_standardization(self):
        mic = self.product('10063')
        self.assertEqual(mic['standard_name'], 'Micrófono Alámbrico Dinámico SHURE SM-58')
        self.assertEqual((mic['family'], mic['method']), ('Micrófonos', 'Alta confianza'))
        self.assertRegex(mic['standard_code'], r'^AUD-MIC-\d{5}$')
        self.assertEqual(self.product('10208')['family'], 'Cables y adaptadores')
        self.assertIsNone(self.product('11134')['standard_code'])  # "NO USAR": sin código nuevo
        self.assertEqual(self.product('11136')['method'], 'Revisar: sin regla')
        # Mismo proyector en Chile y Colombia con otra escritura de marca/modelo → candidato a duplicado
        self.assertIsNotNone(self.product('CO PRY01')['duplicate_group'])
        self.assertEqual(self.product('CO PRY01')['duplicate_group'], self.product('11133')['duplicate_group'])
        self.assertIsNone(self.product('10208')['duplicate_group'])  # 30 m ≠ 20 m
        # El stock en un sitio de descarte no cuenta como disponible
        self.assertEqual(self.product('11135')['stock_available'], 7.0)
        sites = {s['code']: s for s in std.sites(self.db)}
        self.assertEqual((sites['CD BOGOTA']['country'], sites['BOTAR CHILE']['site_type']), ('CO', 'Descarte / baja'))

    def test_repeatable_and_respects_people(self):
        codes = dict(self.db.execute('SELECT master_id,standard_code FROM product_standards'))
        again = std.apply(self.db, self.load)
        self.assertEqual(again['new_codes'], 0)
        self.assertEqual(codes, dict(self.db.execute('SELECT master_id,standard_code FROM product_standards')))
        site = next(s for s in std.sites(self.db) if s['code'] == 'H. W')
        std.set_site(self.db, dict(self.who, site_id=site['site_id'], country_code='CL'))
        std.apply(self.db, self.load)
        self.assertEqual(next(s for s in std.sites(self.db) if s['code'] == 'H. W')['country'], 'CL')
        self.assertIn('CL', self.product('11135')['countries'])

    def test_search_and_new_product(self):
        found = std.search(self.db, 'microfono shure')
        self.assertEqual(found['total'], 1)
        self.assertEqual(std.search(self.db, 'MICRÓFONO dinamico')['rows'][0]['standard_code'], found['rows'][0]['standard_code'])
        self.assertGreaterEqual(std.search(self.db, '', status='review')['total'], 2)
        proposal = std.propose(self.db, {'name': 'MICROFONO ALAMBRICO DINAMICO', 'brand': 'Shure', 'model': 'sm 58', 'product_type': 'ITEM'})
        self.assertEqual(proposal['family'], 'Micrófonos')
        self.assertEqual(len(proposal['exact_duplicates']), 1)
        data = dict(self.who, name='MICROFONO ALAMBRICO DINAMICO', brand='Shure', model='sm-58', product_type='ITEM', request_id='r1')
        with self.assertRaises(ValueError):
            std.create(self.db, data)  # duplicado exacto sin confirmar
        created = std.create(self.db, dict(data, request_id='r2', name='Microfono de podio cuello largo', model='MX418'))
        self.assertRegex(created['standard_code'], r'^AUD-MIC-\d{5}$')
        self.assertEqual(std.search(self.db, 'podio')['rows'][0]['origin'], 'manual')
        std.apply(self.db, self.load)  # una recarga no elimina ni re-codifica el alta manual
        self.assertEqual(std.search(self.db, 'podio')['rows'][0]['standard_code'], created['standard_code'])

    def test_review_assigns_code(self):
        row = next(r for r in op.review_rows(self.db, self.load) if r['legacy_code'] == '11136')
        fam = self.db.execute("SELECT family_id FROM families WHERE name='Mobiliario y oficina'").fetchone()[0]
        op.save_review(self.db, dict(self.who, load_id=self.load, legacy_id=row['legacy_id'], revision=row['revision'],
                                     decision='approve', family_id=fam))
        std.after_review(self.db, row['master_id'], 'approve')
        product = self.product('11136')
        self.assertEqual((product['family'], product['method']), ('Mobiliario y oficina', 'Revisor'))
        self.assertRegex(product['standard_code'], r'^MOB-MOB-\d{5}$')
        std.apply(self.db, self.load)  # la decisión humana prevalece sobre la regla
        self.assertEqual(self.product('11136')['method'], 'Revisor')

    def test_export(self):
        out = Path(self.tmp.name) / 'export.sqlite3'
        info = export(self.db, out)
        self.assertEqual(info['tables']['productos'], self.db.execute('SELECT count(*) FROM product_standards').fetchone()[0])
        with closing(sqlite3.connect(out)) as e:
            self.assertEqual(e.execute("SELECT familia FROM v_catalogo WHERE codigos_origen='10063'").fetchone()[0], 'Micrófonos')
            self.assertEqual(e.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertGreater(e.execute('SELECT count(*) FROM inventario').fetchone()[0], 0)
            self.assertEqual(json.loads(json.dumps(dict(e.execute('SELECT * FROM metadatos'))))['version_reglas'], R.RULES_VERSION)


if __name__ == '__main__':
    unittest.main()
