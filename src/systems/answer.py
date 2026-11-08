from __future__ import annotations
import json, re
SCALES = {'thousand': 1000.0, 'thousands': 1000.0, 'k': 1000.0, 'million': 1000000.0, 'millions': 1000000.0, 'm': 1000000.0, 'mm': 1000000.0, 'billion': 1000000000.0, 'billions': 1000000000.0, 'b': 1000000000.0, 'bn': 1000000000.0, 'trillion': 1000000000000.0, 'trillions': 1000000000000.0, 't': 1000000000000.0}
ABSTAIN_MARKERS = ('unanswerable', 'not available', 'cannot be answered', 'no evidence', 'not yet public', 'insufficient', 'not disclosed', 'unknown', 'cannot determine', 'not public', 'abstain')
_NUM = re.compile('-?\\$?\\s*\\(?\\d[\\d,]*\\.?\\d*\\)?\\s*(?:thousand|million|billion|trillion|[kmbt]n?)?%?', re.I)
_THOUSANDS = re.compile('(?<=\\d),(?=\\d{3}(?:\\D|$))')
_BARE = re.compile('(?<=[\\[:,])(\\s*)([A-Za-z][A-Za-z0-9_]*)(?=\\s*[,\\]}])')

def _repair_json(txt: str) -> str:
    txt = _THOUSANDS.sub('', txt)
    return _BARE.sub(lambda m: m.group(0) if m.group(2) in ('true', 'false', 'null') else f'{m.group(1)}"{m.group(2)}"', txt)

def parse_output(raw: str) -> dict:
    out = {'answer': None, 'citations': [], 'abstain': False, 'raw': raw}
    m = re.search('\\{.*\\}', raw or '', re.S)
    if m:
        try:
            try:
                d = json.loads(m.group(0))
            except Exception:
                d = json.loads(_repair_json(m.group(0)))
            out['answer'] = d.get('answer')
            c = d.get('citations') or d.get('citation') or []
            out['citations'] = [str(x) for x in (c if isinstance(c, list) else [c])]
            out['abstain'] = bool(d.get('abstain'))
            if out['answer'] is not None or out['abstain']:
                return out
        except Exception:
            pass
    txt = (raw or '').strip()
    out['answer'] = txt
    out['abstain'] = any((k in txt.lower() for k in ABSTAIN_MARKERS))
    return out
_DATE = re.compile('^\\s*\\d{4}-\\d{2}-\\d{2}\\s*$')

def looks_like_date(s) -> bool:
    return isinstance(s, str) and bool(_DATE.match(s))

def to_number(s) -> float | None:
    if isinstance(s, (int, float)):
        return float(s)
    if not isinstance(s, str):
        return None
    t = s.strip().lower().replace(',', '')
    neg = '(' in t and ')' in t
    t = t.replace('(', '').replace(')', '').replace('$', '').replace('us', '').strip()
    pct = t.endswith('%')
    t = t.rstrip('%').strip()
    mult = 1.0
    for w, f in sorted(SCALES.items(), key=lambda x: -len(x[0])):
        if t.endswith(' ' + w) or (t.endswith(w) and (not t[:-len(w)].strip().endswith('e'))):
            cand = t[:-len(w)].strip()
            if cand and re.fullmatch('-?\\d*\\.?\\d+', cand):
                t, mult = (cand, f)
                break
    try:
        v = float(t) * mult
    except ValueError:
        m = _NUM.search(s)
        if not m:
            return None
        return to_number(m.group(0)) if m.group(0) != s else None
    if neg:
        v = -v
    return v

def numbers_in(s: str) -> list[float]:
    if not isinstance(s, str):
        return []
    out = []
    for m in _NUM.finditer(s):
        v = to_number(m.group(0))
        if v is not None:
            out.append(v)
    return out

def match_number(pred, gold: float, answer_type: str='number', rel_tol: float=0.01, pp_tol: float=0.1) -> bool:
    cands = []
    v = to_number(pred)
    if v is not None:
        cands.append(v)
    if isinstance(pred, str):
        cands.extend(numbers_in(pred)[:6])
    if not cands:
        return False
    for v in cands:
        if answer_type == 'percent':
            if abs(v - gold) <= pp_tol or abs(v - gold) <= abs(gold) * rel_tol:
                return True
            continue
        if gold == 0:
            if abs(v) <= 1e-09:
                return True
            continue
        for scale in (1.0, 1000.0, 1000000.0, 1000000000.0, 0.001, 1e-06, 1e-09):
            if abs(v * scale - gold) <= abs(gold) * rel_tol:
                return True
    return False

def match_answer(pred_obj: dict, item: dict) -> bool:
    at = item.get('answer_type', 'number')
    gold = item['answer']
    if at == 'abstain':
        return bool(pred_obj.get('abstain'))
    if pred_obj.get('abstain'):
        return False
    pred = pred_obj.get('answer')
    if at in ('number', 'percent'):
        try:
            g = float(gold)
        except (TypeError, ValueError):
            return False
        return match_number(pred, g, at)
    if at == 'date':
        s = str(pred or '')
        return str(gold) in s or str(gold).replace('-', '/') in s
    return str(gold).lower().strip() in str(pred or '').lower()
