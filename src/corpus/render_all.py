from __future__ import annotations
import json, sys, time, os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C

def _work(f: dict):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from corpus.build_corpus import process
    try:
        b = process(f)
    except Exception as e:
        return {'accession': f['accession'], 'ticker': f['ticker'], 'ok': False, 'err': str(e)[:200]}
    if not b:
        return {'accession': f['accession'], 'ticker': f['ticker'], 'ok': False, 'err': 'render failed'}
    return {'accession': f['accession'], 'ticker': f['ticker'], 'ok': True, 'pages': b['n_pages'], 'tables': len(b['tables']), 'spans': len(b['blocks']), 'facts': len(b['facts']), 'ixbrl': bool(b['has_ixbrl']), 'ahit': b['anchor_hits'], 'achk': b['anchor_checked']}

def main():
    idx = json.loads((C.RAW / 'filing_index.json').read_text())
    todo = [f for f in idx if not (C.FILINGS / f['ticker'] / f['accession'] / 'bundle.json').exists()]
    print(f'{len(todo)} filings to render ({len(idx) - len(todo)} already done)', flush=True)
    nw = int(os.environ.get('NW', '5'))
    t0 = time.time()
    ok = fail = pages = tables = spans = facts = ixbrl = ahit = achk = 0
    errs = []
    with ProcessPoolExecutor(max_workers=nw) as ex:
        futs = [ex.submit(_work, f) for f in todo]
        for i, fut in enumerate(as_completed(futs), 1):
            r = fut.result()
            if r['ok']:
                ok += 1
                pages += r['pages']
                tables += r['tables']
                spans += r['spans']
                facts += r['facts']
                ixbrl += r['ixbrl']
                ahit += r['ahit']
                achk += r['achk']
            else:
                fail += 1
                errs.append((r['ticker'], r['accession'], r['err']))
            if i % 10 == 0 or i == len(todo):
                el = time.time() - t0
                print(f'[{i}/{len(todo)}] ok={ok} fail={fail} pages={pages} tables={tables} facts={facts} ixbrl={ixbrl} anchor={100 * ahit / max(1, achk):.1f}% {el:.0f}s eta={el / i * (len(todo) - i) / 60:.0f}min', flush=True)
    print(f'DONE ok={ok} fail={fail} pages={pages} tables={tables} spans={spans} facts={facts} ixbrl_filings={ixbrl} anchor={100 * ahit / max(1, achk):.2f}%')
    for e in errs[:25]:
        print('  FAIL', e)
if __name__ == '__main__':
    main()
