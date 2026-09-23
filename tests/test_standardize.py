from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import pandas as pd
from catalogo import operations as op, standardize as std, std_rules as R
from catalogo.build_catalog import build
from catalogo.export_catalog import export
from catalogo.import_excel import connect, stage_frame


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
    record('11140', 'Cable HDMI 5 metros', Stock='4,00'),   # misma ficha dos veces en Chile → duplicado
    record('11141', 'Cable HDMI 5 mts', Stock='1,00'),
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
        # Mismo proyector en Chile y Colombia con otra escritura de marca/modelo → equivalente entre países
        self.assertIsNotNone(self.product('CO PRY01')['duplicate_group'])
        self.assertEqual(self.product('CO PRY01')['duplicate_group'], self.product('11133')['duplicate_group'])
        self.assertEqual(self.product('CO PRY01')['duplicate_kind'], 'Otro país')
        # Dos fichas del mismo cable en Chile → duplicado en el mismo país
        self.assertEqual(self.product('11140')['duplicate_kind'], 'Mismo país')
        self.assertIsNone(self.product('10208')['duplicate_group'])  # 30 m ≠ 20 m
        # Stock por país, sin sumar países; el stock en un sitio de descarte no cuenta como disponible
        self.assertEqual(json.loads(self.product('11135')['stock_by_country']), {'Sin país': 7.0})
        self.assertEqual(json.loads(self.product('CO PRY01')['stock_by_country']), {'CO': 2.0})
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
        self.assertEqual(json.loads(self.product('11135')['stock_by_country']), {'CL': 7.0})

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

    def test_detail_explains_available_stock(self):
        product = self.product('11135')  # 5 en "Botar Chile" (descarte, CL) y 7 en "H. W" (sede, sin país)
        detail = std.detail(self.db, product['master_id'])
        self.assertEqual(detail['stock_summary'], [
            {'country': 'CL', 'available': 0.0, 'unavailable': {'Descarte / baja': 5.0}},
            {'country': 'Sin país', 'available': 7.0, 'unavailable': {}}])
        # El disponible del resumen coincide con stock_by_country (misma regla)
        self.assertEqual({r['country']: r['available'] for r in detail['stock_summary'] if r['available']},
                         json.loads(product['stock_by_country']))
        self.assertEqual([r['available'] for r in detail['stock']], [True, False])  # disponibles primero

    def test_link_equivalents_keeps_inventory_by_country(self):
        cl, co = self.product('11133'), self.product('CO PRY01')
        with self.assertRaises(ValueError):
            std.link(self.db, {'target_id': cl['master_id'], 'source_id': co['master_id'], 'actor': '', 'reason': 'x'})
        result = std.link(self.db, dict(self.who, target_id=cl['master_id'], source_id=co['master_id']))
        self.assertEqual((result['codes'], result['retired_code']), (['CO PRY01'], co['standard_code']))
        std.apply(self.db, self.load)
        linked = self.product('11133')
        self.assertEqual(linked['legacy_codes'], '11133, CO PRY01')
        self.assertEqual(linked['standard_code'], cl['standard_code'])                 # conserva el código del destino
        self.assertEqual(json.loads(linked['stock_by_country']), {'CL': 2.0, 'CO': 2.0})  # separado por país
        self.assertIsNone(linked['duplicate_group'])
        self.assertEqual(std.search(self.db, co['standard_code'])['rows'][0]['master_id'], cl['master_id'])  # código retirado sigue sirviendo
        std.apply(self.db, self.load)  # una nueva estandarización no deshace la vinculación
        self.assertEqual(self.product('CO PRY01')['master_id'], cl['master_id'])
        link_id = std.detail(self.db, cl['master_id'])['links'][0]['link_id']
        std.unlink(self.db, dict(self.who, link_id=link_id))
        std.apply(self.db, self.load)
        self.assertEqual(self.product('CO PRY01')['standard_code'], co['standard_code'])  # recupera su código original
        self.assertEqual(self.product('11133')['legacy_codes'], '11133')

    def test_export(self):
        from catalogo.export_catalog import info
        out = Path(self.tmp.name) / 'export.sqlite3'
        result = export(self.db, out)
        self.assertEqual(result['tables']['productos'], self.db.execute('SELECT count(*) FROM product_standards').fetchone()[0])
        with closing(sqlite3.connect(out)) as e:
            self.assertEqual(e.execute("SELECT familia FROM v_catalogo WHERE codigos_origen='10063'").fetchone()[0], 'Micrófonos')
            self.assertEqual(e.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertGreater(e.execute('SELECT count(*) FROM inventario').fetchone()[0], 0)
            self.assertEqual(e.execute("SELECT stock_por_pais,tipo_duplicado FROM v_catalogo WHERE codigos_origen='CO PRY01'").fetchone(), ('CO: 2', 'Otro país'))
            self.assertEqual(e.execute("SELECT count(DISTINCT pais) FROM stock_disponible_por_pais").fetchone()[0], 3)
            self.assertEqual(dict(e.execute('SELECT * FROM metadatos'))['version_reglas'], R.RULES_VERSION)
        # La pestaña "Base SQLite" lista cada tabla con sus atributos reales
        schema = {t['name']: t for t in info(out)['schema']}
        self.assertIn('codigo_estandar', schema['productos']['columns'])
        self.assertEqual(schema['v_catalogo']['type'], 'vista')
        self.assertEqual(schema['productos']['rows'], result['tables']['productos'])

    def test_country_filter_only_lists_countries_with_stock(self):
        from catalogo.app import stock_countries
        codes = [c['code'] for c in stock_countries(self.db)]
        self.assertEqual(codes, ['CL', 'CO', 'Sin país'])  # países sin stock disponible no aparecen; 'Sin país' al final
        self.assertEqual(std.search(self.db, '', country='Sin país')['total'], 1)

if __name__ == '__main__':
    unittest.main()
