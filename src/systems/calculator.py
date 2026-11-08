from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bench.families import RATIOS

def duration_days(valid_key: str) -> int | None:
    import datetime as _dt
    st, en = (valid_key or '/').split('/', 1)
    if st in ('', 'instant'):
        return None
    try:
        return (_dt.date.fromisoformat(en) - _dt.date.fromisoformat(st)).days
    except ValueError:
        return None

def duration_matches(valid_key: str, months: int | None) -> bool:
    if months is None:
        return True
    d = duration_days(valid_key)
    if months == 0:
        return d is None
    if d is None:
        return False
    return abs(d - months * 30.4) <= 45

def growth(v_prev: float, v_curr: float) -> float | None:
    if v_prev is None or v_curr is None or v_prev == 0:
        return None
    return (v_curr - v_prev) / abs(v_prev) * 100.0

def ratio(numer: float, denom: float, as_percent: bool=True) -> float | None:
    if numer is None or denom is None or denom == 0:
        return None
    return numer / denom * (100.0 if as_percent else 1.0)

def ratio_spec(metric: str):
    spec = RATIOS.get(metric)
    if not spec:
        return None
    name, num, dens = spec
    return {'name': name, 'numerator': num, 'denominators': list(dens), 'as_percent': metric not in ('current_ratio',)}

def compute(operation: str, parsed: dict, pick):
    if operation == 'growth':
        metric = parsed.get('metric')
        p_new = parsed.get('period_end')
        p_old = parsed.get('compare_period_end')
        if not p_old:
            per = sorted((p for p in parsed.get('periods') or [] if p))
            if len(per) >= 2:
                p_old, p_new = (per[0], per[-1])
        a = pick(metric, p_old)
        b = pick(metric, p_new)
        if not a or not b:
            return None
        v = growth(a['value'], b['value'])
        if v is None:
            return None
        return {'value': round(v, 4), 'unit': 'percent', 'trace': {'operation': 'growth', 'metric': metric, 'formula': '(v_new - v_old) / |v_old| * 100', 'v_old': a['value'], 'v_new': b['value'], 'period_old': a.get('valid_key'), 'period_new': b.get('valid_key')}}
    if operation == 'ratio':
        spec = ratio_spec(parsed.get('metric'))
        if not spec:
            return None
        end = parsed.get('period_end') or (parsed.get('periods') or [None])[0]
        num = pick(spec['numerator'], end)
        den = None
        for d in spec['denominators']:
            den = pick(d, end)
            if den:
                break
        if not num or not den:
            return None
        v = ratio(num['value'], den['value'], spec['as_percent'])
        if v is None:
            return None
        return {'value': round(v, 4), 'unit': 'percent' if spec['as_percent'] else 'ratio', 'trace': {'operation': 'ratio', 'metric': spec['name'], 'formula': f"{spec['numerator']} / {den.get('concept', 'denominator')}" + (' * 100' if spec['as_percent'] else ''), 'numerator': num['value'], 'denominator': den['value'], 'period': num.get('valid_key')}}
    if operation == 'lookup':
        metric = parsed.get('metric')
        end = parsed.get('period_end') or (parsed.get('periods') or [None])[0]
        a = pick(metric, end)
        if not a:
            return None
        return {'value': a['value'], 'unit': a.get('unit'), 'trace': {'operation': 'lookup', 'metric': metric, 'period': a.get('valid_key'), 'asserted_at': a.get('asserted_at')}}
    return None

def render_trace(calc: dict) -> str:
    if not calc:
        return ''
    t = calc['trace']
    op = t['operation']
    if op == 'growth':
        return f"\nStructured calculation ({op}): {t['metric']} moved from {t['v_old']:,.4f} ({t['period_old']}) to {t['v_new']:,.4f} ({t['period_new']}); {t['formula']} = {calc['value']:,.4f} percent.\n"
    if op == 'ratio':
        return f"\nStructured calculation ({op}): {t['metric']} = {t['formula']} = {t['numerator']:,.4f} / {t['denominator']:,.4f} = {calc['value']:,.4f} {calc['unit']} for {t['period']}.\n"
    return f"\nStructured calculation (lookup): {t['metric']} for {t['period']} = {calc['value']:,.4f} {calc.get('unit') or ''}.\n"
