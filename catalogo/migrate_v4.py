"""Migración aditiva al modelo relacional v4 (usada al crear una base nueva)."""
import hashlib
import json
from pathlib import Path
import sqlite3

FIELDS=['Availability Group','Report Group','DEPARTMENT','REVENUEGROUP','EXCHANGEGROUP',
        'INVENTORYGROUP','ACCUMULATEDDEPRECIATIONGLCODE','WRITEOFFGLCODE','COGSGROUP','TAXGROUP',
        'DEPRCIATIONGLCODE','DISCOUNTGROUP','SUBRENTGLCODE','SELLGLCODE','Price Group']


def fingerprint(db,table,columns):
    names=','.join('"'+c+'"' for c in columns)
    digest=hashlib.sha256();count=0
    for row in db.execute(f'SELECT {names} FROM "{table}" ORDER BY rowid'):
        digest.update(json.dumps(row,ensure_ascii=False,separators=(',',':')).encode())
        count+=1
    return {'rows':count,'sha256':digest.hexdigest()}


def statements(script):
    current=''
    for line in script.splitlines(True):
        current+=line
        if sqlite3.complete_statement(current):
            yield current;current=''
    if current.strip(): raise ValueError('SQL incompleto')


def apply_migration(db):
    if db.execute('SELECT 1 FROM schema_version WHERE version=4').fetchone(): return False
    db.execute('PRAGMA foreign_keys=ON')
    with db:
        db.execute('BEGIN IMMEDIATE')
        for sql in statements(Path(__file__).with_name('sql').joinpath('004_relational_model.sql').read_text(encoding='utf-8')):
            db.execute(sql)
        labels={}; expected=0
        for raw_id,source_id,payload in db.execute('SELECT r.raw_record_id,l.source_id,r.raw_json FROM raw_records r JOIN loads l USING(load_id)'):
            raw=json.loads(payload)
            for field in FIELDS:
                value=raw.get(field)
                if value is None or not str(value).strip(): continue
                value=str(value);key=(source_id,field,value)
                if key not in labels:
                    labels[key]=db.execute('INSERT INTO classification_values(source_id,field_name,raw_value) VALUES(?,?,?)',key).lastrowid
                db.execute('INSERT INTO record_classifications VALUES(?,?,?)',(raw_id,field,labels[key]))
                expected+=1
        db.execute('INSERT INTO snapshot_classifications SELECT i.snapshot_id,r.field_name,r.value_id FROM inventory_snapshots i JOIN record_classifications r USING(raw_record_id)')
        db.execute('INSERT INTO snapshot_commercial(snapshot_id,cost,replacement_cost,currency_code) SELECT snapshot_id,cost,replacement_cost,currency FROM inventory_snapshots')
        assert db.execute('SELECT count(*) FROM record_classifications').fetchone()[0]==expected
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
        db.execute("INSERT INTO audit_events(entity_type,entity_id,action,after_json,actor,reason) VALUES('schema','4','migration',?,'migrate_v4','Modelo relacional aditivo; conserva compatibilidad y staging')",(json.dumps({'classification_links':expected,'classification_values':len(labels)}),))
    return True
