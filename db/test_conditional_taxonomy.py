import unittest
from db.conditional_taxonomy import classify

class ConditionalTests(unittest.TestCase):
    def result(self,text,family,package='ITEM'):
        return classify({'description_key':text,'Package':package,'Type':'ITEM','quarantined':False},{family})['family']
    def test_accessory_before_keyword(self):
        self.assertEqual(self.result('RECEPTOR DE MICROFONO','Micrófonos'),'Accesorios de audio')
        self.assertEqual(self.result('LENTE DE PROYECTOR','Proyectores'),'Accesorios de video')
    def test_package_preserved(self):
        self.assertEqual(self.result('MICROFONO DE MANO CON RECEPTOR','Micrófonos','PACKAGE'),'Micrófonos')
        self.assertIsNone(self.result('SISTEMA DE PROYECCION','Proyectores','PACKAGE'))
    def test_cable_exclusions(self):
        self.assertEqual(self.result('DISTRIBUIDOR ELECTRICO 100A','Cables y adaptadores'),'Distribución eléctrica')
        self.assertIsNone(self.result('CAJA REMOTA X32','Cables y adaptadores'))
        self.assertEqual(self.result('CABLE BNC 30 METROS','Cables y adaptadores'),'Cables y adaptadores')
    def test_uncertain_and_warning(self):
        self.assertIsNone(self.result('CAPSULA LAVALIER','Micrófonos'))
        self.assertIsNone(self.result('PROBARPROYECTOR 6000','Proyectores'))

if __name__=='__main__':unittest.main()
