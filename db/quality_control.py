"""Control documentado de una muestra: evaluación del asistente, no aprobación humana."""
from contextlib import closing
import json
from pathlib import Path
from db import operations as op

OBSERVATIONS={
 '11280':'Audífono de intérprete: confirmar si la política lo ubica en audio o interpretación simultánea.',
 '10763':'Imprevistos es un cargo, pero el origen declara ITEM. Confirmar tipo y alcance con negocio.',
 '11254':'Licencia OFFICE: revisar tratamiento como licencia y tipo ITEM frente a servicio/cargo.',
 'PE MISC07':'Licencia Windows: revisar tratamiento como licencia y tipo ITEM frente a servicio/cargo.'}


def main():
    with closing(op.connect()) as db:
        saved=op.backup(db); op.setup(db); op.ensure_sample(db,1)
        original=[json.loads(r[0]) for r in db.execute('SELECT original_json FROM quality_samples WHERE load_id=1')]
        current={r['legacy_code']:r for r in op.review_rows(db,1)}
        for code,reason in OBSERVATIONS.items():
            row=current[code]
            if row['status']=='approved_by_rule':
                op.save_review(db,dict(load_id=1,legacy_id=row['legacy_id'],revision=row['revision'],family_id=row['family_id'],
                    decision='pending',actor='Codex: control de muestra',reason=reason))
        rows=[]
        for r in original:
            rows.append({'code':r['legacy_code'],'description':r['standard_name'],'family':r['family'],
              'assessment':'requiere confirmación' if r['legacy_code'] in OBSERVATIONS else 'compatible con la descripción',
              'note':OBSERVATIONS.get(r['legacy_code'],'La descripción es compatible con la familia propuesta. No se verificaron ficha técnica, existencia física ni vigencia.'),
              'evidence':r['evidence']})
        result={'method':'Hasta 5 códigos por familia aplicada por regla; orden SHA256 estable por código. Revisión semántica por el asistente.',
          'load_id':1,'sample_size':len(rows),'families':len({r['family'] for r in rows}),
          'flagged':len(OBSERVATIONS),'human_approved':0,'accuracy_estimate':None,'backup':saved,'rows':rows}
        out=Path('outputs/catalogo/control_muestra.json');out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=True))


if __name__=='__main__': main()
