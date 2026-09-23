import json
from pathlib import Path
import sqlite3
import unittest
from db.matching import compare,candidates,identity,save_decision


def product(code,description,brand='MARCA',model='M1'):
    return {'code':code,'Description':description,'description_key':description,'brand':brand,'model':model,
            'Type':'ITEM','Package':'ITEM','ITEMCATEGORY':'NONSERIAL','rows':[2],'quarantined':False}


class MatchingTests(unittest.TestCase):
    def test_different_lengths_are_flagged(self):
        result=compare(product('A','CABLE 20 METROS'),product('B','CABLE 30 METROS'))
        self.assertEqual(result['priority'],'diferencias relevantes')
        self.assertIn('Numeros o medidas diferentes en descripcion',result['differences'])

    def test_missing_identity_does_not_become_strong(self):
        self.assertEqual(identity('N/A'),'')
        self.assertEqual(identity('GENERICO'),'')
        result=compare(product('A','MICROFONO','',''),product('B','MICROFONO','',''))
        self.assertEqual(result['priority'],'revision por descripcion')

    def test_exact_description_preserves_conflicting_models(self):
        items={'A':product('A','MICROFONO',model='M1'),'B':product('B','MICROFONO',model='M2')}
        rows,_=candidates(items)
        self.assertEqual(len(rows),1)
        self.assertIn('Diferente modelo',rows[0]['differences'])

    def test_pair_unique_and_no_self_match(self):
        rows,_=candidates({c:product(c,'MICROFONO 18') for c in ['A','B','C']})
        self.assertEqual(len(rows),3)
        self.assertTrue(all(r['code_a']<r['code_b'] for r in rows))

    def test_decision_persists_and_audits_without_merging(self):
        db=sqlite3.connect(':memory:')
        try:
            db.executescript(Path('db/schema.sql').read_text(encoding='utf-8'))
            for file in ['002_normalization.sql','003_candidate_reviews.sql']:
                db.executescript(Path('db/migrations',file).read_text(encoding='utf-8'))
            db.execute("INSERT INTO loads(source_id,filename,sha256,row_count) VALUES(1,'test',?,2)",('a'*64,))
            for index,code in enumerate(['A','B'],1):
                db.execute("INSERT INTO raw_records(raw_record_id,load_id,excel_row,raw_json) VALUES(?,1,?,'{}')",(index,index+1))
                db.execute('INSERT INTO normalized_records VALUES(?,?,?)',(index,json.dumps({'Product ID':code}),'1.0'))
            db.commit()
            save_decision(db,1,'B','A','separate','Longitudes distintas','Revisor')
            save_decision(db,1,'A','B','pending','Reconsiderar medida','Revisor')
            self.assertEqual(db.execute('SELECT code_a,code_b,decision FROM candidate_reviews').fetchone(),('A','B','pending'))
            self.assertEqual(db.execute('SELECT count(*) FROM audit_events').fetchone()[0],2)
            self.assertEqual(db.execute('SELECT count(*) FROM product_mappings').fetchone()[0],0)
        finally: db.close()


if __name__=='__main__': unittest.main()
