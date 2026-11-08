from __future__ import annotations
import json, sys, random, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C
from kg.graph import EvidenceGraph
from kg import schema as S
from kg.build import build
from bench.generate import Generator
from bench.families import FAMILIES, FAMILY_LABEL, F1, F2, F3, F4, F5, F6, F7
SPLIT_COMPANIES = {'dev': ['AAPL', 'MSFT', 'AMZN', 'GOOGL', 'META', 'NVDA', 'JPM', 'KO', 'PG', 'CSCO'], 'val': ['WMT', 'XOM', 'INTC', 'VZ'], 'test': ['TSLA', 'BAC', 'JNJ', 'PFE', 'DIS', 'CVX']}
QUOTA = {'test': {F1: 80, F2: 400, F3: 60, F4: 60, F5: 60, F6: 40, F7: 40}, 'val': {F1: 40, F2: 400, F3: 30, F4: 30, F5: 30, F6: 20, F7: 20}, 'dev': {F1: 40, F2: 400, F3: 30, F4: 30, F5: 30, F6: 20, F7: 20}}
GEN = {F1: 'gen_fact_at_date', F2: 'gen_restatement', F3: 'gen_period_comparison', F4: 'gen_ratio', F5: 'gen_crossmodal', F6: 'gen_multihop', F7: 'gen_unanswerable'}

def build_split(name: str, graph_path: Path | None=None) -> list[dict]:
    comps = SPLIT_COMPANIES[name]
    g = build(comps, verbose=False)
    gen = Generator(g, seed=C.SEED + hash(name) % 1000)
    for fam, n in QUOTA[name].items():
        made = getattr(gen, GEN[fam])(n)
        print(f'  {name:4s} {FAMILY_LABEL[fam]:28s} requested {n:4d}  produced {made:4d}', flush=True)
    for it in gen.items:
        it['split'] = name
        it['qid'] = f"pf-{name}-{it['qid'].split('-')[-1]}"
    return (gen.items, g)

def main():
    all_items = []
    stats = {}
    for split in ('dev', 'val', 'test'):
        print(f"[{split}] companies: {', '.join(SPLIT_COMPANIES[split])}", flush=True)
        items, g = build_split(split)
        all_items += items
        stats[split] = {'n': len(items), 'graph': g.stats()}
        print(f'  -> {len(items)} items\n', flush=True)
    random.Random(C.SEED).shuffle(all_items)
    out = C.BENCH / 'questions.jsonl'
    with out.open('w') as fh:
        for it in all_items:
            fh.write(json.dumps(it) + '\n')
    ids = collections.Counter((i['qid'] for i in all_items))
    clash = [q for q, n in ids.items() if n > 1]
    assert not clash, f'duplicate question ids after namespacing: {clash[:5]}'
    fam = collections.Counter(((i['split'], i['family']) for i in all_items))
    print(f'TOTAL {len(all_items)} items -> {out}')
    print(f"{'family':30s} {'dev':>6s} {'val':>6s} {'test':>6s} {'all':>6s}")
    for f in FAMILIES:
        r = [fam[s, f] for s in ('dev', 'val', 'test')]
        print(f'{FAMILY_LABEL[f]:30s} {r[0]:6d} {r[1]:6d} {r[2]:6d} {sum(r):6d}')
    tot = [sum((fam[s, f] for f in FAMILIES)) for s in ('dev', 'val', 'test')]
    print(f"{'TOTAL':30s} {tot[0]:6d} {tot[1]:6d} {tot[2]:6d} {sum(tot):6d}")
    (C.BENCH / 'stats.json').write_text(json.dumps(stats, indent=1))
if __name__ == '__main__':
    main()
