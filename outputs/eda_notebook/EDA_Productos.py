# %% [markdown]
# # EDA de productos RLA — evidencia antes de decidir
# Ejecutar las celdas en orden en VS Code (extensiones Python y Jupyter).
# Seleccionar un kernel con pandas, numpy, matplotlib e ipykernel.
# Instalación, si hace falta, en la terminal: `python -m pip install pandas numpy matplotlib ipykernel`.
# El CSV adjunto contiene las 42 columnas originales del staging de la carga 1,
# sin normalizaciones, exclusiones ni familias inferidas. Una fila representa producto × sitio.
# Repetir un código en varios sitios no implica duplicación de producto.
# Este notebook no modifica la base de datos ni elimina registros.

# %%
from pathlib import Path
import hashlib
import json
import re
import unicodedata
from decimal import Decimal, InvalidOperation
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from IPython.display import display

pd.set_option('display.max_columns', 45)
pd.set_option('display.max_colwidth', 100)
plt.rcParams.update({'figure.figsize': (11, 5), 'axes.spines.top': False, 'axes.spines.right': False})

# %% [markdown]
# ## 1. Archivo y procedencia
# Si VS Code usa otro directorio de trabajo, modificar CSV_PATH con la ruta completa.
# UTF-8 con BOM y separador coma. Todo se carga como texto para preservar ceros iniciales,
# códigos, marcadores como NA y formatos numéricos. Los vacíos se analizan explícitamente.

# %%
BASE = Path(__file__).resolve().parent if '__file__' in globals() else Path.cwd()
CSV_PATH = BASE / 'Lista_Productos_original.csv'
if not CSV_PATH.exists():
    CSV_PATH = Path.home() / 'Desktop' / 'EDA_RLA' / 'Lista_Productos_original.csv'
if not CSV_PATH.exists():
    raise FileNotFoundError('Modifica CSV_PATH para apuntar al CSV adjunto.')
raw = pd.read_csv(CSV_PATH, encoding='utf-8-sig', sep=',', dtype='string', keep_default_na=False)
assert raw.columns.is_unique, 'Hay encabezados repetidos'
required = {'Product ID', 'SITEID', 'Description'}
assert required <= set(raw.columns), f'Faltan columnas: {required - set(raw.columns)}'
csv_hash = hashlib.sha256(CSV_PATH.read_bytes()).hexdigest()
print(f'Archivo: {CSV_PATH}\nSHA256: {csv_hash}\nFilas: {len(raw):,}; columnas: {raw.shape[1]}')
manifest_path = CSV_PATH.with_name('procedencia.json')
if manifest_path.exists():
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    display(manifest)
    assert manifest['csv_sha256'] == csv_hash, 'El CSV cambió respecto del exportado'
display(raw.head())

# %% [markdown]
# ## 2. Preparación de una copia para explorar
# Solo se quitan espacios externos y se representan blancos como NA en `df`.
# No se sustituyen marcadores, no se imputan datos ni se alteran `raw` o el CSV.

# %%
df = raw.apply(lambda s: s.str.strip()).replace('', pd.NA)
df.index = pd.RangeIndex(2, len(df) + 2, name='fila_excel')
raw.index = df.index
summary = pd.Series({'filas_producto_sitio': len(df), 'columnas': df.shape[1],
                     'codigos_producto': df['Product ID'].nunique(), 'sitios': df['SITEID'].nunique()})
display(summary.to_frame('valor'))
df.info()

# %% [markdown]
# ## 3. Nulos, completitud y marcadores de ausencia
# Los porcentajes de filas están ponderados por sitios. La tabla por código evita
# confundir un fabricante repetido en muchos sitios con muchos productos distintos.
# NA, S/N o GENERICO son señales a revisar, no nulos automáticos.

# %%
profile = pd.DataFrame({'tipo': raw.dtypes.astype(str), 'nulos': df.isna().sum(),
                        'porcentaje_nulos': df.isna().mean().mul(100),
                        'valores_distintos': df.nunique(dropna=True)})
display(profile.sort_values('porcentaje_nulos', ascending=False))
profile.sort_values('porcentaje_nulos').tail(20)['porcentaje_nulos'].plot.barh(color='#286a87')
plt.title('20 columnas con mayor ausencia — todas las filas del CSV')
plt.xlabel('Filas con valor ausente (%)'); plt.ylabel('Columna'); plt.tight_layout(); plt.show()
identity_cols = [c for c in ['Description', 'MANUFACTURER', 'MODEL'] if c in df]
missing_by_code = df.dropna(subset=['Product ID']).groupby('Product ID')[identity_cols].count().eq(0)
display(pd.DataFrame({'codigos_sin_dato_en_ningun_sitio': missing_by_code.sum(),
                      'porcentaje_codigos': missing_by_code.mean().mul(100)}))
markers = {'NA', 'N/A', 'NULL', 'NONE', 'S/N', 'SIN DATO', '-', 'GENERICO', 'GENERICA'}
marker_mask = df.apply(lambda s: s.str.upper().isin(markers))
display(marker_mask.sum().sort_values(ascending=False).to_frame('posibles_marcadores'))

# %% [markdown]
# ## 4. Duplicados y contradicciones
# Separar filas exactas, clave producto-sitio repetida y atributos incompatibles para un código.
# Una descripción compartida por distintos códigos solo es candidata a revisión.

# %%
exact_duplicates = raw.loc[raw.duplicated(keep=False)]
valid_key = df[['Product ID','SITEID']].notna().all(axis=1)
key_duplicates = df.loc[valid_key & df.duplicated(['Product ID','SITEID'], keep=False)]
identity_fields = [c for c in ['Description','MANUFACTURER','MODEL','Type','Package','ITEMCATEGORY'] if c in df]
distinct = df.dropna(subset=['Product ID']).groupby('Product ID')[identity_fields].nunique()
conflicts = distinct.loc[distinct.gt(1).any(axis=1)]
display(pd.Series({'filas_en_duplicados_exactos': len(exact_duplicates),
                   'filas_con_clave_repetida': len(key_duplicates),
                   'codigos_con_conflicto_identidad': len(conflicts)}).to_frame('cantidad'))
display(key_duplicates.head(20)); display(conflicts.head(30))
def search_key(value):
    if pd.isna(value): return pd.NA
    value = ' '.join(str(value).upper().split())
    return ''.join(ch for ch in unicodedata.normalize('NFKD', value) if not unicodedata.combining(ch))
description_keys = df['Description'].map(search_key)
description_candidates = (df.assign(clave_descripcion=description_keys)
    .dropna(subset=['Product ID','clave_descripcion'])
    .groupby('clave_descripcion')['Product ID'].agg(lambda s: sorted(s.unique().tolist())))
description_candidates = description_candidates[description_candidates.map(len) > 1]
display(description_candidates.head(25).to_frame('codigos_distintos_no_fusionar_automaticamente'))

# %% [markdown]
# ## 5. Codificación y nomenclatura
# La lectura UTF-8 es estricta. Estas señales detectan posibles problemas, no prueban corrupción.
# Las claves sin tildes sirven para comparar; no se proponen como nombres finales del catálogo.

# %%
text_changes = pd.DataFrame({'espacios_externos': raw.ne(raw.apply(lambda s:s.str.strip())).sum(),
 'espacios_repetidos': raw.apply(lambda s:s.str.contains(r'\s{2,}',regex=True,na=False)).sum(),
 'posible_codificacion_incorrecta': raw.apply(lambda s:s.str.contains('�|Ã|Â',regex=True,na=False)).sum()})
display(text_changes.loc[text_changes.sum(axis=1)>0])
display(df.loc[df['Product ID'].str.match(r'^0\d+', na=False),['Product ID','Description']].drop_duplicates().head(20))

# %% [markdown]
# ## 6. Números: conversión explícita y errores visibles
# Un único separador seguido de tres cifras se considera ambiguo (1.234 / 1,234).
# No se asume decimal o miles. Se conservan originales y se reporta el error.
# Los floats se usan solo para estadísticas exploratorias; no para contabilidad.

# %%
numeric_fields = [c for c in ['Stock','Cost','Replacement Cost','CostoTotal','RETAILPRICE',
 'LOWRETAILPRICE','MSRP','MAXIMUMQTY','MINIMUMQTY','REORDERQTY'] if c in df]
def parse_number(value):
    if pd.isna(value): return np.nan, None
    s = str(value).strip()
    if re.fullmatch(r'[+-]?\d+',s): canonical = s
    elif re.fullmatch(r'[+-]?\d+[,.]\d+',s):
        if len(re.split('[,.]',s)[-1]) == 3: return np.nan, 'Separador ambiguo'
        canonical = s.replace(',','.')
    elif re.fullmatch(r'[+-]?\d{1,3}(?:\.\d{3})+,\d+',s): canonical = s.replace('.','').replace(',','.')
    elif re.fullmatch(r'[+-]?\d{1,3}(?:,\d{3})+\.\d+',s): canonical = s.replace(',','')
    else: return np.nan, 'Formato no reconocido'
    try:
        value = float(Decimal(canonical))
        return (value, None) if np.isfinite(value) else (np.nan, 'Fuera de rango')
    except (InvalidOperation, OverflowError): return np.nan, 'Conversión inválida'
numbers = pd.DataFrame(index=df.index)
numeric_errors = []
for column in numeric_fields:
    parsed = df[column].map(parse_number)
    numbers[column] = parsed.map(lambda v:v[0])
    for index, pair in parsed.items():
        if pair[1]: numeric_errors.append({'fila_excel':index,'columna':column,'original':df.at[index,column],'motivo':pair[1]})
numeric_errors = pd.DataFrame(numeric_errors, columns=['fila_excel','columna','original','motivo'])
display(numeric_errors.head(30))
display(numbers.describe(percentiles=[.01,.25,.5,.75,.95,.99]).T)
display(pd.DataFrame({'negativos':numbers.lt(0).sum(),'ceros':numbers.eq(0).sum(),
                      'ausentes_o_no_convertibles':numbers.isna().sum()}))

# %% [markdown]
# ## 7. Distribuciones y valores atípicos
# IQR es una alerta estadística, no una regla de eliminación. Se muestran todos los valores
# con escala simétrica logarítmica para no ocultar negativos ni grandes extremos.
# No se suman costos de distintas sedes: no hay moneda confirmada.

# %%
outliers = []
for column in numeric_fields:
    s = numbers[column].dropna()
    if s.empty: continue
    q1,q3 = s.quantile([.25,.75]); iqr = q3-q1
    flagged = (s < q1-1.5*iqr) | (s > q3+1.5*iqr) if iqr > 0 else pd.Series(False,index=s.index)
    outliers.append({'columna':column,'IQR':iqr,'alertas_IQR':int(flagged.sum()),'nota':'IQR cero: criterio no aplicado' if iqr==0 else 'Revisar, no eliminar'})
display(pd.DataFrame(outliers))
for column in [c for c in ['Stock','Cost','CostoTotal'] if c in numbers]:
    s=numbers[column].dropna()
    if not s.empty:
        plt.figure(); plt.scatter(np.arange(len(s)),s,s=4,alpha=.3,color='#286a87')
        plt.yscale('symlog'); plt.title(f'{column}: valores por registro — CSV completo')
        plt.xlabel('Orden de registros con dato numérico'); plt.ylabel(f'{column} (unidad/moneda de origen sin confirmar)')
        plt.tight_layout(); plt.show()
if {'Stock','Cost','CostoTotal'} <= set(numbers):
    reconciliation = numbers[['Stock','Cost','CostoTotal']].dropna().copy()
    reconciliation['calculado'] = reconciliation['Stock'] * reconciliation['Cost']
    reconciliation['diferencia'] = reconciliation['CostoTotal'] - reconciliation['calculado']
    display(reconciliation.loc[~np.isclose(reconciliation['CostoTotal'],reconciliation['calculado'],rtol=1e-6,atol=.01)].head(30))
    print('Diferencias son diagnósticas: no sustituir CostoTotal sin confirmar su definición.')

# %% [markdown]
# ## 8. Grupos originales, categorías y sitios
# Department y RevenueGroup son clasificaciones de origen, no familias canónicas.
# Los conteos por etiqueta incluyen códigos que podrían tener otra etiqueta en otra sede;
# no sumar estas cantidades como si fueran grupos mutuamente excluyentes.

# %%
groups = [c for c in ['Type','Package','ITEMCATEGORY','DEPARTMENT','REVENUEGROUP',
 'Report Group','EXCHANGEGROUP','INVENTORYGROUP','Availability Group'] if c in df]
for column in groups:
    print('\n',column)
    display(df.groupby(column,dropna=False).agg(filas=('Product ID','size'),codigos=('Product ID','nunique')).sort_values('filas',ascending=False).head(20))
site_profile = df.groupby(['SITEID','SITENAME'],dropna=False).agg(filas=('Product ID','size'),codigos=('Product ID','nunique'))
display(site_profile.sort_values('filas',ascending=False).head(20))
if {'DEPARTMENT','REVENUEGROUP'} <= set(df):
    display(pd.crosstab(df['DEPARTMENT'].fillna('(vacío)'),df['REVENUEGROUP'].fillna('(vacío)')))
print('País: no inferirlo del prefijo del código ni del sitio. Moneda: desconocida si no existe dato explícito.')

# %% [markdown]
# ## 9. Registros a revisar y las cinco C
# La falta de familia no demuestra que un producto sea desconocido. Se separan registros
# técnicos, identidad ausente, negativos y conflictos. No se realiza ninguna eliminación.
# Current: la fecha de carga es solo referencia provisional, no fecha de inventario confirmada.
# Correct: verificar con negocio/fichas; un EDA no certifica exactitud semántica.

# %%
domains = {'Type':{'ITEM','LABOR','PARTS','MISCCHARGE'}, 'Package':{'ITEM','PACKAGE'},
 'ITEMCATEGORY':{'SERIAL','NONSERIAL'},'CANRENT':{'RENTABLE','NOTRENTABLE'},
 'CANSELL':{'SELLABLE','NOTSELLABLE'},'CANSUBRENT':{'SUBRENT','NOTSUBRENT'}}
domain_errors = pd.DataFrame(index=df.index)
for column, allowed in domains.items():
    if column in df: domain_errors[column] = ~df[column].str.upper().isin(allowed)
display(domain_errors.sum().to_frame('filas_fuera_del_dominio_o_ausentes'))
technical_codes = {'DEFAULTITEM','DEFAULTLABOR','DEFAULTMISC','SYSTEMDEFAULT'}
review_flags = pd.DataFrame(index=df.index)
review_flags['codigo_tecnico'] = df['Product ID'].isin(technical_codes)
review_flags['falta_codigo'] = df['Product ID'].isna()
review_flags['falta_descripcion'] = df['Description'].isna()
review_flags['falta_sitio'] = df['SITEID'].isna()
review_flags['clave_repetida'] = df.index.isin(key_duplicates.index)
review_flags['conflicto_identidad'] = df['Product ID'].isin(conflicts.index)
review_flags['numero_negativo'] = numbers.lt(0).any(axis=1)
review_flags['numero_no_convertible'] = df.index.isin(numeric_errors['fila_excel'])
review_flags['dominio_invalido_o_ausente'] = domain_errors.any(axis=1)
review_queue = df.loc[review_flags.any(axis=1)].copy()
review_queue['motivos_revision'] = review_flags.loc[review_queue.index].apply(lambda r:'; '.join(r.index[r].tolist()),axis=1)
display(review_flags.sum().to_frame('filas_con_alerta_no_aditivas'))
display(review_queue.head(30))
five_c = pd.DataFrame([
 ('Clean','Espacios, vacíos y formatos', 'Ver perfil y errores; no imputar ni eliminar automáticamente'),
 ('Consistent','Claves, dominios y atributos por código','Examinar duplicados y contradicciones'),
 ('Current','Vigencia temporal','No verificable: carga provisional no acredita fecha de corte'),
 ('Correct','Exactitud de identidad y cifras','Requiere fuente autorizada y validación de negocio'),
 ('Comprehensive','Cobertura de campos y productos','Medida de nulos; cobertura externa no verificable solo con CSV')
],columns=['C','Dimensión','Interpretación'])
display(five_c)

# %% [markdown]
# ## 10. Exportación opcional de evidencia
# Cambiar EXPORTAR a True para guardar diagnósticos en una carpeta nueva junto al CSV.
# No sobrescribe el CSV ni ejecuta decisiones sobre SQLite. Registrar responsable y motivo
# antes de aprobar cualquier exclusión, fusión o cambio de familia.

# %%
EXPORTAR = False
if EXPORTAR:
    from datetime import datetime
    output = CSV_PATH.parent / ('resultados_eda_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    output.mkdir()
    for filename, table in {'perfil_columnas':profile,'errores_numericos':numeric_errors,
                            'conflictos_identidad':conflicts,'cola_revision':review_queue,
                            'duplicados_clave':key_duplicates}.items():
        table.to_csv(output / f'{filename}.csv',encoding='utf-8-sig',index=True)
    print('Diagnósticos guardados en',output)
else:
    print('Exportación desactivada. El análisis no cambió archivos de datos ni la base SQL.')
