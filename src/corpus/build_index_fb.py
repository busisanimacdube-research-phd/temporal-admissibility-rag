from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C
from corpus.sec_client import get_json, ticker_to_cik
from corpus.build_index import filings_for

def main():
    idx_path = C.RAW / 'filing_index.json'
    existing = json.loads(idx_path.read_text())
    have = {f['accession'] for f in existing}
    primary = {f['ticker'] for f in existing}
    print(f'existing index: {len(existing)} filings over {len(primary)} companies')
    t2c = ticker_to_cik()
    added, missing = ([], [])
    lo, hi = (C.YEAR_MIN, C.YEAR_MAX)
    C.YEAR_MIN, C.YEAR_MAX = (C.FB_YEAR_MIN, C.FB_YEAR_MAX)
    try:
        for tk in C.FB_TICKERS:
            cik = C.CIK_OVERRIDE.get(tk, t2c.get(tk))
            if cik is None:
                missing.append(tk)
                print(f'  {tk:6s} ticker not found in SEC index')
                continue
            fs = [f for f in filings_for(cik) if f['accession'] not in have]
            for f in fs:
                f['ticker'] = tk
                f['external_only'] = True
                f['url'] = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{f['accession_nodash']}/{f['primary_doc']}"
            added += fs
            print(f'  {tk:6s} cik={cik} +{len(fs):3d} filings', flush=True)
    finally:
        C.YEAR_MIN, C.YEAR_MAX = (lo, hi)
    out = existing + added
    out.sort(key=lambda x: (x['ticker'], x['acceptance_datetime']))
    idx_path.write_text(json.dumps(out, indent=1))
    print(f"\nadded {len(added)} filings; index now {len(out)} over {len({f['ticker'] for f in out})} companies")
    if missing:
        print(f'unresolved tickers: {missing}')
if __name__ == '__main__':
    main()
