"""Revisión unificada, clasificación conservadora y maestros sin fusiones."""
from collections import Counter
import json,re
from catalogo.import_excel import search_key
from catalogo.std_rules import LABEL_ALIASES

VERSION='catalog-1'
FIELDS=['Report Group','EXCHANGEGROUP','DEPARTMENT','REVENUEGROUP','INVENTORYGROUP','Availability Group']
# Identificadores descriptivos del objeto principal; no busca palabras en cualquier posición.
PATTERNS={
'Micrófonos':r'^MICROFONO\b',
'Altavoces':r'^(ALTAVOZ|ALTAVOCES|PARLANTE|SUBWOOFER|SUB BAJO|SOUNDBAR)\b',
'Consolas de audio':r'^(CONSOLA (?:DE )?AUDIO|MEZCLADOR(?:A)? (?:DE )?AUDIO|POWER MIXER)\b',
'Amplificadores':r'^AMPLIFICADOR (?:DE )?AUDIO\b',
'Procesamiento de audio':r'^(PROCESADOR (?:DE )?AUDIO|CAJA DIRECTA|COMPRESOR (?:DE )?AUDIO|MATRIZ (?:DE )?AUDIO)\b',
'Accesorios de audio':r'^(RECEPTOR.*(?:MICROFONO|MIC\b)|ATRIL (?:DE )?MICROFONO|SOPORTE (?:DE )?PARLANTE|ANTENA.*AUDIO|AUDIFONO)\b',
'Proyectores':r'^(PROYECTOR|VIDEOPROYECTOR)\b',
'Monitores y televisores':r'^(MONITOR|TELEVISOR|TV|PANTALLA TACTIL)\b',
'Pantallas LED':r'^(PANTALLA LED|PANEL LED|MODULO(?:S)? (?:DE )?LED)\b',
'Pantallas de proyección':r'^(TELON|PANTALLA (?:DE )?PROYECCION)\b',
'Cámaras':r'^(CAMARA|VIDEOCAMARA)\b',
'Procesamiento y distribución de video':r'^(?:SWITCHER|ESCALADOR|MATRIZ DE VIDEO|DISTRIBUIDOR (?:DE )?(?:VIDEO|VGA|HDMI|SDI)|(?:CONVERSOR|CONVERTIDOR).*(?:VGA|HDMI|SDI))\b',
'Reproducción de video':r'^REPRODUCTOR (?:DE )?(?:VIDEO|DVD|BLU.?RAY)\b',
'Accesorios de video':r'^(LENTE|SOPORTE (?:DE )?(?:PROYECTOR|PLASMA|LCD|MONITOR)|ADAPTADOR.*(?:VGA|HDMI|SDI))\b',
'Computadores':r'^(NOTEBOOK|LAPTOP|COMPUTADOR|COMPUTADORA|SERVIDOR|CPU)\b',
'Redes':r'^(SWITCH (?:DE )?RED|ROUTER|ACCESS POINT|PUNTO DE ACCESO)\b',
'Impresoras':r'^IMPRESORA\b',
'Periféricos y almacenamiento':r'^(MOUSE|TECLADO|MEMORIA|DISCO DURO|LECTOR DE CODIGO|TABLET)\b',
'Luminarias':r'^(FOCO|LUMINARIA|CABEZA MOVIL|OPTIPAR)\b',
'Control de iluminación':r'^(CONSOLA (?:DE )?ILUMINACION|DIMMER|SPLITTER DMX|CONTROLADOR DMX)\b',
'Accesorios de iluminación':r'^SOPORTE (?:DE )?ILUMINACION\b',
'Distribución eléctrica':r'^(TABLERO ELECTRICO|DISTRIBUIDOR ELECTRICO|DISTRIBUIDOR DE CORRIENTE|CAJA DE DISTRIBUCION|ZAPATILLA(?:S)? (?:ELECTRICA|CHUCO))\b',
'Respaldo y generación':r'^(UPS|GENERADOR)\b',
'Interpretación simultánea':r'^(RECEPTOR (?:DE )?TRADUCCION|PUPITRE (?:DE )?INTERPRETE|CABINA (?:DE )?(?:TRADUCCION|INTERPRETACION))\b',
'Debate y votación':r'^(MICROFONO.*DEBATE|UNIDAD (?:DE )?(?:DEBATE|VOTACION)|SISTEMA DE VOTACION)\b',
'Conferencia e intercomunicación':r'^(INTERCOMUNICADOR|RADIO PORTATIL|TELEFONO (?:DE )?CONFERENCIA|SISTEMA (?:DE )?VIDEOCONFERENCIA)\b',
'Cables y adaptadores':r'^(CABLE|CHICOTE|EXTENSION|CORDON|COPLA|ADAPTADOR)\b',
'Estructuras y montaje':r'^(TRUSS|ESTRUCTURA|TORRE DE ELEVACION|BASE DE PISO)\b',
'Transporte y protección de equipos':r'^(CASE|FLIGHT CASE|BOLSO)\b',
'Mobiliario y oficina':r'^(MESA|SILLA|PAPELOGRAFO|PODIO)\b',
'Consumibles y repuestos':r'^(TINTA|TONER|REPUESTO|PILA|BATERIA)\b',
'Servicios técnicos':r'^(SERVICIO TECNICO|CONFIGURACION (?:DE )?REDES|EDICION (?:DE )?VIDEO)\b',
'Personal':r'^(OPERADOR|TECNICO|INTERPRETE|PERSONAL)\b',
'Transporte y viajes':r'^(TRANSPORTE|VIAJE)\b',
'Licencias':r'^LICENCIA\b',
'Gastos y cargos':r'^(COMISION|ALOJAMIENTO|ALIMENTACION|IMPREVISTOS)\b'}

PLACEHOLDERS={'NA','N/A','NULL','NONE','S/N','SIN DATO','-','GENERICO','GENERICA'}


def identity(value):
    key=search_key(value or '')
    return '' if key in PLACEHOLDERS else key


def products(connection,load_id):
    """Un registro por código de la carga, con sus filas de origen y claves de comparación."""
    found={}
    for excel_row,status,payload in connection.execute('SELECT r.excel_row,r.validation_status,n.normalized_json FROM raw_records r JOIN normalized_records n USING(raw_record_id) WHERE r.load_id=? ORDER BY r.excel_row',(load_id,)):
        n=json.loads(payload)
        code=n.get('Product ID')
        if not code:continue
        if code not in found:
            found[code]=dict(n,code=code,rows=[],quarantined=False)
        p=found[code]
        p['rows'].append(excel_row)
        p['quarantined']|=status=='quarantined'
        for field,value in n.items():
            if not p.get(field) and value is not None:p[field]=value
    for p in found.values():
        p['description_key']=search_key(p.get('Description') or '')
        p['brand']=identity(p.get('MANUFACTURER'))
        p['model']=identity(p.get('MODEL'))
    return found

def review(p,aliases):
    evidence=[{'field':f,'value':p.get(f)} for f in FIELDS]
    specific={aliases[search_key(p[f])] for f in ['Report Group','EXCHANGEGROUP','INVENTORYGROUP'] if p.get(f) and search_key(p[f]) in aliases}
    lexical={family for family,pattern in PATTERNS.items() if re.search(pattern,p['description_key'])}
    # Una descripción específica de debate prevalece como propuesta sobre micrófono genérico.
    if 'Debate y votación' in lexical:lexical.discard('Micrófonos')
    family=None; reason='Sin evidencia suficiente'; status='pending'
    if p['quarantined']:return dict(family=None,status='quarantined',reason='Validacion de origen pendiente',evidence=evidence,lexical=sorted(lexical),groups=sorted(specific))
    if len(specific)==1 and len(lexical)==1 and specific==lexical:
        family=next(iter(specific));reason='Objeto principal y etiqueta especifica coinciden'
        status='approved_by_rule'
    elif len(lexical)==1:
        family=next(iter(lexical));reason='Descripcion sugiere familia; etiquetas ausentes o distintas'
    elif len(specific)==1:
        family=next(iter(specific));reason='Solo etiqueta: descripcion requiere revision'
    else:reason='Evidencias ambiguas o contradictorias'
    if p.get('Package')=='PACKAGE':status='pending';reason+='; validar composicion del paquete'
    if re.search(r'PROBAR|NO USAR|FICHA MALA|DEFAULT|ITEM MISSING',p['description_key']):status='pending';reason+='; advertencia operacional'
    if p.get('Type')!='ITEM':status='pending';reason+='; validar tipo de servicio/repuesto/cargo'
    return dict(family=family,status=status,reason=reason,evidence=evidence,lexical=sorted(lexical),groups=sorted(specific))

def build(db,load_id):
    aliases={search_key(a):f for f,values in LABEL_ALIASES.items() for a in values}
    items=products(db,load_id)
    source=db.execute('SELECT source_id FROM loads WHERE load_id=?',(load_id,)).fetchone()[0]
    families={name:(fid,cat,cname) for fid,name,cat,cname in db.execute('SELECT f.family_id,f.name,c.category_id,c.name FROM families f JOIN categories c USING(category_id)')}
    previous={}
    # Recuperar historia desde SQLite, sin depender de informes que puedan estar desactualizados.
    for payload,value,target,version in db.execute("SELECT r.raw_json,p.proposed_value,p.target_field,s.version FROM field_standardization_proposals p JOIN raw_records r USING(raw_record_id) JOIN standardization_rules s USING(rule_id) WHERE r.load_id=? AND s.version IN ('conditional-1','context-1') ORDER BY CASE s.version WHEN 'conditional-1' THEN 0 ELSE 1 END",(load_id,)):
        code=json.loads(payload).get('Product ID');previous.setdefault(code,[]).append({'version':version,'value':value,'field':target})
    rows=[];new_masters=0;new_reviews=0
    with db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('''CREATE TABLE IF NOT EXISTS unified_catalog_reviews(
          load_id INTEGER NOT NULL REFERENCES loads,legacy_id INTEGER NOT NULL REFERENCES legacy_products,
          version TEXT NOT NULL,master_id INTEGER REFERENCES master_products,family_id INTEGER REFERENCES families,
          status TEXT NOT NULL CHECK(status IN ('pending','approved_by_rule','approved_by_reviewer','rejected','quarantined')),
          evidence_json TEXT NOT NULL CHECK(json_valid(evidence_json)),reason TEXT NOT NULL,
          PRIMARY KEY(load_id,legacy_id,version))''')
        for code,p in items.items():
            decision=review(p,aliases)
            history=previous.get(code,[])
            if decision['status']=='pending' and history:
                latest=history[-1]
                if latest['field']=='family_id' and latest['value']:
                    name=db.execute('SELECT name FROM families WHERE family_id=?',(latest['value'],)).fetchone()
                    if name:
                        decision['family']=name[0]
                        decision['reason']='Propuesta previa mas reciente conservada ('+latest['version']+'); no cumple aprobacion automatica'
                elif latest['field']=='category_id':
                    decision['family']=None
                    decision['reason']='Revision previa permite solo categoria; familia pendiente'
            legacy=db.execute('SELECT legacy_id FROM legacy_products WHERE source_id=? AND legacy_code=?',(source,code)).fetchone()
            if legacy:legacy_id=legacy[0]
            else:legacy_id=db.execute('INSERT INTO legacy_products(source_id,legacy_code) VALUES(?,?)',(source,code)).lastrowid
            mapping=db.execute('SELECT master_id FROM product_mappings WHERE legacy_id=?',(legacy_id,)).fetchone()
            mid=mapping[0] if mapping else None
            if mid is None and not p['quarantined']:
                # Nombre limpio provisional; no afirmar nomenclatura técnica final.
                mid=db.execute("INSERT INTO master_products(standard_name,product_type,model,package_type,serialization,origin,created_by,creation_reason) VALUES(?,?,?,?,?,'import','catalog_builder','Un maestro por codigo original; nombre provisional; sin fusion')",(p['Description'],p['Type'],p.get('MODEL'),p.get('Package'),p.get('ITEMCATEGORY'))).lastrowid
                db.execute("INSERT INTO product_mappings(legacy_id,master_id,method,reason,decided_by) VALUES(?,?,'initial','Identidad inicial por codigo de origen','catalog_builder')",(legacy_id,mid))
                db.execute("INSERT INTO audit_events(entity_type,entity_id,action,after_json,actor,reason) VALUES('master_product',?,'create',?,'catalog_builder','Alta inicial sin fusion')",(str(mid),json.dumps({'legacy_id':legacy_id,'code':code})))
                new_masters+=1
            fid=families[decision['family']][0] if decision['family'] else None
            old=db.execute('SELECT status,family_id,reason FROM unified_catalog_reviews WHERE load_id=? AND legacy_id=? AND version=?',(load_id,legacy_id,VERSION)).fetchone()
            if old:decision['status'],fid,decision['reason']=old
            else:
                if decision['status']=='approved_by_rule' and mid:
                    current=db.execute('SELECT family_id,origin FROM master_products WHERE master_id=?',(mid,)).fetchone()
                    # Maestro previo/manual o equivalencia revisada no se sobreescribe.
                    if mapping or current[1]=='manual':
                        decision['status']='pending';decision['reason']+='; maestro existente requiere aprobacion explicita'
                    else:
                        db.execute('UPDATE master_products SET family_id=? WHERE master_id=?',(fid,mid))
                        db.execute("INSERT INTO audit_events(entity_type,entity_id,action,after_json,actor,reason) VALUES('master_product',?,'classify_by_rule',?,'rule:catalog-1',?)",(str(mid),json.dumps({'family_id':fid}),decision['reason']))
                db.execute('INSERT INTO unified_catalog_reviews VALUES(?,?,?,?,?,?,?,?)',(load_id,legacy_id,VERSION,mid,fid,decision['status'],json.dumps(decision,ensure_ascii=False),decision['reason']))
                new_reviews+=1
            if fid:
                family_name,category=db.execute('SELECT f.name,c.name FROM families f JOIN categories c USING(category_id) WHERE family_id=?',(fid,)).fetchone()
            else:
                family_name=category=None
                if history and history[-1]['field']=='category_id' and history[-1]['value']:
                    catrow=db.execute('SELECT name FROM categories WHERE category_id=?',(history[-1]['value'],)).fetchone()
                    if catrow:category=catrow[0]
            master_code=db.execute('SELECT master_code FROM master_products WHERE master_id=?',(mid,)).fetchone()[0] if mid else None
            rows.append(dict(code=code,master_code=master_code,description=p['Description'],row=p['rows'][0],family=family_name,category=category,status=decision['status'],reason=decision['reason'],evidence=decision['evidence'],history=previous.get(code,[])))
        # Familias usadas por reglas aprobadas quedan activas; las demás conservan el borrador.
        db.execute("UPDATE families SET status='approved' WHERE family_id IN (SELECT family_id FROM unified_catalog_reviews WHERE status='approved_by_rule') AND status='draft'")
        db.execute("UPDATE categories SET status='approved' WHERE category_id IN (SELECT category_id FROM families WHERE status='approved') AND status='draft'")
        if db.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('Error de integridad referencial')
    return rows,{'codes':len(rows),'status':dict(Counter(r['status'] for r in rows)),'new_masters':new_masters,'new_reviews':new_reviews,'version':VERSION,'load_id':load_id}
