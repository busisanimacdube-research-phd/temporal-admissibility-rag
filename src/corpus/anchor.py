from __future__ import annotations
import re, bisect
_KEEP = re.compile('[^0-9a-z]+')

def _norm(s: str) -> str:
    return _KEEP.sub('', s.lower())

def build_pdf_stream(page_texts: list[str]):
    parts, starts, pos = ([], [], 0)
    for t in page_texts:
        n = _norm(t)
        starts.append(pos)
        parts.append(n)
        pos += len(n)
    return (''.join(parts), starts)

def _page_of(offset: int, starts: list[int]) -> int:
    return bisect.bisect_right(starts, offset)

def anchor_items(items: list[dict], page_texts: list[str], key: str='text', anchor_len: int=60, min_len: int=24) -> dict[int, int]:
    stream, starts = build_pdf_stream(page_texts)
    n_pages = len(page_texts)
    cursor, last_page, out = (0, 1, {})
    for it in items:
        probe = _norm(it.get(key) or '')
        page = None
        if len(probe) >= min_len:
            for ln in (anchor_len, 40, min_len):
                if len(probe) < ln:
                    continue
                for off in (0, ln, 2 * ln):
                    if off + ln > len(probe):
                        break
                    hit = stream.find(probe[off:off + ln], cursor)
                    if hit >= 0:
                        page = _page_of(hit, starts)
                        cursor = hit
                        break
                if page:
                    break
        if page is None:
            page = last_page
        else:
            last_page = page
        out[it['order']] = min(page, n_pages)
    return out

def assign_pages(ix: dict, page_texts: list[str]) -> dict:
    items = [{'order': t['order'], 'text': t['text']} for t in ix['tables']] + [{'order': b['order'], 'text': b['text']} for b in ix['blocks']]
    items.sort(key=lambda x: x['order'])
    pages = anchor_items(items, page_texts)
    for t in ix['tables']:
        t['page'] = pages.get(t['order'], 1)
    for b in ix['blocks']:
        b['page'] = pages.get(b['order'], 1)
    tpage = {t['table_idx']: t['page'] for t in ix['tables']}
    for f in ix['facts']:
        f['page'] = tpage.get(f['table_idx']) if f['table_idx'] is not None else pages.get(f['order'], 1)
    return ix

def _row_tokens(f: dict) -> list[str]:
    row = f.get('row_text') or ''
    toks = [t for t in re.findall('[A-Za-z]{4,}', row)]
    return [t.lower() for t in toks[:6]]

def repair_fact_pages(ix: dict, page_texts: list[str], window: int=8) -> dict:
    norm_pages = [_norm(t) for t in page_texts]
    n = len(page_texts)
    repaired = 0
    for f in ix['facts']:
        v = (f.get('raw_text') or '').strip()
        if len(v) < 3:
            continue
        p = f.get('page') or 1
        vn = _norm(v)
        if vn and vn in norm_pages[p - 1]:
            continue
        toks = _row_tokens(f)
        best, best_score = (None, -1.0)
        lo, hi = (max(1, p - window), min(n, p + window))
        for rng in (range(lo, hi + 1), range(1, n + 1)):
            for q in rng:
                if vn not in norm_pages[q - 1]:
                    continue
                hits = sum((1 for t in toks if t in norm_pages[q - 1]))
                score = hits - 0.02 * abs(q - p)
                if score > best_score:
                    best, best_score = (q, score)
            if best is not None:
                break
        if best is not None and best != p:
            f['page'] = best
            f['page_repaired'] = True
            repaired += 1
    ix['n_page_repairs'] = repaired
    return ix
