from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from systems.answer import match_answer, match_number, to_number, numbers_in
from bench.families import F2, F5, F3, F4, F6, F7

def gold_ids(item) -> set[str]:
    ev = item.get('evidence') or {}
    return set(ev.get('fact_ids') or []) | set(ev.get('table_ids') or []) | set(ev.get('page_ids') or [])

def gold_visual_ids(item) -> set[str]:
    ev = item.get('evidence') or {}
    return set(ev.get('page_ids') or []) | set(ev.get('table_ids') or [])

def evidence_recall(item, units) -> float | None:
    g = gold_ids(item)
    if not g:
        return None
    return float(bool(g & {u['uid'] for u in units}))

def multimodal_recall(item, units) -> float | None:
    g = gold_visual_ids(item)
    if not g:
        return None
    return float(bool(g & {u['uid'] for u in units}))

def temporal_leakage(item, units) -> float:
    tau = item['as_of']
    return float(any(((u.get('asserted_at') or '') > tau for u in units)))

def answer_channel_leakage(item, pred) -> float | None:
    if item.get('family') != F2 or item.get('restatement_phase') != 'pre_revision':
        return None
    sv = item.get('superseded_value')
    if sv is None or pred.get('abstain'):
        return None
    if match_number(pred.get('answer'), float(item['answer']), item.get('answer_type', 'number')):
        return 0.0
    return float(match_number(pred.get('answer'), float(sv), item.get('answer_type', 'number')))

def _close(a: float, b: float, rel: float=0.01) -> bool:
    if b == 0:
        return abs(a) <= 1e-09
    return any((abs(a * s - b) <= abs(b) * rel for s in (1.0, 1000.0, 1000000.0, 1000000000.0, 0.001, 1e-06, 1e-09)))

def supported(pred, units) -> bool:
    v = to_number(pred.get('answer'))
    if v is None:
        return True
    calc = pred.get('calc')
    if calc and calc.get('value') is not None and _close(v, float(calc['value'])):
        tr = calc.get('trace') or {}
        inputs = [tr[k] for k in ('v_old', 'v_new', 'numerator', 'denominator') if isinstance(tr.get(k), (int, float))]
        if not inputs:
            return True
        found = 0
        for x in inputs:
            for u in units:
                if u.get('value') is not None and _close(float(u['value']), float(x)):
                    found += 1
                    break
                if any((_close(w, float(x)) for w in numbers_in(u.get('text', ''))[:400])):
                    found += 1
                    break
        if found == len(inputs):
            return True
    for u in units:
        if u.get('value') is not None:
            g = float(u['value'])
            if g != 0 and any((abs(v * s - g) <= abs(g) * 0.01 for s in (1.0, 1000.0, 1000000.0, 1000000000.0, 0.001, 1e-06, 1e-09))):
                return True
        for w in numbers_in(u.get('text', ''))[:400]:
            if w != 0 and any((abs(v * s - w) <= abs(w) * 0.01 for s in (1.0, 1000.0, 1000000.0, 1000000000.0, 0.001, 1e-06, 1e-09))):
                return True
    return False

def hallucination(item, pred, units) -> float | None:
    if item.get('answer_type') == 'abstain' or pred.get('abstain'):
        return None
    return float(not supported(pred, units))

def citation_precision(item, pred, units) -> float | None:
    cits = pred.get('citations') or []
    if not cits or not units:
        return None
    idx = {}
    for i, u in enumerate(units, 1):
        idx[f'e{i}'] = u
    ok = tot = 0
    for c in cits:
        u = idx.get(str(c).strip().lower())
        if u is None:
            tot += 1
            continue
        tot += 1
        ok += int(supported(pred, [u]))
    return ok / tot if tot else None

def abstention_correct(item, pred) -> float | None:
    if item.get('answer_type') == 'abstain':
        return float(bool(pred.get('abstain')))
    return float(not pred.get('abstain'))

def score_item(item, pred) -> dict:
    units = pred.get('units') or []
    correct = float(match_answer(pred, item))
    fam = item.get('family')
    return {'qid': item['qid'], 'family': fam, 'split': item.get('split'), 'acc': correct, 'num_acc': correct if item.get('answer_type') in ('number', 'percent') else None, 'pit_acc': correct if fam == F2 else None, 'calc_val': correct if fam in (F3, F4) else None, 'multihop_acc': correct if fam == F6 else None, 'er': evidence_recall(item, units), 'mer': multimodal_recall(item, units), 'tlr': temporal_leakage(item, units), 'acl': answer_channel_leakage(item, pred), 'hr': hallucination(item, pred, units), 'cp': citation_precision(item, pred, units), 'abs_acc': abstention_correct(item, pred), 'latency': pred.get('latency'), 'n_units': len(units)}

def aggregate(rows: list[dict]) -> dict:
    keys = ('acc', 'num_acc', 'pit_acc', 'calc_val', 'multihop_acc', 'er', 'mer', 'tlr', 'acl', 'hr', 'cp', 'abs_acc', 'latency', 'n_units')
    out = {}
    for k in keys:
        vals = [r[k] for r in rows if r.get(k) is not None]
        out[k] = sum(vals) / len(vals) if vals else None
        out[k + '_n'] = len(vals)
    out['n'] = len(rows)
    return out
