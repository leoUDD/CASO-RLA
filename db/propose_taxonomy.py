"""Propuesta versionada, sin escribir al catálogo SQL."""
import html
import json
from pathlib import Path
import sqlite3
from collections import Counter
from db.matching import products
from db.import_excel import search_key

# Familia: categoría, alias explícitos de grupos existentes, atributos, plantilla.
FAMILIES = [
('Micrófonos','Audio',['MICROFONOS','AUDIO MICROPHONE','AUDIO MICROPHONE S','MICROFONOS INALAMBRICOS','MICROFONOS ALAMBRICOS','MICROFONOS DE PODIUM','MICROFONO PODIUM','MIC PODIUM','MICROFONO HEADSET','MICROFONO DE CAMARA'],['tipo','conectividad','patrón polar','longitud del cuello (in)','banda/frecuencia'],'Micrófono {tipo} {conectividad} {longitud} {marca} {modelo}'),
('Altavoces','Audio',['ALTAVOCES','SUB BAJO ACTIVO','SOUNDBAR','SISTEMA ARRAY','LINE ARRY'],['tipo','activo/pasivo','potencia (W) y norma','diámetro (in)'],'Altavoz {tipo} {activo/pasivo} {potencia y norma} {marca} {modelo}'),
('Consolas de audio','Audio',['CONSOLAS AUDIO','CONSOLAS DE AUDIO','POWER MIXER'],['canales','analógica/digital','amplificada'],'Consola de audio {canales} canales {tecnología} {marca} {modelo}'),
('Amplificadores','Audio',['AMPLIFICADOREWS'],['canales','potencia por canal e impedancia'],'Amplificador {canales} canales {potencia e impedancia} {marca} {modelo}'),
('Procesamiento de audio','Audio',['PROCESADORES DE AUDIO','CAJA DIRECTA','MATRIZ DE AUDIO','CONTROLADOR MIDI'],['función','entradas','salidas'],'{función} de audio {entradas/salidas} {marca} {modelo}'),
('Accesorios de audio','Audio',['ACCESORIOS AUDIO','ACCESORIOS DE AUDIO','PERIFERICOS AUDIO','RECEPTOR MIC','ANTENA AUDIO','DISTRIBUIDOR DE ANTENAS','ATRIL DE MICROFONO','SOPORTE PARLANTE','AUDIFONOS'],['tipo de accesorio','compatibilidad','conectividad'],'{tipo de accesorio} de audio {compatibilidad} {marca} {modelo}'),
('Proyectores','Video',['PROYECTORES','PROJECTOR','PROYECTORES LASER'],['luminosidad y norma','resolución nativa','tecnología','relación de tiro'],'Proyector {luminosidad y norma} {resolución nativa} {tecnología} {marca} {modelo}'),
('Monitores y televisores','Video',['MONITORES Y TV','TELEVISORES MONITORES','PANTALLA TACTIL','PANTALLAS TACTILES'],['diagonal (in)','resolución','táctil'],'{monitor/televisor} {diagonal} in {resolución} {marca} {modelo}'),
('Pantallas LED','Video',['PANTALLA LED'],['pixel pitch (mm)','ancho y alto del módulo (m)','interior/exterior','clase','unidad comercial'],'Pantalla LED {pitch} mm {dimensiones} {clase} {unidad comercial} {marca} {modelo}'),
('Pantallas de proyección','Video',['TELONES','TELON ELECTRICO','TELON MECANO','TELON MANUAL','PANTALLA INFLABLE'],['mecanismo','ancho y alto (m)','relación de aspecto'],'Pantalla de proyección {mecanismo} {dimensiones} {relación}'),
('Cámaras','Video',['CAMARA DE VIDEO','FOTOGRAFIA'],['tipo','resolución','interfaces'],'Cámara {tipo} {resolución} {marca} {modelo}'),
('Procesamiento y distribución de video','Video',['DISTRIBUIDOR DE VIDEO','EXTENSORES DE VIDEO','PROCESADOR DE VIDEO','SWITH DE VIDEO','MATRIZ DE VIDEO','ESCALADORES','ESCALER','SWITCHER/DISTRIBUIDOR'],['función','interfaces','entradas/salidas','resolución admitida'],'{función} de video {interfaces} {entradas/salidas} {marca} {modelo}'),
('Reproducción de video','Video',['REPRODUCTORES VIDEO','SISTEMA WATCHOUT','DIGITAL SIGNAGE'],['función','formato','salidas'],'Reproductor de video {formato} {marca} {modelo}'),
('Accesorios de video','Video',['ACCESORIOS DE VIDEO','ADAPTADORES DE VIDEO','SOPORTE PLASMA','SOPORTE LCD','SOPORTE PROYECTOR','SOPORTE WALL 4'],['tipo','compatibilidad','conectores'],'{tipo de accesorio} de video {compatibilidad} {marca} {modelo}'),
('Computadores','Informática y redes',['NOTEBOOK','LAPTOP','CPU','COMPUTADORES','SERVIDORES'],['formato','procesador','RAM (GB)','almacenamiento (GB)','sistema operativo'],'{Notebook/PC/servidor} {procesador} {RAM} GB {almacenamiento} {marca} {modelo}'),
('Redes','Informática y redes',['REDES','SWITCH DE RED','ROUTERS','NETWORKING'],['tipo','puertos','velocidad','PoE'],'{Switch/router} {puertos} puertos {velocidad} {PoE} {marca} {modelo}'),
('Impresoras','Informática y redes',['IMPRESORA','IMPRESORAS'],['tecnología','color/monocromo','formato'],'Impresora {tecnología} {color} {formato} {marca} {modelo}'),
('Periféricos y almacenamiento','Informática y redes',['PERIFERICOS PC','MOUSE INALAMBRICO','MEMRORIAS','DISPOSITIVOS MOVILES','LECTORES CODIGOS','ACCESORIOS INFORMATICOS'],['tipo','capacidad','interfaz'],'{tipo} {capacidad} {interfaz} {marca} {modelo}'),
('Luminarias','Iluminación',['FOCOS LED','FOCO PAR 64','ROBOTIZADO','LASER'],['tipo','fuente','potencia (W)','canales de control'],'Luminaria {tipo} {fuente} {potencia} W {marca} {modelo}'),
('Control de iluminación','Iluminación',['CONSOLA DE ILUMINACION','SPLITTER ILUMINACION','POWER DIMMER','DIMMER'],['función','protocolo','canales'],'{controlador/dimmer/splitter} {protocolo} {canales} canales {marca} {modelo}'),
('Accesorios de iluminación','Iluminación',['PERIFERICO ILUMINACION','SOPORTE ILUMINACION'],['tipo','compatibilidad'],'{tipo de accesorio} de iluminación {compatibilidad}'),
('Distribución eléctrica','Energía',['TABLERO ELECTRICO','PERIFERICOS ELECTRICIDAD'],['función','tensión (V)','corriente (A)','fases','conectores'],'{tipo} eléctrico {tensión} V {corriente} A {fases}'),
('Respaldo y generación','Energía',['UPS','GENERADOR'],['tipo','potencia y unidad W/VA/kVA','tensión','autonomía'],'{UPS/generador} {potencia y unidad} {tensión} V {marca} {modelo}'),
('Interpretación simultánea','Interpretación y comunicaciones',['SISTEMA DE INTERPRETACION SIMULTANEA','TRADUCCION SIMULTANEA','AUDIFONO TRADUCCION','RECEPTOR DE TRADUCCION','PUPITRE','CABINAS'],['función','canales/idiomas','tecnología','compatibilidad'],'{tipo de equipo} de interpretación {canales} {marca} {modelo}'),
('Debate y votación','Interpretación y comunicaciones',['MIC DEBATE','SISTEMA DE DEBATE','SISTEMA DEBATE','SISTEMA DE VOTACION'],['función','conectividad','compatibilidad'],'{unidad de debate/votación} {función} {marca} {modelo}'),
('Conferencia e intercomunicación','Interpretación y comunicaciones',['VIDEOCONFERENCIA','VIDEO CONFERENCIA','TELEFONO CONFERENCIA','INTERCOMUNICADORES','RADIOS'],['función','protocolo/banda','compatibilidad'],'{tipo de equipo} {protocolo/banda} {marca} {modelo}'),
('Cables y adaptadores','Conectividad',['CABLES','CABLE','CABLES DE AUDIO','CABLES VIDEO','CABLES DE ENERGIA','CABLES DE RED','CABLES DE DATOS','CABLES TRADUCCION','CABLES ILUMINACION','CABLE S'],['función/señal','conector A y género','conector B y género','longitud (m)','calibre/especificación'],'Cable {conector A} a {conector B} {longitud} m {especificación}'),
('Estructuras y montaje','Montaje y soporte',['ACCESORIOS MONTAJE','RIGGING PANTALLA LED','ESTRUCTURA','BASE PISO'],['tipo','dimensiones','carga admisible y unidad','compatibilidad'],'{tipo de estructura/soporte} {dimensiones} {compatibilidad}'),
('Transporte y protección de equipos','Montaje y soporte',['CASES','BOLSOS'],['tipo','dimensiones','compatibilidad'],'{case/bolso} {compatibilidad} {dimensiones}'),
('Mobiliario y oficina','Mobiliario y oficina',['MOBILIARIO','ARTICULOS DE OFICINA','PAPELOGRAFO'],['tipo','dimensiones','material'],'{tipo} {dimensiones} {material}'),
('Consumibles y repuestos','Consumibles y repuestos',['INSUMOS','REPUESTOS','TINTA IMPRESORA','BATERIAS'],['naturaleza consumible/repuesto','tipo','compatibilidad','capacidad/unidad'],'{consumible/repuesto} {tipo} {compatibilidad} {capacidad/unidad}'),
('Servicios técnicos','Servicios',['SERVICIO TECNICO','CONFIGURACION REDES','EDICION','REGISTRO AUDIO','MAPING'],['especialidad','alcance','unidad de cobro','duración'],'Servicio {especialidad} {alcance} por {unidad de cobro}'),
('Personal','Servicios',['LABOR','PERSONAL','OPERADOR','INTERPRETES','DJ'],['rol','especialidad','jornada/duración','unidad de cobro'],'Personal {rol} {especialidad} {jornada}'),
('Transporte y viajes','Servicios',['TRANSPORTE','VIAJES','VIAJE SUR'],['vehículo','origen','destino','trayecto','unidad de cobro'],'Transporte {vehículo} {origen} a {destino} {trayecto}'),
('Licencias','Servicios',['LICENCIA'],['software','edición','vigencia','usuarios'],'Licencia {software} {edición} {vigencia} {usuarios} usuarios'),
('Gastos y cargos','Cargos comerciales',['IMPREVISTOS','COMISION AGENCIA','ALOJAMIENTO','ALIMENTACION'],['concepto','base de cobro','unidad'],'Cargo {concepto} por {unidad}')]


def main():
    out=Path('outputs/estandarizacion');out.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect('data/rla.sqlite3') as db: items=products(db,1)
    aliases={search_key(alias):(i+1,name,category) for i,(name,category,values,attrs,template) in enumerate(FAMILIES) for alias in values}
    fields=['Report Group','EXCHANGEGROUP','DEPARTMENT','Availability Group','REVENUEGROUP']
    mapping=[]; evidence={}; proposals=[]
    for field in fields:
        groups={}
        for p in items.values():
            value=p.get(field)
            if value: groups.setdefault(value,[]).append(p)
        for value,group in sorted(groups.items()):
            match=aliases.get(search_key(value))
            # Revenue es contable/comercial: aporta evidencia, nunca asigna familia.
            eligible=field in ['Report Group','EXCHANGEGROUP']
            mapping.append({'field':field,'original':value,'codes':len(group),'category':match[2] if match else None,
                            'family':match[1] if match else None,'status':'propuesta de equivalencia' if match and eligible else 'requiere contexto',
                            'examples':[{'code':p['code'],'description':p.get('Description'),'row':p['rows'][0]} for p in group[:3]]})
    for p in items.values():
        signals=[(f,aliases[search_key(p[f])]) for f in ['Report Group','EXCHANGEGROUP'] if p.get(f) and search_key(p[f]) in aliases]
        families={m[0] for f,m in signals}
        status='pendiente'
        if p['quarantined']: status='cuarentena'
        elif len(families)>1: status='conflicto entre grupos'
        elif len(families)==1: status='propuesta por revisar'
        selected=signals[0][1] if status=='propuesta por revisar' else None
        proposals.append({'code':p['code'],'description':p.get('Description'),'row':p['rows'][0],
                          'type':p.get('Type'),'package':p.get('Package'),'family':selected[1] if selected else None,
                          'category':selected[2] if selected else None,'status':status,
                          'evidence':[{'field':f,'value':p[f],'suggested_family':m[1]} for f,m in signals]})
    schema=[{'id':i+1,'category':cat,'family':name,'attributes':attrs,'template':template,
             'source_aliases':values,'status':'borrador'} for i,(name,cat,values,attrs,template) in enumerate(FAMILIES)]
    summary={'products':len(items),'categories':len(set(f['category'] for f in schema)), 'families':len(schema),
             'source_values':len(mapping),'proposal_status':dict(Counter(p['status'] for p in proposals)),
             'load':1,'version':'borrador-1','applied_to_catalog':False}
    payload={'summary':summary,'taxonomy':schema,'mappings':mapping,'proposals':proposals}
    (out/'propuesta.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    esc=lambda s:html.escape(str(s))
    blocks=['<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>RLA · Propuesta de estandarización</title><style>body{font:16px/1.55 system-ui;background:#f8fafb;color:#21343e;margin:0}main{max-width:1120px;margin:auto;padding:30px}h1{font-size:28px}h2{font-size:22px;margin-top:32px}details{padding:14px 0;border-bottom:1px solid #cbd8df}summary{cursor:pointer;font-weight:600}small{color:#546770}.tag{color:#07696d}table{border-collapse:collapse;width:100%;font-size:14px}td,th{text-align:left;padding:10px;border-bottom:1px solid #cbd8df;vertical-align:top}.scroll{overflow:auto;max-height:500px}th{position:sticky;top:0;background:#eaf0f3}</style><main><p>RLA / Estandarización / Borrador 1</p><h1>Taxonomía y reglas de nombres</h1><p>Propuesta basada en categorías y productos de la carga 1. No se modificaron maestros, categorías SQL, países ni decisiones de duplicidad.</p>']
    blocks.append('<p class="tag">'+esc(f'{summary["categories"]} categorías · {summary["families"]} familias · {len(mapping)} valores originales por campo revisados')+'</p>')
    blocks.append('<h2>Alcance y cobertura</h2><ul>'+''.join('<li>'+esc(k)+': '+str(v)+' códigos</li>' for k,v in summary['proposal_status'].items())+'</ul><p>Una propuesta por revisar es una correspondencia entre etiquetas, no una clasificación validada del producto. Las descripciones pueden contradecirla. No se fuerza una familia en casos sin señal suficiente.</p>')
    blocks.append('<h2>Reglas comunes</h2><ul><li>Nombre de presentación en español con acentos; marca y modelo conservan su escritura aprobada.</li><li>Nombre = tipo específico + atributos que distinguen variantes + marca/modelo cuando aporten identidad. Omitir datos desconocidos; no rellenar con NA.</li><li>Conservar original, propuesta, regla, versión, evidencia y estado de aprobación por campo.</li><li>País pertenece al sitio; no se deduce del prefijo del código. Moneda y fecha de corte siguen pendientes.</li><li>Tipo ITEM/LABOR/MISCCHARGE/PARTS, paquete, serialización, unidad comercial y modalidad de subarriendo son dimensiones independientes de la familia.</li><li>Medidas solo se convierten cuando el número y la unidad sean explícitos y no ambiguos. W, VA y kVA no se intercambian; luminosidad no se completa desde el modelo.</li><li>Fabricantes: mayúsculas/espacios para búsqueda, pero equivalencias de marcas distintas requieren aprobación. No borrar guiones ni sufijos del modelo.</li><li>Servicios: origen, destino, alcance, duración y unidad de cobro distinguen registros. Parecido textual no basta.</li></ul>')
    blocks.append('<h2>Taxonomía propuesta y atributos</h2>')
    for f in schema:
        samples=[p for p in proposals if p['family']==f['family']][:3]
        blocks.append('<details><summary>'+esc(f['category']+' / '+f['family'])+'</summary><p>Atributos a estructurar: '+esc(', '.join(f['attributes']))+'</p><p>Plantilla: '+esc(f['template'])+'</p><p>Alias observados: '+esc(', '.join(f['source_aliases']))+'</p>')
        for p in samples: blocks.append('<p><b>'+esc(p['code'])+'</b> — '+esc(p['description'])+' <small>(fila '+str(p['row'])+')</small></p>')
        blocks.append('</details>')
    blocks.append('<h2>Equivalencias de etiquetas originales</h2><p>Report Group y EXCHANGEGROUP aportan propuestas de familia. Los otros campos se mantienen como contexto; ningún campo se declara fuente de verdad.</p><div class="scroll"><table><tr><th>Campo</th><th>Original</th><th>Códigos</th><th>Familia sugerida</th><th>Tratamiento</th></tr>')
    for m in mapping: blocks.append('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in [m['field'],m['original'],m['codes'],m['family'] or 'Sin equivalencia',m['status']])+'</tr>')
    blocks.append('</table></div><h2>Conflictos reales entre grupos</h2><p>Hasta 20 ejemplos; todos los registros y su evidencia se conservan en propuesta.json.</p>')
    for p in [p for p in proposals if p['status']=='conflicto entre grupos'][:20]:
        blocks.append('<p><b>'+esc(p['code'])+'</b> — '+esc(p['description'])+'<br><small>'+esc('; '.join(e['field']+' = '+e['value']+' → '+e['suggested_family'] for e in p['evidence']))+'</small></p>')
    blocks.append('<h2>Decisiones pendientes</h2><p>Validar la taxonomía, revisar compatibilidad de cada grupo con los productos, completar alias ambiguos y aprobar extracción por familia. Consola, monitor, procesadores, control, accesorios, códigos numéricos y etiquetas mixtas no se mapean automáticamente. Los cuatro DEFAULT permanecen en cuarentena.</p><p>Fuente: Lista_Productos.xlsx, hoja Lista de productos, carga 1. Conteos por código legado, no por fila ni por producto maestro consolidado.</p></main></html>')
    (out/'propuesta.html').write_text(''.join(blocks),encoding='utf-8')
    assert sum(summary['proposal_status'].values())==len(items)
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
