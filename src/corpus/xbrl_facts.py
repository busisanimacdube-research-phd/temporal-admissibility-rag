from __future__ import annotations
import json, sys, collections
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C
from corpus.sec_client import get_json, ticker_to_cik
CORE_CONCEPTS = ['Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax', 'RevenueFromContractWithCustomerIncludingAssessedTax', 'CostOfRevenue', 'CostOfGoodsAndServicesSold', 'GrossProfit', 'OperatingIncomeLoss', 'OperatingExpenses', 'ResearchAndDevelopmentExpense', 'SellingGeneralAndAdministrativeExpense', 'NetIncomeLoss', 'ProfitLoss', 'EarningsPerShareBasic', 'EarningsPerShareDiluted', 'Assets', 'AssetsCurrent', 'Liabilities', 'LiabilitiesCurrent', 'StockholdersEquity', 'CashAndCashEquivalentsAtCarryingValue', 'InventoryNet', 'AccountsReceivableNetCurrent', 'LongTermDebtNoncurrent', 'LongTermDebt', 'DebtCurrent', 'NetCashProvidedByUsedInOperatingActivities', 'NetCashProvidedByUsedInInvestingActivities', 'NetCashProvidedByUsedInFinancingActivities', 'PaymentsToAcquirePropertyPlantAndEquipment', 'IncomeTaxExpenseBenefit', 'InterestExpense', 'CommonStockSharesOutstanding', 'PropertyPlantAndEquipmentNet']

def load_index():
    idx = json.loads((C.RAW / 'filing_index.json').read_text())
    by_accn = {f['accession']: f for f in idx}
    return (idx, by_accn)

def harvest(cik: str, ticker: str, by_accn: dict) -> list[dict]:
    d = get_json(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json')
    us = d.get('facts', {}).get('us-gaap', {})
    dei = d.get('facts', {}).get('dei', {})
    recs = []
    for concept in CORE_CONCEPTS:
        node = us.get(concept) or dei.get(concept)
        if not node:
            continue
        label = node.get('label') or concept
        for unit, rows in node['units'].items():
            for r in rows:
                if r.get('form') not in C.FORMS:
                    continue
                accn = r.get('accn')
                src = by_accn.get(accn)
                asserted = src['acceptance_datetime'] if src else f"{r['filed']}T23:59:59.000Z"
                recs.append({'ticker': ticker, 'cik': cik, 'concept': concept, 'label': label, 'unit': unit, 'start': r.get('start'), 'end': r['end'], 'val': r['val'], 'fy': r.get('fy'), 'fp': r.get('fp'), 'form': r['form'], 'frame': r.get('frame'), 'accn': accn, 'filed': r['filed'], 'asserted_at': asserted, 'in_corpus': src is not None})
    return recs

def main():
    idx, by_accn = load_index()
    t2c = ticker_to_cik()
    tickers = list(C.TICKERS) + [t for t in getattr(C, 'FB_TICKERS', []) if t not in C.TICKERS]
    all_recs = []
    for tk in tickers:
        cik = C.CIK_OVERRIDE.get(tk) or t2c.get(tk)
        if cik is None:
            print(f'{tk:6s} no CIK; skipped')
            continue
        recs = harvest(cik, tk, by_accn)
        g = collections.defaultdict(set)
        for r in recs:
            g[r['concept'], r['unit'], r['start'], r['end']].add(round(float(r['val']), 4))
        revised = sum((1 for v in g.values() if len(v) > 1))
        print(f'{tk:6s} facts={len(recs):6d} periods={len(g):5d} value-revised={revised:4d}', flush=True)
        all_recs.extend(recs)
    out = C.XBRL / 'facts.jsonl'
    with out.open('w') as fh:
        for r in all_recs:
            fh.write(json.dumps(r) + '\n')
    print(f'\nTOTAL {len(all_recs)} fact assertions -> {out}')
if __name__ == '__main__':
    main()
