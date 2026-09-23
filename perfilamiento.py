"""Diagnóstico reproducible, de solo lectura, de Lista_Productos.xlsx.

Uso: python perfilamiento.py --input RUTA.xlsx --output outputs/perfilamiento
Dependencias: pandas, openpyxl (solo lectura).
"""
import argparse
import hashlib
import html
import json
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def normalized(value):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', value.strip().upper())
                           if not unicodedata.combining(c)).split())


def number(value):
    """Parsea formatos inequívocos; un único separador con 3 decimales se marca ambiguo."""
    s = value.strip()
    if not s:
        return None, 'vacio'
    if re.fullmatch(r'[+-]?\d+', s):
        return float(s), 'entero'
    if re.fullmatch(r'[+-]?\d+[,.]\d+', s):
        if len(re.split('[,.]', s)[-1]) == 3:
            return None, 'ambiguo'
        return float(s.replace(',', '.')), 'decimal_coma' if ',' in s else 'decimal_punto'
    if re.fullmatch(r'[+-]?\d{1,3}(?:\.\d{3})+,\d+', s):
        return float(s.replace('.', '').replace(',', '.')), 'miles_punto_decimal_coma'
    if re.fullmatch(r'[+-]?\d{1,3}(?:,\d{3})+\.\d+', s):
        return float(s.replace(',', '')), 'miles_coma_decimal_punto'
    return None, 'no_interpretable'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', type=Path, default=Path('outputs/perfilamiento'))
    args = parser.parse_args()
    source = args.input.resolve()
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    xls = pd.ExcelFile(source)
    sheet = 'Lista de productos' if 'Lista de productos' in xls.sheet_names else xls.sheet_names[0]
    # No convertir tokens como NA, N/A o NULL a nulos implícitos.
    d = pd.read_excel(xls, sheet_name=sheet, dtype=str, keep_default_na=False).fillna('')
    xls.close()
    required = ['Product ID', 'SITEID', 'Description', 'MANUFACTURER', 'MODEL']
    missing = [c for c in required if c not in d]
    if missing:
        raise ValueError(f'Faltan columnas requeridas: {missing}')
    out = args.output.resolve()
    if source.is_relative_to(out):
        raise ValueError('La salida debe estar separada del archivo original.')
    out.mkdir(parents=True, exist_ok=True)
    stripped = d.apply(lambda c: c.str.strip())
    valid = stripped.replace('', pd.NA)
    ids = stripped['Product ID']
    good = ids.ne('')
    base = valid.loc[good].groupby('Product ID', sort=False).first()
    profiles, variants = [], []
    for col in d:
        s = stripped[col]
        present = s.ne('')
        counts = s[present].value_counts()
        mapped = pd.DataFrame({'original': s[present].unique()})
        mapped['normalizado'] = mapped['original'].map(normalized)
        groups = mapped.groupby('normalizado')['original'].agg(list)
        for key, values in groups.items():
            if len(values) > 1:
                variants.append({'campo': col, 'normalizado': key, 'variantes': values})
        profiles.append({'campo': col, 'filas': len(d), 'vacios': int((~present).sum()),
                         'porcentaje_vacio': round((~present).mean()*100, 4),
                         'distintos_originales_no_vacios': int(d.loc[present,col].nunique()),
                         'distintos_sin_espacios_exteriores': len(counts),
                         'filas_con_espacios_exteriores': int(d[col].ne(s).sum()),
                         'tokens_posible_ausencia': int(s.str.upper().isin(['N/A','NA','NULL','NONE','S/N','SIN DATO','-']).sum()),
                         'ejemplos_frecuentes': [{'valor':v,'filas':int(n)} for v,n in counts.head(5).items()]})
    attrs = [c for c in ['Description','MANUFACTURER','MODEL','Type','Package','ITEMCATEGORY',
                         'Availability Group','Report Group','DEPARTMENT','REVENUEGROUP','EXCHANGEGROUP',
                         'CANRENT','CANSELL','CANSUBRENT'] if c in d]
    conflicts = []
    conflict_rows = []
    for col in attrs:
        n = valid.loc[good].groupby('Product ID')[col].nunique()
        bad = n[n.gt(1)].index
        conflicts.append({'campo': col, 'codigos_con_valores_distintos':len(bad)})
        for pid in bad:
            vals = valid.loc[ids.eq(pid), col].dropna().unique().tolist()
            conflict_rows.append({'campo':col,'Product ID':pid,'valores':vals})
    numeric = []
    anomalies = []
    for col in [c for c in ['Stock','Cost','Replacement Cost','CostoTotal','RETAILPRICE',
                            'LOWRETAILPRICE','MAXIMUMQTY','MINIMUMQTY','MSRP','REORDERQTY'] if c in d]:
        parsed = stripped[col].map(number)
        status = parsed.map(lambda x:x[1])
        values = pd.Series([x[0] for x in parsed],dtype='float64')
        numeric.append({'campo':col,'formatos':dict(Counter(status)),
                        'negativos':int(values.lt(0).sum()),'ceros':int(values.eq(0).sum()),
                        'positivos':int(values.gt(0).sum()),
                        'minimo':None if values.dropna().empty else float(values.min()),
                        'maximo':None if values.dropna().empty else float(values.max())})
        flag = status.isin(['ambiguo','no_interpretable']) | values.lt(0)
        for i in d.index[flag]:
            anomalies.append({'fila_excel':int(i)+2,'campo':col,'valor':d.at[i,col],
                              'Product ID':ids[i], 'SITEID':stripped.at[i,'SITEID'],
                              'motivo':status[i] if status[i] in ['ambiguo','no_interpretable'] else 'negativo_revisar'})
    for i in d.index[ids.eq('') | ids.eq('0')]:
        anomalies.append({'fila_excel':int(i)+2,'campo':'Product ID','valor':ids[i],
                          'Product ID':ids[i],'SITEID':stripped.at[i,'SITEID'],
                          'motivo':'codigo_vacio' if not ids[i] else 'codigo_cero_revisar'})
    # Candidatos: solo evidencia de coincidencia, nunca fusiones.
    b = base.fillna('').copy()
    for c in ['MANUFACTURER','MODEL','Description']:
        b[c+'_norm'] = b[c].map(normalized)
    candidate_groups = []
    known = b['MANUFACTURER_norm'].ne('') & b['MODEL_norm'].ne('')
    for (brand, model), group in b[known].groupby(['MANUFACTURER_norm','MODEL_norm']):
        if len(group)>1:
            candidate_groups.append({'fabricante':brand,'modelo':model,'codigos':group.index.tolist(),
                                     'descripciones':group['Description'].tolist()})
    completeness = []
    for col in required[2:]:
        completeness.append({'campo':col,'filas_sin_valor':int(valid[col].isna().sum()),
                             'codigos_sin_ningun_valor':int(base[col].isna().sum()),
                             'codigos_totales':len(base)})
    categories = {}
    for c in ['Type','ITEMCATEGORY','Package','Availability Group','Report Group','DEPARTMENT','REVENUEGROUP','EXCHANGEGROUP']:
        if c in d:
            categories[c] = [{'valor':v,'filas':int(n),'codigos':int(ids[stripped[c].eq(v)].nunique())}
                             for v,n in stripped[c].value_counts().items()]
    site_map = valid.groupby('SITEID')['SITENAME'].nunique() if 'SITENAME' in d else pd.Series(dtype=int)
    summary = {'archivo':str(source),'sha256':before,'generado_utc':datetime.now(timezone.utc).isoformat(),
               'hojas_disponibles':xls.sheet_names,'hoja_analizada':sheet,'filas':len(d),'columnas':len(d.columns),
               'codigos_no_vacios':int(ids[good].nunique()),'sitios_no_vacios':int(valid['SITEID'].nunique()),
               'filas_duplicadas_exactas':int(d.duplicated().sum()),
               'repeticiones_clave_original':int(d.duplicated(['Product ID','SITEID']).sum()),
               'repeticiones_clave_sin_espacios':int(stripped.duplicated(['Product ID','SITEID']).sum()),
               'filas_sin_codigo':int((~good).sum()),'filas_codigo_cero':int(ids.eq('0').sum()),
               'codigos_con_ceros_iniciales':int(ids[ids.str.match(r'^0\d+$')].nunique()),
               'longitudes_codigo':{str(k):int(v) for k,v in ids[good].drop_duplicates().str.len().value_counts().sort_index().items()},
               'sitios_con_varios_nombres':int(site_map.gt(1).sum()),
               'campos_totalmente_vacios':[p['campo'] for p in profiles if p['vacios']==len(d)],
               'grupos_marca_modelo_compartidos':len(candidate_groups),
               'codigos_en_grupos_marca_modelo':sum(len(g['codigos']) for g in candidate_groups),
               'completitud':completeness,'conflictos_por_codigo':conflicts,'numericos':numeric}
    after = hashlib.sha256(source.read_bytes()).hexdigest()
    if before != after:
        raise RuntimeError('El archivo fuente cambió durante el análisis.')
    summary['original_sin_cambios_sha256'] = True
    payload = {'resumen':summary,'perfil_columnas':profiles,'categorias':categories,
               'variantes_tipograficas':variants,'conflictos':conflict_rows,
               'candidatos_marca_modelo':candidate_groups,'anomalias':anomalies}
    (out/'diagnostico.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    # Datos tabulares de evidencia; JSON conserva las listas sin pérdida.
    for name, rows in [('perfil_columnas',profiles),('anomalias',anomalies),('conflictos',conflict_rows),('candidatos_marca_modelo',candidate_groups)]:
        if rows:
            frame = pd.DataFrame(rows)
            for c in frame:
                frame[c] = frame[c].map(lambda v:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v)
            frame.to_csv(out/(name+'.csv'),index=False,encoding='utf-8-sig')
    def esc(v):
        return html.escape(str(v))
    def table(rows, fields):
        return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+esc(label)+'</th>' for key,label in fields)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+esc(row.get(key,''))+'</td>' for key,label in fields)+'</tr>' for row in rows)+'</tbody></table></div>'
    parts = ['<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>RLA · Perfilamiento</title><style>body{font:16px/1.55 system-ui;color:#182c39;background:#f7f8fa;margin:0}main{max-width:1120px;margin:auto;padding:36px 24px}h1{font-size:30px}h2{margin-top:36px;font-size:22px}.metrics{display:flex;gap:30px;flex-wrap:wrap;border-block:1px solid #bac9d1;padding:20px 0}.metrics strong{display:block;font-size:27px;color:#086b71}table{border-collapse:collapse;width:100%;font-size:14px;background:white}th,td{text-align:left;padding:10px;border-bottom:1px solid #d9e0e4;vertical-align:top}th{background:#e8eff2;position:sticky;top:0}.scroll{overflow:auto;max-height:540px}small{color:#526571}code{overflow-wrap:anywhere}details{margin:16px 0}summary{cursor:pointer;font-weight:600}@media print{.scroll{max-height:none;overflow:visible}body{background:white}}</style><main><p>RLA / Problema 1 / Paso 1</p><h1>Diagnóstico del catálogo de productos</h1><p>Perfilamiento de solo lectura. Las coincidencias son señales para investigar; no se han fusionado ni corregido productos.</p>']
    parts.append('<div class="metrics">'+''.join(f'<div><strong>{v:,}</strong>{label}</div>' for label,v in [('Registros',len(d)),('Columnas',len(d.columns)),('Códigos no vacíos',summary['codigos_no_vacios']),('Sitios',summary['sitios_no_vacios'])])+'</div>')
    parts.append('<h2>Qué cambia para el diseño</h2><ul><li>Evaluar la clave producto–sitio antes de hablar de duplicados: '+str(summary['repeticiones_clave_original'])+' repeticiones adicionales de la clave original.</li><li>Conservar los códigos como texto para no perder ceros iniciales.</li><li>Separar ausencia por fila de ausencia por código. Un campo puede existir en otro sitio del mismo producto.</li><li>Marca y modelo compartidos generan candidatos; no prueban equivalencia de paquetes, especificaciones o uso.</li><li>No sumar costos entre sitios: el archivo no contiene una columna explícita de moneda. Stock no demuestra disponibilidad para fechas futuras.</li></ul>')
    parts.append('<h2>Completitud de identidad</h2>'+table(completeness,[('campo','Campo'),('filas_sin_valor','Filas vacías'),('codigos_sin_ningun_valor','Códigos sin ningún valor'),('codigos_totales','Códigos evaluados')]))
    parts.append('<h2>Perfil de las 42 columnas</h2><p>Vacío = celda vacía o texto formado solo por espacios. Los tokens NA, N/A y NULL se conservan como valores y se señalan aparte.</p>'+table(profiles,[('campo','Campo'),('vacios','Vacíos'),('porcentaje_vacio','Vacíos (%)'),('distintos_originales_no_vacios','Distintos originales'),('filas_con_espacios_exteriores','Filas con espacios exteriores'),('tokens_posible_ausencia','Posibles marcadores de ausencia')]))
    parts.append('<h2>Consistencia dentro de cada código</h2><p>Se cuentan códigos con más de un valor no vacío; los faltantes no se consideran contradicciones.</p>'+table(conflicts,[('campo','Campo'),('codigos_con_valores_distintos','Códigos con contradicción textual')]))
    parts.append('<h2>Formatos y valores numéricos</h2><p>Interpretación provisional: decimal coma/punto y miles explícitos; un único separador seguido de tres dígitos se marca ambiguo. Los negativos requieren contexto; no se corrigen automáticamente.</p>'+table(numeric,[('campo','Campo'),('formatos','Formatos y conteos'),('negativos','Negativos'),('ceros','Ceros'),('minimo','Mínimo interpretable'),('maximo','Máximo interpretable')]))
    parts.append(f'<h2>Candidatos de marca y modelo</h2><p>{len(candidate_groups)} grupos con varios códigos; {summary["codigos_en_grupos_marca_modelo"]} códigos involucrados. Se muestran hasta 15 grupos. El detalle completo está en diagnostico.json y en el CSV correspondiente.</p>'+table(candidate_groups[:15],[('fabricante','Fabricante normalizado'),('modelo','Modelo normalizado'),('codigos','Códigos'),('descripciones','Descripciones originales')]))
    parts.append(f'<h2>Anomalías para revisar</h2><p>{len(anomalies)} incidencias campo–fila; una fila puede tener varias. Vista de las primeras 30.</p>'+table(anomalies[:30],[('fila_excel','Fila Excel'),('Product ID','Código'),('campo','Campo'),('valor','Valor'),('motivo','Motivo')]))
    parts.append('<h2>Distribuciones de clasificación</h2>')
    for col, rows in categories.items():
        parts.append('<details><summary>'+esc(col)+'</summary>'+table(rows,[('valor','Valor (vacío sin texto)'),('filas','Filas'),('codigos','Códigos distintos')])+'</details>')
    parts.append('<h2>Método y trazabilidad</h2><p>Se analiza una hoja completa. No se modifican celdas ni se infieren países, monedas, equivalencias o definiciones operacionales. La lectura no audita estilos, fórmulas ni resultados recalculados en Excel. Los códigos se agrupan quitando espacios exteriores; se informa por separado la clave original.</p><p>Fuente: '+esc(source)+' · Hoja: '+esc(sheet)+'</p><small>SHA-256 antes y después: <code>'+before+'</code><br>Generado: '+esc(summary['generado_utc'])+'</small></main></html>')
    (out/'diagnostico.html').write_text(''.join(parts),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
