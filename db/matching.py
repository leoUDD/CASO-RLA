"""Candidatos explicables en staging. Ninguna coincidencia ejecuta una fusión."""
import argparse
from collections import defaultdict, Counter
from difflib import SequenceMatcher
from itertools import combinations
import json
import re
import sqlite3
from pathlib import Path
from db.import_excel import search_key

VERSION = '1.0'
PLACEHOLDERS = {'NA','N/A','NULL','NONE','S/N','SIN DATO','-','GENERICO','GENERICA'}
STOP = {'DE','DEL','LA','EL','LOS','LAS','CON','PARA','Y','EN','UN','UNA','POR'}


def identity(value):
    key = search_key(value or '')
    return '' if key in PLACEHOLDERS else key


def numeric_signature(description):
    # Señal conservadora, no equivalencia dimensional: 1 m y 100 cm requieren revisión.
    return sorted(set(re.findall(r'\d+(?:[.,]\d+)?',description.replace(',','.'))))


def compare(a,b,scorer=None):
    da,db = a['description_key'],b['description_key']
    similarity = round(scorer(da,db) if scorer else 100*SequenceMatcher(None,da,db,autojunk=False).ratio(),1)
    reasons, differences = [], []
    if a['brand'] and a['brand']==b['brand'] and a['model'] and a['model']==b['model']:
        reasons.append('Fabricante y modelo coinciden')
    if da and da==db:
        reasons.append('Descripcion normalizada exacta')
    if similarity>=80:
        reasons.append(f'Similitud textual {similarity}/100 (no es probabilidad)')
    for field,label in [('brand','fabricante'),('model','modelo'),('Type','tipo'),('Package','paquete'),('ITEMCATEGORY','serializacion')]:
        if a.get(field) and b.get(field) and a[field]!=b[field]:
            differences.append('Diferente '+label)
    if numeric_signature(da)!=numeric_signature(db):
        differences.append('Numeros o medidas diferentes en descripcion')
    for pattern,label in [(r'\bCLASE\s+B\b','clase B'),(r'METRO CUADRADO|\bM2\b','unidad por metro cuadrado'),(r'\bKIT\b|\bPACK\b|\bSET\b','kit o conjunto')]:
        if bool(re.search(pattern,da))!=bool(re.search(pattern,db)):
            differences.append('Diferente indicacion de '+label)
    if any(re.search(r'NO USAR|FICHA MALA|SYSTEM DEFAULT|DEFAULTITEM|DEFAULTLABOR|DEFAULTMISC',s) for s in [da,db]):
        differences.append('Descripcion contiene advertencia de uso o registro de sistema')
    if a['quarantined'] or b['quarantined']:
        differences.append('Incluye registro en cuarentena')
    strong = bool(a['brand'] and a['brand']==b['brand'] and a['model'] and a['model']==b['model'])
    status = 'diferencias relevantes' if differences else ('coincidencia fuerte' if strong else 'revision por descripcion')
    return {'code_a':a['code'],'code_b':b['code'],'description_a':a['Description'],
            'description_b':b['Description'],'brand_a':a['brand'],'brand_b':b['brand'],
            'model_a':a['model'],'model_b':b['model'],'similarity':similarity,
            'priority':status,'reasons':reasons,'differences':differences,
            'rows_a':a['rows'],'rows_b':b['rows']}


def products(connection,load_id):
    found = {}
    for excel_row,status,payload in connection.execute('SELECT r.excel_row,r.validation_status,n.normalized_json FROM raw_records r JOIN normalized_records n USING(raw_record_id) WHERE r.load_id=? ORDER BY r.excel_row',(load_id,)):
        n = json.loads(payload)
        code = n.get('Product ID')
        if not code: continue
        if code not in found:
            found[code] = dict(n,code=code,rows=[],quarantined=False)
        p = found[code]
        p['rows'].append(excel_row)
        p['quarantined'] |= status=='quarantined'
        for field,value in n.items():
            if not p.get(field) and value is not None: p[field]=value
    for p in found.values():
        p['description_key']=search_key(p.get('Description') or '')
        p['brand']=identity(p.get('MANUFACTURER'))
        p['model']=identity(p.get('MODEL'))
    return found


def candidate_pairs(items):
    brands,descriptions,tokens = defaultdict(list),defaultdict(list),defaultdict(list)
    for code,p in items.items():
        if p['brand'] and p['model']: brands[(p['brand'],p['model'])].append(code)
        if p['description_key']: descriptions[p['description_key']].append(code)
        for word in set(re.findall(r'[A-Z0-9]+',p['description_key']))-STOP:
            if len(word)>=3 and not word.isdigit(): tokens[word].append(code)
    pairs=set()
    for group in list(brands.values())+list(descriptions.values()):
        pairs.update(tuple(sorted(pair)) for pair in combinations(group,2))
    exact_pairs=set(pairs)
    # Bloqueo por palabras poco frecuentes para no comparar todos contra todos.
    for group in tokens.values():
        if 2<=len(group)<=60:
            for x,y in combinations(group,2):
                a,b=items[x],items[y]
                if a.get('Type')!=b.get('Type'): continue
                if a['brand'] and b['brand'] and a['brand']!=b['brand']: continue
                if a['model'] and b['model'] and a['model']!=b['model']: continue
                pairs.add(tuple(sorted((x,y))))
    return pairs,exact_pairs,{'pairs_compared':len(pairs),'brand_model_groups':sum(len(g)>1 for g in brands.values()),
                   'exact_description_groups':sum(len(g)>1 for g in descriptions.values()),
                   'token_max_frequency':60,'text_threshold':80}


def candidates(items,scorer=None):
    pairs,exact_pairs,coverage=candidate_pairs(items)
    result=[]
    for x,y in sorted(pairs):
        candidate=compare(items[x],items[y],scorer)
        if (x,y) in exact_pairs or candidate['similarity']>=80:
            result.append(candidate)
    return result,coverage


def save_decision(connection,source_id,a,b,decision,reason,actor):
    a,b=sorted([a,b])
    if a==b or not reason.strip() or not actor.strip(): raise ValueError('Par, autor y motivo obligatorios')
    for code in [a,b]:
        exists=connection.execute("SELECT 1 FROM normalized_records n JOIN raw_records r USING(raw_record_id) JOIN loads l USING(load_id) WHERE l.source_id=? AND json_extract(n.normalized_json,'$.\"Product ID\"')=? LIMIT 1",(source_id,code)).fetchone()
        if not exists: raise ValueError('Codigo no encontrado en la fuente: '+code)
    previous=connection.execute('SELECT decision,reason,actor FROM candidate_reviews WHERE source_id=? AND code_a=? AND code_b=?',(source_id,a,b)).fetchone()
    with connection:
        connection.execute("INSERT INTO candidate_reviews(source_id,code_a,code_b,decision,reason,actor) VALUES(?,?,?,?,?,?) ON CONFLICT(source_id,code_a,code_b) DO UPDATE SET decision=excluded.decision,reason=excluded.reason,actor=excluded.actor,updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')",(source_id,a,b,decision,reason,actor))
        connection.execute("INSERT INTO audit_events(entity_type,entity_id,action,before_json,after_json,actor,reason) VALUES('candidate_review',?,'decision',?,?,?,?)",(json.dumps([source_id,a,b]),json.dumps(previous),json.dumps({'decision':decision}),actor,reason))


def report(connection,load_id,out):
    source=connection.execute('SELECT source_id,filename FROM loads WHERE load_id=?',(load_id,)).fetchone()
    if not source: raise ValueError('Carga inexistente')
    items=products(connection,load_id)
    results,coverage=candidates(items)
    decisions={(a,b):(d,r) for a,b,d,r in connection.execute('SELECT code_a,code_b,decision,reason FROM candidate_reviews WHERE source_id=?',(source[0],))}
    for c in results:
        c['decision'],c['decision_reason']=decisions.get((c['code_a'],c['code_b']),('pending',''))
    rank={'coincidencia fuerte':0,'revision por descripcion':1,'diferencias relevantes':2}
    results.sort(key=lambda c:(c['decision']!='pending',rank[c['priority']],-c['similarity'],c['code_a'],c['code_b']))
    system=[{'code':p['code'],'description':p.get('Description'),'rows':p['rows'],'type':p.get('Type'),
             'site':p.get('SITEID'),'stock':p.get('Stock'),'proposal':'Conservar en origen y solicitar clasificacion como plantilla de sistema; no inventar sitio ni excluir sin aprobacion.'}
            for p in items.values() if p['quarantined']]
    payload={'load_id':load_id,'source':source[1],'rules_version':VERSION,'products':len(items),'pairs':len(results),
             'by_priority':dict(Counter(c['priority'] for c in results)),'coverage':coverage,
             'limitations':['Bloqueo por palabras: no garantiza encontrar todos los duplicados.',
                            'Puntaje textual no calibrado; no representa probabilidad.',
                            'Numeros distintos son una alerta, no prueba de productos diferentes.',
                            'No se ejecutan fusiones. Categorias originales no se usan como verdad.',
                            'Decisiones guardadas se conservan por fuente y par; revisar nuevamente si cambia la identidad.'],
             'candidates':results,'quarantined_products':system}
    out.mkdir(parents=True,exist_ok=True)
    (out/'candidatos.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    embedded=json.dumps(payload,ensure_ascii=False).replace('<','\\u003c')
    template=Path(__file__).with_name('matching_report.html').read_text(encoding='utf-8')
    (out/'revision.html').write_text(template.replace('/*DATA*/',embedded),encoding='utf-8')
    print(json.dumps({k:v for k,v in payload.items() if k!='candidates'},ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--db',default='data/rla.sqlite3')
    parser.add_argument('--load',type=int,default=1)
    parser.add_argument('--output',type=Path,default=Path('outputs/duplicados'))
    parser.add_argument('--decision',choices=['equivalent','separate','pending'])
    parser.add_argument('--codes',nargs=2)
    parser.add_argument('--reason')
    parser.add_argument('--actor')
    args=parser.parse_args()
    connection=sqlite3.connect(args.db)
    try:
        connection.execute('PRAGMA foreign_keys=ON')
        connection.executescript(Path(__file__).with_name('migrations').joinpath('003_candidate_reviews.sql').read_text(encoding='utf-8'))
        if args.decision:
            if not args.codes or not args.reason or not args.actor: parser.error('Decision requiere codes, reason y actor')
            source=connection.execute('SELECT source_id FROM loads WHERE load_id=?',(args.load,)).fetchone()
            if not source: raise ValueError('Carga inexistente')
            save_decision(connection,source[0],*args.codes,args.decision,args.reason,args.actor)
        report(connection,args.load,args.output)
    finally: connection.close()

