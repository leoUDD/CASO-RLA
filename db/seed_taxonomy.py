"""Carga borradores revisables; nunca asigna familias a productos."""
import argparse
from contextlib import closing
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sqlite3


def seed(db,payload):
    taxonomy=payload['taxonomy']; mappings=payload['mappings']
    assert len({f['family'] for f in taxonomy})==len(taxonomy)
    version=payload['summary']['version']
    changed=0
    with db:
        db.execute('BEGIN IMMEDIATE')
        if 'status' not in [r[1] for r in db.execute('PRAGMA table_info(families)')]:
            db.execute("ALTER TABLE families ADD COLUMN status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','approved','inactive'))")
        db.execute('''CREATE TABLE IF NOT EXISTS taxonomy_mapping_drafts (
            mapping_id INTEGER PRIMARY KEY, source_id INTEGER NOT NULL REFERENCES sources,
            version TEXT NOT NULL, field_name TEXT NOT NULL, original_value TEXT NOT NULL,
            suggested_family_id INTEGER REFERENCES families,
            status TEXT NOT NULL CHECK(status IN ('draft','needs_context','approved','rejected')),
            evidence_json TEXT NOT NULL CHECK(json_valid(evidence_json)),
            rule_id INTEGER REFERENCES standardization_rules,
            UNIQUE(source_id,version,field_name,original_value))''')
        source=db.execute('SELECT source_id FROM loads WHERE load_id=?',(payload['summary']['load'],)).fetchone()
        if not source: raise ValueError('La carga de evidencia no existe')
        families={}
        for item in taxonomy:
            # Códigos deterministas por nombre; los renombrados requieren migración explícita.
            category_code='CAT-'+hashlib.sha256(item['category'].encode()).hexdigest()[:12].upper()
            db.execute("INSERT INTO categories(name,category_code,status) SELECT ?,?,'draft' WHERE NOT EXISTS(SELECT 1 FROM categories WHERE category_code=?)",(item['category'],category_code,category_code))
            category=db.execute('SELECT category_id,name,parent_id FROM categories WHERE category_code=?',(category_code,)).fetchone()
            if category[1]!=item['category'] or category[2] is not None: raise ValueError('Conflicto de categoria')
            family_code='FAM-'+hashlib.sha256((item['category']+'/'+item['family']).encode()).hexdigest()[:12].upper()
            db.execute("INSERT INTO families(category_id,family_code,name,status) SELECT ?,?,?,'draft' WHERE NOT EXISTS(SELECT 1 FROM families WHERE family_code=?)",(category[0],family_code,item['family'],family_code))
            family=db.execute('SELECT family_id,category_id,name FROM families WHERE family_code=?',(family_code,)).fetchone()
            if family[1:]!=(category[0],item['family']): raise ValueError('Conflicto de familia')
            families[item['family']]=family[0]
            rule_key='name-template:'+family_code
            db.execute("INSERT OR IGNORE INTO standardization_rules(rule_key,version,input_field,condition_json,output_field,proposed_output,status) VALUES(?,?,'family_id',?,'standard_name',?,'draft')",
                       (rule_key,version,json.dumps({'family_id':family[0],'attributes':item['attributes']},ensure_ascii=False),item['template']))
        for m in mappings:
            prior=db.execute('SELECT mapping_id FROM taxonomy_mapping_drafts WHERE source_id=? AND version=? AND field_name=? AND original_value=?',(source[0],version,m['field'],m['original'])).fetchone()
            if prior: continue  # No sobrescribir revisiones humanas.
            family_id=families.get(m['family'])
            eligible=m['status']=='propuesta de equivalencia' and family_id is not None
            rule_id=None
            if eligible:
                key='classification:'+hashlib.sha256(json.dumps([source[0],m['field'],m['original']],ensure_ascii=False).encode()).hexdigest()
                rule_id=db.execute("INSERT INTO standardization_rules(rule_key,version,input_field,condition_json,output_field,proposed_output,status) VALUES(?,?,?,?,'family_id',?,'draft')",
                    (key,version,m['field'],json.dumps({'source_id':source[0],'equals_original':m['original'],'review_required':True},ensure_ascii=False),str(family_id))).lastrowid
            db.execute('INSERT INTO taxonomy_mapping_drafts(source_id,version,field_name,original_value,suggested_family_id,status,evidence_json,rule_id) VALUES(?,?,?,?,?,?,?,?)',
                       (source[0],version,m['field'],m['original'],family_id,'draft' if eligible else 'needs_context',json.dumps({'codes':m['codes'],'examples':m['examples'],'load_id':payload['summary']['load']},ensure_ascii=False),rule_id))
            changed+=1
        if changed:
            db.execute("INSERT INTO audit_events(entity_type,entity_id,action,after_json,actor,reason) VALUES('taxonomy',?,'seed_draft',?,'seed_taxonomy','Borrador autorizado; ninguna asignacion a productos')",(version,json.dumps({'mappings_added':changed})))
        if db.execute('PRAGMA foreign_key_check').fetchall(): raise ValueError('Relaciones invalidas')
    return changed


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--db',default='data/rla_modelo_v4.sqlite3');args=parser.parse_args()
    payload=json.loads(Path('outputs/estandarizacion/propuesta.json').read_text(encoding='utf-8'))
    path=Path(args.db)
    if not path.exists(): raise ValueError('Base migrada inexistente')
    with closing(sqlite3.connect(path)) as db:
        db.execute('PRAGMA foreign_keys=ON')
        backup=Path('data/backups')/('rla_pre_taxonomy_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.sqlite3')
        backup.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(backup)) as copy: db.backup(copy)
        before=list(db.execute('SELECT * FROM master_products ORDER BY master_id'))
        added=seed(db,payload)
        assert seed(db,payload)==0
        assert before==list(db.execute('SELECT * FROM master_products ORDER BY master_id'))
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        result={'backup':str(backup),'mappings_added':added,
                'categories':dict(db.execute('SELECT status,count(*) FROM categories GROUP BY status')),
                'families':dict(db.execute('SELECT status,count(*) FROM families GROUP BY status')),
                'mappings':dict(db.execute('SELECT status,count(*) FROM taxonomy_mapping_drafts GROUP BY status')),
                'rules':dict(db.execute('SELECT status,count(*) FROM standardization_rules GROUP BY status')),
                'products_unchanged':True,'repeat_added':0,'integrity':'ok'}
        Path('outputs/estandarizacion/carga_borrador.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
