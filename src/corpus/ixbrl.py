from __future__ import annotations
import re
from lxml import etree
XBRLI = 'http://www.xbrl.org/2003/instance'
_WS = re.compile('\\s+')

def _ln(el) -> str:
    try:
        return etree.QName(el).localname
    except ValueError:
        return str(el.tag)

def _txt(el) -> str:
    return _WS.sub(' ', ''.join(el.itertext())).strip()

def parse_contexts(doc) -> dict[str, dict]:
    out = {}
    for c in doc.xpath("//*[local-name()='context']"):
        cid = c.get('id')
        if not cid:
            continue
        rec = {'start': None, 'end': None, 'instant': None, 'dims': {}}
        for p in c.iter():
            n = _ln(p)
            if n == 'startDate':
                rec['start'] = (p.text or '').strip()
            elif n == 'endDate':
                rec['end'] = (p.text or '').strip()
            elif n == 'instant':
                rec['instant'] = (p.text or '').strip()
            elif n == 'explicitMember':
                dim = p.get('dimension', '')
                rec['dims'][dim.split(':')[-1]] = (p.text or '').strip().split(':')[-1]
        out[cid] = rec
    return out

def _numeric(el) -> float | None:
    raw = _txt(el).replace(',', '').replace('$', '').replace('%', '').strip()
    if raw in ('', '-', '—', '–'):
        return None
    neg = raw.startswith('(') and raw.endswith(')')
    raw = raw.strip('()')
    try:
        v = float(raw)
    except ValueError:
        return None
    try:
        v *= 10 ** int(el.get('scale') or 0)
    except ValueError:
        pass
    if el.get('sign') == '-' or neg:
        v = -v
    return v

def extract(html_bytes: bytes) -> dict:
    doc = etree.fromstring(html_bytes, etree.XMLParser(recover=True, huge_tree=True))
    contexts = parse_contexts(doc)
    _alive = list(doc.iter())
    order = {id(el): i for i, el in enumerate(_alive)}
    tables, tbl_id = ([], {})
    MAX_ROWS, MAX_COLS, CELL_CHARS = (80, 24, 160)
    for t in doc.xpath("//*[local-name()='table']"):
        rows = []
        for tr in t.xpath(".//*[local-name()='tr']"):
            owner = next((a for a in tr.iterancestors() if _ln(a) == 'table'), None)
            if owner is not t:
                continue
            cells = t_cells = tr.xpath("./*[local-name()='td' or local-name()='th']")
            vals = []
            for td in cells[:MAX_COLS]:
                if td.xpath(".//*[local-name()='table']"):
                    vals.append('')
                else:
                    vals.append(_txt(td)[:CELL_CHARS])
            if any((v for v in vals)):
                rows.append(vals)
            if len(rows) >= MAX_ROWS:
                break
        if not rows:
            continue
        tbl_id[id(t)] = len(tables)
        tables.append({'table_idx': len(tables), 'order': order[id(t)], 'n_rows': len(rows), 'n_cols': max((len(r) for r in rows)), 'rows': rows, 'text': ' | '.join((' '.join(r) for r in rows[:40]))[:4000]})
    facts = []
    for el in doc.xpath("//*[local-name()='nonFraction']"):
        name = el.get('name') or ''
        if ':' not in name:
            continue
        prefix, concept = name.split(':', 1)
        ctx = contexts.get(el.get('contextRef') or '', {})
        ti = ri = ci = None
        cell_text = row_text = None
        td = tr = tb = None
        for a in el.iterancestors():
            n = _ln(a)
            if n in ('td', 'th') and td is None:
                td = a
            elif n == 'tr' and tr is None:
                tr = a
            elif n == 'table' and tb is None:
                tb = a
                break
        if tb is not None and id(tb) in tbl_id:
            ti = tbl_id[id(tb)]
            if tr is not None:
                trs = [x for x in tb.xpath(".//*[local-name()='tr']") if next((a for a in x.iterancestors() if _ln(a) == 'table'), None) is tb]
                ri = trs.index(tr) if tr in trs else None
                row_cells = tr.xpath("./*[local-name()='td' or local-name()='th']")
                if td is not None and td in row_cells:
                    ci = row_cells.index(td)
                row_text = ' '.join((_txt(c) for c in row_cells))[:300]
        if td is not None:
            cell_text = _txt(td)[:120]
        facts.append({'concept': concept, 'prefix': prefix, 'context_ref': el.get('contextRef'), 'start': ctx.get('start'), 'end': ctx.get('end') or ctx.get('instant'), 'instant': ctx.get('instant'), 'dims': ctx.get('dims', {}), 'unit_ref': el.get('unitRef'), 'scale': el.get('scale'), 'sign': el.get('sign'), 'decimals': el.get('decimals'), 'raw_text': _txt(el)[:60], 'value': _numeric(el), 'table_idx': ti, 'row_idx': ri, 'col_idx': ci, 'cell_text': cell_text, 'row_text': row_text, 'order': order[id(el)], 'fact_id': el.get('id')})
    blocks = []
    for el in doc.xpath("//*[local-name()='p' or local-name()='div']"):
        if any((_ln(a) == 'table' for a in el.iterancestors())):
            continue
        if any((_ln(ch) in ('p', 'div', 'table') for ch in el)):
            continue
        t = _txt(el)
        if len(t) >= 40:
            blocks.append({'order': order[id(el)], 'text': t[:3000]})
    return {'contexts': contexts, 'facts': facts, 'tables': tables, 'blocks': blocks, 'has_ixbrl': len(facts) > 0}
