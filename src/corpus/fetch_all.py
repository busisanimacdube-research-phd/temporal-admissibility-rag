from __future__ import annotations
import json, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C
from corpus.sec_client import get
from corpus.render import filing_dir

def fetch_one(f: dict) -> tuple[str, bool, int]:
    d = filing_dir(f)
    d.mkdir(parents=True, exist_ok=True)
    p = d / 'primary.htm'
    if p.exists() and p.stat().st_size > 5000:
        return (f['accession'], True, p.stat().st_size)
    try:
        p.write_text(get(f['url']), encoding='utf-8')
        return (f['accession'], True, p.stat().st_size)
    except Exception:
        p.unlink(missing_ok=True)
        return (f['accession'], False, 0)

def main():
    idx = json.loads((C.RAW / 'filing_index.json').read_text())
    t0, ok, fail, nbytes = (time.time(), 0, 0, 0)
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(fetch_one, f): f for f in idx}
        for i, fut in enumerate(as_completed(futs), 1):
            accn, good, sz = fut.result()
            ok += good
            fail += not good
            nbytes += sz
            if i % 25 == 0 or i == len(idx):
                print(f'[{i}/{len(idx)}] ok={ok} fail={fail} {nbytes / 1000000000.0:.2f} GB {time.time() - t0:.0f}s', flush=True)
    print(f'DONE ok={ok} fail={fail}')
if __name__ == '__main__':
    main()
