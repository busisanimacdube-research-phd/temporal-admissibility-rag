from __future__ import annotations
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C
from systems.llm import generate
from bench.families import CONCEPT_NAME, RATIOS
CONCEPTS = sorted(CONCEPT_NAME)
_MENU = '\n'.join((f'- {c}: {CONCEPT_NAME[c]}' for c in CONCEPTS))
_RATIOS = '\n'.join((f'- {k}: {v[0]}' for k, v in RATIOS.items()))
PROMPT = 'Extract the structure of this financial question.\n\nAvailable metrics:\n{menu}\n\nAvailable ratios:\n{ratios}\n\nQuestion: {q}\nAs-of date: {tau}\n\nA period is identified by BOTH its end date and its duration, because a quarter\nand the year-to-date span can end on the same day.\n\nReply with one JSON object and nothing else:\n{{"metric": <a metric or ratio name from the lists, or null>,\n "second_metric": <a second metric if the question compares two periods, else null>,\n "period_end": <the fiscal period end date the question asks about, YYYY-MM-DD, or null>,\n "duration_months": <3, 6, 9 or 12 for a span; 0 for a balance as at a date; null if unstated>,\n "compare_period_end": <the earlier period end date if two periods are compared, else null>,\n "operation": <"lookup", "growth", "ratio", "argmax", or "none">,\n "periods": [<all period end dates mentioned, YYYY-MM-DD>]}}'

def parse_query(question: str, tau: str, model: str=C.READER_TEXT) -> dict:
    raw = generate(PROMPT.format(menu=_MENU, ratios=_RATIOS, q=question, tau=tau[:10]), model=model, max_tokens=220)
    out = {'metric': None, 'second_metric': None, 'period_end': None, 'duration_months': None, 'compare_period_end': None, 'operation': 'none', 'periods': []}
    m = re.search('\\{.*\\}', raw or '', re.S)
    if m:
        try:
            d = json.loads(m.group(0))
            for k in out:
                if k in d and d[k] is not None:
                    out[k] = d[k]
        except Exception:
            pass
    try:
        out['duration_months'] = int(out['duration_months']) if out['duration_months'] is not None else None
    except (TypeError, ValueError):
        out['duration_months'] = None
    if not isinstance(out['periods'], list):
        out['periods'] = []
    out['periods'] = [str(p)[:10] for p in out['periods'] if re.match('\\d{4}-\\d{2}-\\d{2}', str(p))]
    if out['period_end'] and (not re.match('\\d{4}-\\d{2}-\\d{2}', str(out['period_end']))):
        out['period_end'] = None
    if out['metric'] in RATIOS:
        out['operation'] = 'ratio'
    elif out['compare_period_end'] or len(set(out['periods'])) >= 2:
        out['operation'] = 'growth'
    elif out['metric']:
        out['operation'] = 'lookup'
    return out
