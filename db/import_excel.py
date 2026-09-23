"""Importa a staging; nunca publica una fotografía ni fusiona productos."""
import argparse
from collections import Counter, defaultdict
from contextlib import closing
from decimal import Decimal
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import sqlite3
import unicodedata

import pandas as pd

RULES_VERSION = '1.0'
REQUIRED = ['Product ID','Description','Type','ITEMCATEGORY','Package','SITEID','SITENAME',
            'MANUFACTURER','MODEL','Stock','Cost','Replacement Cost','CANRENT','CANSELL','CANSUBRENT']
NUMBERS = ['Stock','Cost','Replacement Cost','CostoTotal','RETAILPRICE','LOWRETAILPRICE',
           'MAXIMUMQTY','MINIMUMQTY','MSRP','REORDERQTY']
ENUMS = {'Type': {'ITEM','MISCCHARGE','LABOR','PARTS'}, 'Package':{'ITEM','PACKAGE'},
         'ITEMCATEGORY':{'SERIAL','NONSERIAL'}}
FLAGS = {'CANRENT':{'RENTABLE':1,'NOTRENTABLE':0},'CANSELL':{'SELLABLE':1,'NOTSELLABLE':0},
         'CANSUBRENT':{'SUBRENT':1,'NOTSUBRENT':0}}


def clean(value):
    return ' '.join(str(value).split()) if value is not None else ''


def search_key(value):
    return ''.join(c for c in unicodedata.normalize('NFKD',clean(value).upper())
                   if not unicodedata.combining(c))


def decimal_text(value):
    s = str(value).strip()
    if not s:
        return None
    if re.fullmatch(r'[+-]?\d+',s):
        return format(Decimal(s),'f')
    if re.fullmatch(r'[+-]?\d+[,.]\d+',s):
        if len(re.split('[,.]',s)[-1]) == 3:
            raise ValueError('Separador decimal o de miles ambiguo')
        return format(Decimal(s.replace(',','.')),'f')
    if re.fullmatch(r'[+-]?\d{1,3}(?:\.\d{3})+,\d+',s):
        return format(Decimal(s.replace('.','').replace(',','.')),'f')
    if re.fullmatch(r'[+-]?\d{1,3}(?:,\d{3})+\.\d+',s):
        return format(Decimal(s.replace(',','')),'f')
    raise ValueError('Formato numerico no reconocido')


def normalize(raw):
    result = {k:clean(v) or None for k,v in raw.items()}
    issues = []
    def issue(severity,field,code,message):
        issues.append((severity,field,code,message))
    for field in ['Product ID','SITEID','Description','SITENAME']:
        if not result.get(field):
            issue('error',field,'required_value','Falta un valor obligatorio')
    if result.get('Product ID') == '0':
        issue('warning','Product ID','zero_code','Codigo cero: requiere revision, se conserva')
    for field in ['Description','MANUFACTURER','MODEL']:
        result[field+'_search'] = search_key(raw.get(field,'')) or None
    for field in ['MANUFACTURER','MODEL']:
        if not result.get(field):
            issue('warning',field,'missing_identity','Dato de identidad ausente; no se infiere')
        elif search_key(result[field]) in {'NA','N/A','NULL','NONE','S/N','SIN DATO','-'}:
            issue('warning',field,'possible_placeholder','Posible marcador de ausencia; se conserva')
    for field, allowed in ENUMS.items():
        value = clean(raw.get(field,'')).upper()
        result[field] = value or None
        if value not in allowed:
            issue('error',field,'invalid_enum','Valor obligatorio fuera del dominio permitido')
    for field, mapping in FLAGS.items():
        value = clean(raw.get(field,'')).upper()
        result[field] = mapping.get(value)
        if value not in mapping:
            issue('error',field,'invalid_flag','Condicion operativa no reconocida')
    for field in NUMBERS:
        if field not in raw:
            continue
        try:
            result[field] = decimal_text(raw[field])
            if result[field] is not None and Decimal(result[field]) < 0:
                issue('warning',field,'negative_value','Valor negativo: conservar y revisar significado')
        except ValueError as exc:
            result[field] = None
            issue('error',field,'invalid_number',str(exc))
    return result, issues


def connect(path):
    from db.init_db import initialize
    from db.migrate_v4 import apply_migration
    existed = Path(path).exists()
    if existed:
        with closing(sqlite3.connect(path)) as check:
            if not check.execute('SELECT 1 FROM schema_version WHERE version=4').fetchone():
                raise ValueError('La importacion requiere v4. Migrar en copia con db.migrate_v4 antes de importar.')
    initialize(path)
    connection = sqlite3.connect(path)
    connection.execute('PRAGMA foreign_keys=ON')
    connection.executescript(Path(__file__).with_name('migrations').joinpath('002_normalization.sql').read_text(encoding='utf-8'))
    connection.executescript(Path(__file__).with_name('migrations').joinpath('003_candidate_reviews.sql').read_text(encoding='utf-8'))
    if not existed:
        apply_migration(connection)
    return connection


def summary(connection,load_id,repeated=False):
    row = connection.execute('SELECT filename,row_count,status FROM loads WHERE load_id=?',(load_id,)).fetchone()
    counts = dict(connection.execute('SELECT validation_status,count(*) FROM raw_records WHERE load_id=? GROUP BY validation_status',(load_id,)))
    errors = connection.execute("SELECT count(*) FROM validation_issues WHERE load_id=? AND severity='error'",(load_id,)).fetchone()[0]
    issues = [dict(zip(['severity','field','code','count'],r)) for r in connection.execute(
        'SELECT severity,field,code,count(*) FROM validation_issues WHERE load_id=? GROUP BY severity,field,code ORDER BY severity,field,code',(load_id,))]
    return {'load_id':load_id,'file':row[0],'rows':row[1],'status':row[2], 'repeated':repeated,
            'row_status':counts,'blocking_issues':errors,'ready_for_publication':errors==0 and row[1]>0,
            'published':connection.execute('SELECT 1 FROM active_loads WHERE load_id=?',(load_id,)).fetchone() is not None,
            'issues':issues,'rules_version':RULES_VERSION,
            'classification_links':connection.execute('SELECT count(*) FROM record_classifications c JOIN raw_records r USING(raw_record_id) WHERE r.load_id=?',(load_id,)).fetchone()[0]}


def stage_frame(connection, frame, source, filename, digest, sheet_name=None):
    if not source.strip():
        raise ValueError('La fuente no puede estar vacia')
    with connection:
        connection.execute('INSERT OR IGNORE INTO sources(name) VALUES(?)',(source,))
        source_id = connection.execute('SELECT source_id FROM sources WHERE name=?',(source,)).fetchone()[0]
        previous = connection.execute('SELECT load_id FROM loads WHERE source_id=? AND sha256=?',(source_id,digest)).fetchone()
        if previous:
            return summary(connection,previous[0],True)
        load_id = connection.execute('INSERT INTO loads(source_id,filename,sha256,row_count) VALUES(?,?,?,?)',
                                     (source_id,filename,digest,len(frame))).lastrowid
        connection.execute('UPDATE loads SET sheet_name=?,importer_version=? WHERE load_id=?',
                           (sheet_name,'2.0-relational',load_id))
        from db.migrate_v4 import FIELDS
        labels = {(field,value):value_id for value_id,field,value in connection.execute(
            'SELECT value_id,field_name,raw_value FROM classification_values WHERE source_id=?',(source_id,))}
        missing = [c for c in REQUIRED if c not in frame.columns]
        global_issues = [('error',c,'missing_column','Columna requerida ausente') for c in missing]
        if frame.empty:
            global_issues.append(('error','archivo','empty_file','No se publica una fotografia vacia automaticamente'))
        rows = []
        for index, raw in enumerate(frame.fillna('').astype(str).to_dict('records'),2):
            norm, problems = normalize(raw)
            rows.append([index,raw,norm,problems])
        keys = Counter((r[2].get('Product ID'),r[2].get('SITEID')) for r in rows)
        attrs = ['Description','MANUFACTURER','MODEL','Type','Package','ITEMCATEGORY']
        by_code = defaultdict(lambda:defaultdict(set))
        site_names = defaultdict(set)
        for _,_,norm,_ in rows:
            code = norm.get('Product ID')
            if code:
                for field in attrs:
                    if norm.get(field):
                        by_code[code][field].add(norm[field])
            if norm.get('SITEID') and norm.get('SITENAME'):
                site_names[norm['SITEID']].add(norm['SITENAME'])
        for index,raw,norm,problems in rows:
            key = (norm.get('Product ID'),norm.get('SITEID'))
            if keys[key]>1:
                problems.append(('error','Product ID + SITEID','duplicate_key','Clave repetida dentro del archivo; ninguna fila se descarta'))
            for field in attrs:
                if len(by_code.get(key[0],{}).get(field,set()))>1:
                    problems.append(('error',field,'conflicting_identity','Un codigo tiene varios valores de identidad'))
            if len(site_names.get(key[1],set()))>1:
                problems.append(('error','SITENAME','conflicting_site','Un sitio tiene nombres distintos'))
            quarantined = bool(missing) or any(p[0]=='error' for p in problems)
            raw_id = connection.execute('INSERT INTO raw_records(load_id,excel_row,raw_json,validation_status,validation_reason) VALUES(?,?,?,?,?)',
                (load_id,index,json.dumps(raw,ensure_ascii=False),'quarantined' if quarantined else 'accepted',
                 json.dumps(problems,ensure_ascii=False))).lastrowid
            connection.execute('INSERT INTO normalized_records VALUES(?,?,?)',(raw_id,json.dumps(norm,ensure_ascii=False),RULES_VERSION))
            for field in FIELDS:
                value=raw.get(field)
                if value is None or not str(value).strip():
                    continue
                value=str(value)
                key=(field,value)
                if key not in labels:
                    labels[key]=connection.execute('INSERT INTO classification_values(source_id,field_name,raw_value) VALUES(?,?,?)',
                                                   (source_id,field,value)).lastrowid
                connection.execute('INSERT INTO record_classifications(raw_record_id,field_name,value_id) VALUES(?,?,?)',
                                   (raw_id,field,labels[key]))
            connection.executemany('INSERT INTO validation_issues(load_id,raw_record_id,severity,field,code,message) VALUES(?,?,?,?,?,?)',
                                   [(load_id,raw_id,*p) for p in problems])
        connection.executemany('INSERT INTO validation_issues(load_id,raw_record_id,severity,field,code,message) VALUES(?,NULL,?,?,?,?)',
                               [(load_id,*p) for p in global_issues])
        report = summary(connection,load_id)
        connection.execute('UPDATE loads SET validation_notes=? WHERE load_id=?',(json.dumps(report,ensure_ascii=False),load_id))
        connection.execute("INSERT INTO audit_events(entity_type,entity_id,action,after_json,actor,reason) VALUES('load',?,'stage',?,'importador','Importacion y normalizacion; sin publicacion')",
                           (str(load_id),json.dumps(report,ensure_ascii=False)))
    return report


def import_excel(path, db, source='RLA_Productos'):
    path = Path(path)
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    connection = connect(db)
    try:
        existing = connection.execute('SELECT l.load_id FROM loads l JOIN sources s USING(source_id) WHERE s.name=? AND l.sha256=?',(source,digest)).fetchone()
        if existing:
            return summary(connection,existing[0],True)
        with pd.ExcelFile(BytesIO(content)) as book:
            if 'Lista de productos' not in book.sheet_names:
                raise ValueError('No se encuentra la hoja Lista de productos; no se elige otra automaticamente')
            frame = pd.read_excel(book,sheet_name='Lista de productos',dtype=str,keep_default_na=False)
        return stage_frame(connection,frame,source,path.name,digest,'Lista de productos')
    finally:
        connection.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input',required=True)
    parser.add_argument('--db',default='data/rla_modelo_v4.sqlite3')
    parser.add_argument('--source',default='RLA_Productos')
    parser.add_argument('--report',default='outputs/importacion/resultado.json')
    args = parser.parse_args()
    result = import_excel(args.input,args.db,args.source)
    target = Path(args.report)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
