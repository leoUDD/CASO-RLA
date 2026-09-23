"""Propuestas condicionadas: no aprueba ni modifica maestros."""
from collections import Counter
from contextlib import closing
from datetime import datetime,timezone
import html
import json
from pathlib import Path
import re
import sqlite3
from db.matching import products

VERSION='conditional-1'
TARGETS={'Cables y adaptadores','Micrófonos','Proyectores'}


def classify(p,groups):
    text=p['description_key']; package=p.get('Package')=='PACKAGE'
    def result(family,reason):return {'family':family,'reason':reason,'status':'propuesta' if family else 'pendiente'}
    if p['quarantined']:return result(None,'Registro con incidencias de validacion')
    if len(groups)!=1:return result(None,'Etiquetas de entrada apuntan a familias distintas')
    if re.search(r'NO USAR|PROBAR|FICHA MALA',text):return result(None,'Advertencia operacional en la descripcion')
    if p.get('Type')!='ITEM':return result(None,'Tipo distinto de ITEM: revisar naturaleza del registro')
    group=next(iter(groups))
    if group=='Cables y adaptadores':
        if re.search(r'DISTRIBU\w*.*(?:ELECTRIC|CORRIENTE)|CAJA DE DISTRIBUCION',text):
            return result(None,'Distribucion electrica: revisar Energia / Distribucion electrica') if package else result('Distribución eléctrica','La descripcion identifica distribucion electrica, no cable')
        if re.search(r'CAJA REMOTA|STAGE\s?BOX|CONVERSOR|CONVERTIDOR|DISTRIBUIDOR|SPLITTER',text):return result(None,'Equipo activo o funcion distinta: requiere validacion tecnica')
        if package:return result(None,'Paquete: validar composicion antes de asignar familia')
        if re.match(r'^(?:CABLE\b|ADAPTADOR\b|MULTIPAR\b)',text):return result('Cables y adaptadores','Descripcion inicia con cable, adaptador o multipar; sin exclusiones detectadas')
        return result(None,'Descripcion insuficiente para confirmar cable o adaptador')
    if group=='Micrófonos':
        if re.search(r'CAPSULA',text):return result(None,'Capsula: confirmar microfono funcional o componente')
        if package:
            if re.match(r'^MICROFONO\b',text) and not re.search(r'DEBATE|INTERPRETACION',text):return result('Micrófonos','Conjunto de microfono; conservar PACKAGE y revisar componentes')
            return result(None,'Paquete de audio de composicion no confirmada')
        if re.match(r'^(?:RECEPTOR|TRANSMISOR|ANTENA|BASE|SOPORTE|CABLE)\b',text):return result('Accesorios de audio','Descripcion identifica un componente separado del microfono')
        if re.search(r'DEBATE|INTERPRETACION',text):return result(None,'Funcion de debate/interpretacion puede determinar otra familia')
        if re.match(r'^MICROFONO\b',text):return result('Micrófonos','Descripcion identifica microfono individual')
        return result(None,'Descripcion insuficiente para confirmar microfono')
    if re.search(r'LENTE|SOPORTE|LAMPARA',text):
        if re.match(r'^(?:LENTE|SOPORTE|LAMPARA)\b',text) and not package:return result('Accesorios de video','Descripcion identifica accesorio; conservar compatibilidad observada')
        return result(None,'Accesorio o equipo con accesorio: revisar alcance')
    if package or re.search(r'SISTEMA',text):return result(None,'Sistema/paquete de proyeccion: revisar composicion')
    if re.match(r'^PROYECTOR\b',text):return result('Proyectores','Descripcion identifica proyector individual')
    return result(None,'Descripcion insuficiente para confirmar proyector')


def main():
    proposal=json.loads(Path('outputs/estandarizacion/propuesta.json').read_text(encoding='utf-8'))
    aliases={(m['field'],m['original']):m['family'] for m in proposal['mappings'] if m['family'] in TARGETS and m['status']=='propuesta de equivalencia'}
    path=Path('data/rla_modelo_v4.sqlite3')
    with closing(sqlite3.connect(path)) as db:
        db.execute('PRAGMA foreign_keys=ON')
        items=products(db,1);rows=[]
        for p in items.values():
            evidence=[{'field':f,'value':p[f],'family':aliases[(f,p[f])]} for f in ['Report Group','EXCHANGEGROUP'] if (f,p.get(f)) in aliases]
            if not evidence:continue
            decision=classify(p,{e['family'] for e in evidence})
            rows.append(dict(code=p['code'],description=p['Description'],excel_row=p['rows'][0],package=p.get('Package'),evidence=evidence,**decision))
        backup=Path('data/backups')/('rla_pre_conditional_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.sqlite3')
        with closing(sqlite3.connect(backup)) as copy:db.backup(copy)
        families=dict(db.execute('SELECT name,family_id FROM families'))
        masters=list(db.execute('SELECT * FROM master_products ORDER BY master_id'))
        with db:
            db.execute("INSERT OR IGNORE INTO standardization_rules(rule_key,version,input_field,condition_json,output_field,status) VALUES('conditional-three-families',?,'description+groups+type+package',?,'family_id','draft')",(VERSION,json.dumps({'implementation':'db/conditional_taxonomy.py','scope':sorted(TARGETS),'no_auto_approval':True})))
            rule_id=db.execute("SELECT rule_id FROM standardization_rules WHERE rule_key='conditional-three-families' AND version=?",(VERSION,)).fetchone()[0]
            inserted=0
            for row in rows:
                raw_id=db.execute('SELECT raw_record_id FROM raw_records WHERE load_id=1 AND excel_row=?',(row['excel_row'],)).fetchone()[0]
                value=str(families[row['family']]) if row['family'] else None
                cursor=db.execute("INSERT OR IGNORE INTO field_standardization_proposals(raw_record_id,rule_id,target_field,proposed_value,status,reason) VALUES(?,?,'family_id',?,'pending',?)",(raw_id,rule_id,value,json.dumps({'reason':row['reason'],'evidence':row['evidence'],'code':row['code']},ensure_ascii=False)))
                inserted+=cursor.rowcount
            if inserted:db.execute("INSERT INTO audit_events(entity_type,entity_id,action,after_json,actor,reason) VALUES('standardization_rule',?,'generate_proposals',?,'conditional_taxonomy','Propuestas sin aprobacion ni asignacion')",(str(rule_id),json.dumps({'inserted':inserted})))
        assert masters==list(db.execute('SELECT * FROM master_products ORDER BY master_id'))
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    summary={'codes_reviewed':len(rows),'status':dict(Counter(r['status'] for r in rows)),
             'suggested_families':dict(Counter(r['family'] for r in rows if r['family'])),
             'inserted':inserted,'version':VERSION,'catalog_changed':False}
    out=Path('outputs/estandarizacion')
    (out/'revision_condicionada.json').write_text(json.dumps({'summary':summary,'rows':rows},ensure_ascii=False,indent=2),encoding='utf-8')
    esc=lambda v:html.escape(str(v))
    report=['<!doctype html><html lang="es"><meta charset="utf-8"><title>RLA · Reglas condicionadas</title><style>body{font:16px/1.5 system-ui;color:#20343e;max-width:1150px;margin:30px auto;padding:20px}table{border-collapse:collapse;width:100%}td,th{padding:10px;border-bottom:1px solid #ccd7dd;text-align:left}th{position:sticky;top:0;background:#edf3f5}h1{font-size:28px}</style><h1>Revisión condicionada de tres familias</h1><p>Propuestas pendientes de aprobación. No se modificó el catálogo. Fuente: carga 1, Lista_Productos.xlsx.</p>']
    report.append('<p>'+esc(f'{len(rows)} códigos examinados; {summary["status"]}')+'</p><p>Las reglas léxicas generan sugerencias, no validan identidad técnica. La falta de propuesta no excluye al producto. Se usa una fila representativa por código y se conservan sus evidencias.</p><table><tr><th>Código / fila</th><th>Descripción / paquete</th><th>Familia propuesta</th><th>Motivo</th></tr>')
    for r in sorted(rows,key=lambda r:(r['status']!='pendiente',r['code'])):
        report.append('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in [f'{r["code"]} / {r["excel_row"]}',f'{r["description"]} / {r["package"]}',r['family'] or 'Pendiente',r['reason']])+'</tr>')
    report.append('</table></html>')
    (out/'revision_condicionada.html').write_text(''.join(report),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
