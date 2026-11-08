from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C
from corpus.sec_client import get_json, ticker_to_cik

def filings_for(cik: str) -> list[dict]:
    d = get_json(f'https://data.sec.gov/submissions/CIK{cik}.json')
    name = d['name']
    blocks = [d['filings']['recent']]
    for extra in d['filings'].get('files', []):
        blocks.append(get_json(f"https://data.sec.gov/submissions/{extra['name']}"))
    out = []
    for r in blocks:
        n = len(r['form'])
        for i in range(n):
            if r['form'][i] not in C.FORMS:
                continue
            fdate = r['filingDate'][i]
            if not C.YEAR_MIN <= int(fdate[:4]) <= C.YEAR_MAX:
                continue
            if not r['primaryDocument'][i].endswith(('.htm', '.html')):
                continue
            accn = r['accessionNumber'][i]
            out.append({'cik': cik, 'company': name, 'form': r['form'][i], 'accession': accn, 'accession_nodash': accn.replace('-', ''), 'filing_date': fdate, 'acceptance_datetime': r['acceptanceDateTime'][i], 'report_date': r['reportDate'][i], 'primary_doc': r['primaryDocument'][i], 'is_xbrl': bool(r['isXBRL'][i]), 'size': r['size'][i]})
    return out

def main():
    t2c = ticker_to_cik()
    index = []
    for tk in C.TICKERS:
        cik = C.CIK_OVERRIDE.get(tk, t2c[tk])
        fs = filings_for(cik)
        for f in fs:
            f['ticker'] = tk
            f['url'] = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{f['accession_nodash']}/{f['primary_doc']}"
        index.extend(fs)
        print(f"{tk:6s} cik={cik} filings={len(fs):3d} ({sum((1 for x in fs if x['form'] == '10-K'))} 10-K / {sum((1 for x in fs if x['form'] == '10-Q'))} 10-Q)", flush=True)
    index.sort(key=lambda x: (x['ticker'], x['acceptance_datetime']))
    out = C.RAW / 'filing_index.json'
    out.write_text(json.dumps(index, indent=1))
    print(f'\nTOTAL {len(index)} filings -> {out}')
    print(f"total bytes {sum((f['size'] for f in index)) / 1000000000.0:.2f} GB")
if __name__ == '__main__':
    main()
