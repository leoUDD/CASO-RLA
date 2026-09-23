"""Respalda, migra en copia y verifica conservación. No reemplaza la base origen."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
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
        for sql in statements(Path('db/migrations/004_relational_model.sql').read_text(encoding='utf-8')):
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


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=Path('data/rla.sqlite3'))
    parser.add_argument('--target',type=Path,default=Path('data/rla_v4.sqlite3'))
    args=parser.parse_args()
    if args.source.resolve()==args.target.resolve() or args.target.exists():
        raise ValueError('La copia destino debe ser nueva y diferente al origen')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup=Path('data/backups')/f'rla_pre_v4_{stamp}.sqlite3';backup.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(args.source.resolve().as_uri()+'?mode=ro',uri=True)) as source:
        assert source.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        with closing(sqlite3.connect(backup)) as archive: source.backup(archive)
    with closing(sqlite3.connect(backup)) as archive, closing(sqlite3.connect(args.target)) as db:
        archive.backup(db)
        tables=[r[0] for r in archive.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        columns={t:[r[1] for r in archive.execute(f'PRAGMA table_info("{t}")')] for t in tables}
        before={t:fingerprint(archive,t,columns[t]) for t in tables}
        apply_migration(db)
        checks={}
        for t in tables:
            if t in ['schema_version','audit_events']: continue
            checks[t]=before[t]==fingerprint(db,t,columns[t])
        # Tablas append-only: también verificar el prefijo histórico completo.
        for t in ['schema_version','audit_events']:
            original=list(archive.execute(f'SELECT * FROM {t} ORDER BY rowid'))
            copied=list(db.execute(f'SELECT * FROM {t} ORDER BY rowid LIMIT ?',(len(original),)))
            checks[t]=original==copied
        assert all(checks.values()),checks
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert apply_migration(db) is False
        result={'source':str(args.source),'target':str(args.target),'backup':str(backup),
                'preserved_tables':checks,'source_replaced':False,
                'raw_rows':db.execute('SELECT count(*) FROM raw_records').fetchone()[0],
                'normalized_rows':db.execute('SELECT count(*) FROM normalized_records').fetchone()[0],
                'classification_values':db.execute('SELECT count(*) FROM classification_values').fetchone()[0],
                'classification_links':db.execute('SELECT count(*) FROM record_classifications').fetchone()[0],
                'integrity':'ok','foreign_keys':'ok','idempotence':'ok'}
    out=Path('outputs/migracion');out.mkdir(parents=True,exist_ok=True)
    (out/'verificacion_v4.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
