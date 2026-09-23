import unittest
from db.context_taxonomy import evaluate

class ContextTests(unittest.TestCase):
 def p(self,text,**extra):return dict(description_key=text,Type='ITEM',Package='ITEM',quarantined=False,**extra)
 def test_category_is_not_family(self):
  r=evaluate(self.p('.',DEPARTMENT='VIDEO'));self.assertEqual(r['status'],'solo categoria');self.assertIsNone(r['family'])
 def test_accounting_code_not_inferred(self):
  self.assertEqual(evaluate(self.p('EQUIPO',REVENUEGROUP='3040'))['status'],'pendiente')
 def test_conflict_blocks_family(self):
  self.assertIsNone(evaluate(self.p('VIDEOPROYECTOR',DEPARTMENT='VIDEO',REVENUEGROUP='AUDIO'))['family'])
 def test_specific_description_over_broad_group(self):
  self.assertEqual(evaluate(self.p('TELON ELECTRICO',DEPARTMENT='VIDEO',**{'Report Group':'PROYECTORES'}))['family'],'Pantallas de proyección')
 def test_inventorygroup_can_support(self):
  self.assertEqual(evaluate(self.p('TABLERO 100A',INVENTORYGROUP='TABLERO ELECTRICO'))['family'],'Distribución eléctrica')
 def test_package_stays_pending(self):
  p=self.p('PROYECTOR',DEPARTMENT='VIDEO');p['Package']='PACKAGE';self.assertIsNone(evaluate(p)['family'])

if __name__=='__main__':unittest.main()
