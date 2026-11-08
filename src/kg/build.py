from __future__ import annotations
import json, sys, re, time
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C
from kg import schema as S
from kg.graph import EvidenceGraph

def valid_key(start, end) -> str:
    return f"{start or 'instant'}/{end}"

def _fact_join_key(concept, start, end, val) -> tuple:
    try:
        v = round(float(val), 2)
    except (TypeError, ValueError):
        v = None
    return (concept, start or None, end or None, v)

def load_bundles(tickers=None):
    for tdir in sorted(C.FILINGS.iterdir()):
        if not tdir.is_dir() or (tickers and tdir.name not in tickers):
            continue
        for fdir in sorted(tdir.iterdir()):
            bp = fdir / 'bundle.json'
            if bp.exists():
                try:
                    yield json.loads(bp.read_text())
                except Exception:
                    continue

def build(tickers=None, max_spans_per_filing=400, verbose=True) -> EvidenceGraph:
    g = EvidenceGraph()
    t0 = time.time()
    facts = [json.loads(l) for l in (C.XBRL / 'facts.jsonl').read_text().splitlines()]
    if tickers:
        facts = [f for f in facts if f['ticker'] in tickers]
    periods, concepts, companies = (set(), set(), set())
    fact_by_accn = defaultdict(dict)
    for i, r in enumerate(facts):
        tk, cn = (r['ticker'], r['concept'])
        vk = valid_key(r['start'], r['end'])
        fid = f"F:{tk}:{cn}:{vk}:{r['accn']}:{r['unit']}"
        if fid in g.nodes:
            continue
        g.add_node(fid, S.FACT, company=tk, concept=cn, label=r['label'], unit=r['unit'], value=r['val'], valid_start=r['start'], valid_end=r['end'], valid_key=vk, asserted_at=r['asserted_at'], accession=r['accn'], form=r['form'], fy=r.get('fy'), fp=r.get('fp'), modality='structured')
        companies.add(tk)
        concepts.add(cn)
        periods.add(vk)
        fact_by_accn[r['accn']][_fact_join_key(cn, r['start'], r['end'], r['val'])] = fid
    for tk in companies:
        g.add_node(f'C:{tk}', S.COMPANY, ticker=tk)
    for cn in concepts:
        g.add_node(f'K:{cn}', S.CONCEPT, concept=cn)
    for vk in periods:
        st, en = vk.split('/', 1)
        g.add_node(f'P:{vk}', S.PERIOD, valid_key=vk, start=None if st == 'instant' else st, end=en)
    for fid in list(g.by_type[S.FACT]):
        f = g.nodes[fid]
        g.add_edge(fid, S.OF_CONCEPT, f"K:{f['concept']}")
        g.add_edge(fid, S.COVERS, f"P:{f['valid_key']}")
        g.add_edge(fid, S.ABOUT, f"C:{f['company']}")
    if verbose:
        print(f'  facts      {len(g.by_type[S.FACT]):7d}  ({time.time() - t0:.0f}s)', flush=True)
    n_bind = n_pages = n_tables = n_spans = n_filings = 0
    for b in load_bundles(tickers):
        accn, tk = (b['accession'], b['ticker'])
        at = b['acceptance_datetime']
        fl = f'L:{accn}'
        g.add_node(fl, S.FILING, company=tk, accession=accn, form=b['form'], filing_date=b['filing_date'], asserted_at=at, report_date=b['report_date'], url=b['url'], n_pages=b['n_pages'])
        if f'C:{tk}' in g.nodes:
            g.add_edge(f'C:{tk}', S.FILES, fl)
        n_filings += 1
        page_id = {}
        for p in b['pages']:
            pid = f"G:{accn}:{p['page']}"
            g.add_node(pid, S.PAGE, company=tk, accession=accn, page=p['page'], image=p['image'], asserted_at=at, n_chars=p['n_chars'], text=p['text'][:6000], modality='visual')
            g.add_edge(fl, S.CONTAINS, pid)
            page_id[p['page']] = pid
            n_pages += 1
        tbl_id = {}
        for t in b['tables']:
            if t['n_rows'] < 2 or t['n_cols'] < 2:
                continue
            tid = f"T:{accn}:{t['table_idx']}"
            g.add_node(tid, S.TABLE, company=tk, accession=accn, table_idx=t['table_idx'], page=t.get('page', 1), n_rows=t['n_rows'], n_cols=t['n_cols'], text=t['text'][:4000], rows=t['rows'][:40], asserted_at=at, modality='table')
            g.add_edge(fl, S.CONTAINS, tid)
            if t.get('page') in page_id:
                g.add_edge(tid, S.RENDERED_ON, page_id[t['page']])
            tbl_id[t['table_idx']] = tid
            n_tables += 1
        for j, blk in enumerate(b['blocks'][:max_spans_per_filing]):
            if len(blk['text']) < 80:
                continue
            sid = f'S:{accn}:{j}'
            g.add_node(sid, S.SPAN, company=tk, accession=accn, page=blk.get('page', 1), text=blk['text'][:3000], asserted_at=at, modality='text')
            g.add_edge(fl, S.CONTAINS, sid)
            if blk.get('page') in page_id:
                g.add_edge(sid, S.RENDERED_ON, page_id[blk['page']])
            n_spans += 1
        joinable = fact_by_accn.get(accn, {})
        for xf in b['facts']:
            if xf.get('table_idx') is None or xf.get('value') is None:
                continue
            fid = joinable.get(_fact_join_key(xf['concept'], xf.get('start'), xf.get('end'), xf['value']))
            if fid is None:
                continue
            tid = tbl_id.get(xf['table_idx'])
            if tid is None:
                continue
            g.add_edge(fid, S.DISPLAYED_IN, tid)
            n = g.nodes[fid]
            n['cell'] = [xf['table_idx'], xf.get('row_idx'), xf.get('col_idx')]
            n['page'] = xf.get('page')
            n['row_text'] = xf.get('row_text')
            n['displayed'] = xf.get('raw_text')
            pid = page_id.get(xf.get('page'))
            if pid:
                g.add_edge(fid, S.RENDERED_ON, pid)
            n_bind += 1
    if verbose:
        print(f'  filings    {n_filings:7d}\n  pages      {n_pages:7d}\n  tables     {n_tables:7d}\n  spans      {n_spans:7d}\n  cmeb binds {n_bind:7d}  ({time.time() - t0:.0f}s)', flush=True)
    g.finalize()
    n_sup = n_eq = 0
    for key, chain in g.assertion_chain.items():
        for a, b_ in zip(chain, chain[1:]):
            va, vb = (g.nodes[a].get('value'), g.nodes[b_].get('value'))
            g.add_edge(b_, S.SUPERSEDES, a)
            n_sup += 1
            if va is not None and vb is not None and (abs(va - vb) < 1e-06):
                g.add_edge(a, S.EQUIV, b_)
                g.add_edge(b_, S.EQUIV, a)
                n_eq += 2
            else:
                g.nodes[b_]['revises'] = True
    per = sorted(g.by_type[S.PERIOD], key=lambda p: g.nodes[p]['end'] or '')
    for a, b_ in zip(per, per[1:]):
        g.add_edge(a, S.PRECEDES, b_)
    g.finalize()
    if verbose:
        print(f'  supersedes {n_sup:7d}\n  equivalent {n_eq:7d}  ({time.time() - t0:.0f}s)', flush=True)
    return g
if __name__ == '__main__':
    tks = sys.argv[1].split(',') if len(sys.argv) > 1 and sys.argv[1] != 'ALL' else None
    g = build(tks)
    st = g.stats()
    print(json.dumps(st, indent=1))
    out = C.KG / ('graph.json.gz' if not tks else f"graph_{'_'.join(tks)}.json.gz")
    g.save(out)
    print('saved', out, f'{out.stat().st_size / 1000000.0:.1f} MB')
