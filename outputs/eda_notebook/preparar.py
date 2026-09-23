from pathlib import Path
import sqlite3,json,hashlib
import pandas as pd
import io, contextlib, base64
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

base=Path(__file__).resolve().parent
root=base.parents[1]
with sqlite3.connect(f'file:{(root / "data/rla_modelo_v4.sqlite3").as_posix()}?mode=ro',uri=True) as db:
    rows=[json.loads(r[0]) for r in db.execute('SELECT raw_json FROM raw_records WHERE load_id=1 ORDER BY excel_row')]
    load=db.execute('SELECT filename,sha256,received_at FROM loads WHERE load_id=1').fetchone()
frame=pd.DataFrame(rows)
csv=base/'Lista_Productos_original.csv'
frame.to_csv(csv,index=False,encoding='utf-8-sig')
check=pd.read_csv(csv,dtype='string',keep_default_na=False,encoding='utf-8-sig')
assert check.shape==(57011,42)
assert check.astype(str).equals(frame.fillna('').astype(str))
manifest={'source_file':load[0],'source_sha256':load[1],'load_id':1,'received_at':load[2],
 'reference_date_basis':'received_at provisional; no fecha de inventario confirmada',
 'export_source':'raw_records.raw_json: originales de carga 1, orden excel_row',
 'rows':len(frame),'columns':len(frame.columns),'excluded_rows':0,
 'csv_sha256':hashlib.sha256(csv.read_bytes()).hexdigest()}
(base/'procedencia.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
source=(base/'EDA_Productos.py').read_text(encoding='utf-8')
cells=[]
for block in source.split('# %%')[1:]:
    header,_,body=block.partition('\n')
    if '[markdown]' in header:
        cells.append({'cell_type':'markdown','metadata':{},'source':'\n'.join(line[2:] if line.startswith('# ') else '' if line=='#' else line for line in body.strip().splitlines())})
    else:cells.append({'cell_type':'code','metadata':{},'source':body.strip(),'outputs':[],'execution_count':None})
scope={'__file__':str(base/'EDA_Productos.py')}
count=0
for cell in cells:
    if cell['cell_type']!='code': continue
    count+=1; cell['execution_count']=count; outputs=cell['outputs']
    def display(value):
        data={'text/plain':repr(value)}
        if hasattr(value,'to_html'): data['text/html']=value.to_html()
        outputs.append({'output_type':'display_data','data':data,'metadata':{}})
    def show():
        for num in plt.get_fignums():
            buffer=io.BytesIO(); plt.figure(num).savefig(buffer,format='png',bbox_inches='tight')
            outputs.append({'output_type':'display_data','data':{'image/png':base64.b64encode(buffer.getvalue()).decode(),'text/plain':'Gráfico EDA'},'metadata':{}})
        plt.close('all')
    scope['display']=display; plt.show=show
    code=cell['source'].replace('from IPython.display import display','# display proporcionado por el ejecutor de verificación')
    stream=io.StringIO()
    with contextlib.redirect_stdout(stream): exec(compile(code,'EDA_Productos.py','exec'),scope)
    if stream.getvalue():outputs.append({'output_type':'stream','name':'stdout','text':stream.getvalue()})
nb={'nbformat':4,'nbformat_minor':4,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'language_info':{'name':'python','version':'3.12'}},'cells':cells}
(base/'EDA_Productos.ipynb').write_text(json.dumps(nb,ensure_ascii=False,indent=1),encoding='utf-8')
(base/'requirements.txt').write_text('pandas\nnumpy\nmatplotlib\nipykernel\n',encoding='utf-8')
(base/'LEEME.txt').write_text('Abrir EDA_Productos.ipynb con VS Code y seleccionar un kernel Python.\nAlternativa: EDA_Productos.py tiene celdas # %% con Run Cell.\nMantener el CSV y procedencia.json junto al notebook. Ejecutar de arriba hacia abajo.\nSi falta una biblioteca: python -m pip install -r requirements.txt\nEl notebook incluye resultados ejecutados. No elimina registros ni modifica SQLite.\n',encoding='utf-8')
print(json.dumps({'shape':check.shape,'cells':len(cells),'executed':count}))
