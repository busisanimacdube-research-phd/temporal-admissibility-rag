from __future__ import annotations
import json, re, sys, statistics
from pathlib import Path
from collections import Counter
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C
_KEEP = re.compile('[^0-9a-z]+')
STRICT_MIN = 6
LABEL_CHARS = 40

def _norm(s: str) -> str:
    return _KEEP.sub('', (s or '').lower())

def audit_bundle(path: Path) -> dict:
    b = json.loads(path.read_text())
    npages = [_norm(p.get('text') or '') for p in b.get('pages', [])]
    c = Counter()
    spread = []
    for fa in b.get('facts', []):
        pg = fa.get('page')
        v = _norm(fa.get('raw_text') or '')
        if len(v) < 3 or not (isinstance(pg, int) and 1 <= pg <= len(npages)):
            continue
        on_page = v in npages[pg - 1]
        c['loose_n'] += 1
        c['loose_hit'] += on_page
        if len(v) >= STRICT_MIN:
            c['strict_n'] += 1
            c['strict_hit'] += on_page
            spread.append(sum((1 for t in npages if v in t)))
        lab = _norm(fa.get('row_text') or '')[:LABEL_CHARS]
        if len(v) >= STRICT_MIN and len(lab) >= 12:
            c['pair_n'] += 1
            c['pair_hit'] += on_page and lab in npages[pg - 1]
    return {'counts': dict(c), 'spread': spread}

def main():
    bundles = sorted(C.FILINGS.glob('*/*/bundle.json'))
    tot = Counter()
    spread_all = []
    for i, p in enumerate(bundles, 1):
        try:
            r = audit_bundle(p)
        except Exception as e:
            print(f'  skip {p.parent.name}: {type(e).__name__}', flush=True)
            continue
        tot.update(r['counts'])
        spread_all += r['spread']
        if i % 50 == 0 or i == len(bundles):
            print(f"  [{i}/{len(bundles)}] facts so far: {tot['loose_n']:,}", flush=True)

    def pct(h, n):
        return round(100.0 * tot[h] / tot[n], 1) if tot[n] else None
    out = {'n_filings': len(bundles), 'loose': {'n': tot['loose_n'], 'hits': tot['loose_hit'], 'acc': pct('loose_hit', 'loose_n')}, 'strict': {'n': tot['strict_n'], 'hits': tot['strict_hit'], 'acc': pct('strict_hit', 'strict_n'), 'min_chars': STRICT_MIN}, 'paired': {'n': tot['pair_n'], 'hits': tot['pair_hit'], 'acc': pct('pair_hit', 'pair_n'), 'label_chars': LABEL_CHARS}, 'pages_containing_fact_text': {'median': statistics.median(spread_all) if spread_all else None, 'mean': round(statistics.fmean(spread_all), 2) if spread_all else None, 'share_unique': round(100.0 * sum((1 for s in spread_all if s == 1)) / len(spread_all), 1) if spread_all else None}}
    (C.RESULTS / 'anchor_audit.json').write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
if __name__ == '__main__':
    main()
