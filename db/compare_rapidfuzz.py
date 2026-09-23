"""Comparación controlada de scores en idénticos pares, sin modificar decisiones."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.vendor'))
from rapidfuzz import fuzz, __version__
from db.matching import products,candidate_pairs,compare
from difflib import SequenceMatcher
import sqlite3
import json
from time import perf_counter
from statistics import median
from collections import Counter


def main():
    with sqlite3.connect('data/rla.sqlite3') as db:
        items=products(db,1)
    pairs,exact,coverage=candidate_pairs(items)
    pairs=sorted(pairs)
    texts=[(items[a]['description_key'],items[b]['description_key']) for a,b in pairs]
    methods={'SequenceMatcher':lambda a,b:100*SequenceMatcher(None,a,b,autojunk=False).ratio(),
             'RapidFuzz ratio':fuzz.ratio,'RapidFuzz token_sort_ratio':fuzz.token_sort_ratio}
    scores,times={},{}
    for name,method in methods.items():
        runs=[]
        for repeat in range(3):
            start=perf_counter()
            values=[round(method(a,b),1) for a,b in texts]
            runs.append(perf_counter()-start)
        scores[name]=values
        times[name]=round(median(runs),4)
    sets={name:{pair for pair,score in zip(pairs,values) if pair in exact or score>=80}
          for name,values in scores.items()}
    baseline=sets['SequenceMatcher']
    counts=[]
    for name,selected in sets.items():
        counts.append({'method':name,'selected':len(selected),'common':len(selected&baseline),
                       'added':len(selected-baseline),'removed':len(baseline-selected),
                       'median_seconds_3_runs':times[name]})
    rows=[]
    rapid_candidates=[]
    for i,(a,b) in enumerate(pairs):
        seq=scores['SequenceMatcher'][i]; ratio=scores['RapidFuzz ratio'][i]; token=scores['RapidFuzz token_sort_ratio'][i]
        if (a,b) in sets['RapidFuzz ratio']:
            rapid_candidates.append(compare(items[a],items[b],fuzz.ratio))
        if seq!=ratio or seq!=token:
            c=compare(items[a],items[b])
            c.update(sequence=seq,rapid_ratio=ratio,rapid_token_sort=token,
                     seq_selected=(a,b) in baseline,ratio_selected=(a,b) in sets['RapidFuzz ratio'],
                     token_selected=(a,b) in sets['RapidFuzz token_sort_ratio'],
                     exact_rule=(a,b) in exact,delta=round(ratio-seq,1))
            rows.append(c)
    rows.sort(key=lambda r:(r['seq_selected']==r['ratio_selected'],-abs(r['delta']),r['code_a'],r['code_b']))
    payload={'rapidfuzz_version':__version__,'load':1,'coverage':coverage,'methods':counts,
             'thresholds':{str(t):{name:sum(pair in exact or value>=t for pair,value in zip(pairs,values)) for name,values in scores.items()} for t in [75,80,85,90,95]},
             'changed_scores':len(rows),'examples':rows,
             'rapid_ratio_priorities':dict(Counter(r['priority'] for r in rapid_candidates))}
    out=Path('outputs/comparacion');out.mkdir(parents=True,exist_ok=True)
    (out/'comparacion.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'rapidfuzz_candidatos.json').write_text(json.dumps(rapid_candidates,ensure_ascii=False,indent=2),encoding='utf-8')
    template=Path('db/rapidfuzz_report.html').read_text(encoding='utf-8')
    (out/'comparacion.html').write_text(template.replace('/*DATA*/',json.dumps(payload,ensure_ascii=False).replace('<','\\u003c')),encoding='utf-8')
    assert len(baseline)==9920, 'La comparación ya no reproduce la línea base de carga 1'
    print(json.dumps({k:v for k,v in payload.items() if k!='examples'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
