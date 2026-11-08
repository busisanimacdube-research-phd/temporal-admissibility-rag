from __future__ import annotations
import json, sys, time, argparse, traceback
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C
from kg.build import build
from systems.base import CompanyContext
from systems.baselines import ClosedBookLLM, BM25RAG, DenseRAG, HybridRAG, TimeFilteredRAG, VisRAG, M3DocRAG
from systems.kg_baselines import LightRAG, HippoRAG
from systems.tempfinrag import TempFinRAG
from eval.metrics import score_item, aggregate
REGISTRY = {'closedbook': ClosedBookLLM, 'bm25': BM25RAG, 'dense': DenseRAG, 'hybrid': HybridRAG, 'timefiltered': TimeFilteredRAG, 'visrag': VisRAG, 'm3docrag': M3DocRAG, 'lightrag': LightRAG, 'hipporag': HippoRAG, 'tempfinrag': TempFinRAG}
MAIN = ['closedbook', 'bm25', 'dense', 'hybrid', 'timefiltered', 'lightrag', 'hipporag', 'visrag', 'm3docrag', 'tempfinrag']

def load_items(split: str | None, limit: int | None, families=None, bench: str='questions.jsonl'):
    items = [json.loads(l) for l in (C.BENCH / bench).read_text().splitlines()]
    if split:
        items = [i for i in items if i['split'] == split]
    if families:
        items = [i for i in items if i['family'] in families]
    if limit:
        by_fam = defaultdict(list)
        for i in items:
            by_fam[i['family']].append(i)
        per = max(1, limit // max(1, len(by_fam)))
        items = [x for fam in by_fam.values() for x in fam[:per]][:limit]
    return items

def contexts_for(items, dense=True):
    comps = sorted({i['company'] for i in items})
    print(f"building graph + indexes for {len(comps)} companies: {', '.join(comps)}", flush=True)
    gt = time.time()
    g = build(comps, verbose=False)
    print(f"  graph: {g.stats()['n_nodes']:,} nodes {g.stats()['n_edges']:,} edges ({time.time() - gt:.0f}s)", flush=True)
    ctxs = {}
    for c in comps:
        t = time.time()
        ctxs[c] = CompanyContext(g, c, dense=dense)
        print(f'  {c}: {len(ctxs[c].units):6d} units ({time.time() - t:.0f}s)', flush=True)
    return ctxs

def run_system(key: str, items, ctxs, out_dir: Path, resume=True):
    sysobj = REGISTRY[key]()
    if sysobj.restrict_families:
        keep = [i for i in items if i['family'] in sysobj.restrict_families]
        print(f'[{sysobj.name}] defined over {len(sysobj.restrict_families)} families: {len(keep)} of {len(items)} items', flush=True)
        items = keep
    out_path = out_dir / f'{key}.jsonl'
    done = set()
    if resume and out_path.exists():
        for l in out_path.read_text().splitlines():
            try:
                done.add(json.loads(l)['qid'])
            except Exception:
                pass
    todo = [i for i in items if i['qid'] not in done]
    print(f'[{sysobj.name}] {len(todo)} to run ({len(done)} cached)', flush=True)
    t0 = time.time()
    with out_path.open('a') as fh:
        for n, it in enumerate(todo, 1):
            try:
                pred = sysobj.answer(it, ctxs[it['company']])
            except Exception:
                print(f"  ERR {it['qid']}: {traceback.format_exc(limit=1)}", flush=True)
                pred = {'answer': None, 'abstain': False, 'units': [], 'citations': [], 'latency': 0.0, 'error': True}
            row = score_item(it, pred)
            row['pred'] = str(pred.get('answer'))[:200]
            row['abstain'] = bool(pred.get('abstain'))
            row['uids'] = [u['uid'] for u in pred.get('units') or []]
            fh.write(json.dumps(row) + '\n')
            fh.flush()
            if n % 10 == 0 or n == len(todo):
                el = time.time() - t0
                print(f'  [{n}/{len(todo)}] {el:.0f}s  {el / n:.1f}s/q  eta {el / n * (len(todo) - n) / 60:.0f}min', flush=True)
    rows = [json.loads(l) for l in out_path.read_text().splitlines()]
    rows = [r for r in rows if r['qid'] in {i['qid'] for i in items}]
    return aggregate(rows)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--split', default='test')
    ap.add_argument('--limit', type=int, default=None)
    ap.add_argument('--systems', default='main')
    ap.add_argument('--tag', default='main')
    ap.add_argument('--bench', default='questions.jsonl', help='benchmark file under data/questions (e.g. the paraphrased split)')
    ap.add_argument('--no-cache', action='store_true', help='bypass the generation cache so latency is measured rather than inherited from a previous run')
    a = ap.parse_args()
    keys = {'main': MAIN, 'all': list(REGISTRY)}.get(a.systems, a.systems.split(','))
    if a.no_cache:
        import systems.llm as _llm
        _gen = _llm.generate
        _llm.generate = lambda *ar, **kw: _gen(*ar, **{**kw, 'use_cache': False})
        print('generation cache bypassed: latencies are measured\n', flush=True)
    items = load_items(a.split, a.limit, bench=a.bench)
    print(f'{len(items)} items from {a.bench} split={a.split}', flush=True)
    print(f"frozen config: {C.FROZEN or 'NONE -- using defaults, nothing frozen'}")
    print(f'  TOP_K={C.TOP_K} NEAR_DAYS={C.NEAR_DAYS} MAX_UNITS={C.MAX_UNITS}\n', flush=True)
    ctxs = contexts_for(items)
    out_dir = C.RESULTS / a.tag / a.split
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {}
    for k in keys:
        summary[k] = run_system(k, items, ctxs, out_dir)
        s = summary[k]
        print(f"  -> acc={s['acc']:.3f} er={s['er'] or 0:.3f} mer={s['mer'] or 0:.3f} tlr={s['tlr']:.3f} hr={s['hr'] or 0:.3f}\n", flush=True)
        (out_dir / 'summary.json').write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
if __name__ == '__main__':
    main()
