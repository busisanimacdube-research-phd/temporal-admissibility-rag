from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kg import schema as S
SPAN, TABLE, PAGE, FACT = ('span', 'table', 'page', 'fact')

def _fact_sentence(n: dict) -> str:
    per = f"for the period {n['valid_start']} to {n['valid_end']}" if n.get('valid_start') else f"as at {n.get('valid_end')}"
    fy = ''
    if n.get('fy'):
        fy = f" ({n.get('fp') or ''} FY{n['fy']})".replace('  ', ' ')
    unit = n.get('unit') or ''
    val = n.get('value')
    vs = f'{val:,.2f}' if isinstance(val, (int, float)) else str(val)
    row = f" Statement line: {n['row_text']}." if n.get('row_text') else ''
    return f"{n['company']} {n.get('label') or n['concept']} ({n['concept']}) {per}{fy}: {vs} {unit}.{row}"

def build_units(g, company: str | None=None, max_spans_per_filing: int=120) -> list[dict]:
    units, per_filing_spans = ([], {})
    for nid, n in g.nodes.items():
        t = n.get('_type')
        if t not in (S.SPAN, S.TABLE, S.PAGE, S.FACT):
            continue
        if company and n.get('company') != company:
            continue
        if t == S.SPAN:
            k = n.get('accession')
            per_filing_spans[k] = per_filing_spans.get(k, 0) + 1
            if per_filing_spans[k] > max_spans_per_filing:
                continue
            text = n.get('text', '')
            kind = SPAN
        elif t == S.TABLE:
            text = n.get('text', '')
            kind = TABLE
        elif t == S.PAGE:
            text = n.get('text', '')
            kind = PAGE
        else:
            text = _fact_sentence(n)
            kind = FACT
        if not text or len(text) < 30:
            continue
        units.append({'uid': nid, 'kind': kind, 'text': text[:3000], 'company': n.get('company'), 'accession': n.get('accession'), 'page': n.get('page'), 'asserted_at': n.get('asserted_at'), 'image': n.get('image') if t == S.PAGE else None, 'concept': n.get('concept'), 'value': n.get('value'), 'valid_key': n.get('valid_key'), 'unit': n.get('unit')})
    return units
