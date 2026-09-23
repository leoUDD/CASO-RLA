import unittest
from catalogo.build_catalog import review

class CatalogTests(unittest.TestCase):
 def p(self,text,group,**extra):
  p={'description_key':text,'Type':'ITEM','Package':'ITEM','quarantined':False,'Report Group':group};p.update(extra);return p
 def test_clear_approved(self):
  self.assertEqual(review(self.p('IMPRESORA LASER','IMPRESORAS'),{'IMPRESORAS':'Impresoras'})['status'],'approved_by_rule')
 def test_wrong_group_not_approved(self):
  self.assertEqual(review(self.p('LENTE PARA CAMARA','PROYECTORES'),{'PROYECTORES':'Proyectores'})['status'],'pending')
 def test_package_and_warning(self):
  aliases={'PROYECTORES':'Proyectores'}
  self.assertEqual(review(self.p('PROYECTOR','PROYECTORES',Package='PACKAGE'),aliases)['status'],'pending')
  self.assertEqual(review(self.p('PROYECTOR NO USAR','PROYECTORES'),aliases)['status'],'pending')
 def test_quarantine(self):
  self.assertEqual(review(self.p('PROYECTOR','PROYECTORES',quarantined=True),{'PROYECTORES':'Proyectores'})['status'],'quarantined')

if __name__=='__main__':unittest.main()
