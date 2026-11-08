import json, os, statistics, sys
HERE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(HERE, 'src'))
from eval.run import load_items, contexts_for
items = load_items('test', None)
ctxs = contexts_for(items, dense=False)
dates = {}
for c, ctx in ctxs.items():
    us = ctx.units
    vals = us.values() if isinstance(us, dict) else us
    dates[c] = sorted(((u.get('asserted_at') or '')[:10] for u in vals if u.get('asserted_at')))
import bisect
rates = []
for it in items:
    d = dates[it['company']]
    tau = it['as_of'][:10]
    rates.append(100 * (len(d) - bisect.bisect_right(d, tau)) / len(d))
out = {'base_rate_mean': statistics.mean(rates), 'base_rate_median': statistics.median(rates), 'random10_elq': statistics.mean((100 * (1 - (1 - r / 100) ** 10) for r in rates)), 'questions_base_rate_zero': sum((r == 0 for r in rates)), 'units': {c: len(v) for c, v in dates.items()}}
json.dump(out, open(os.path.join(HERE, 'results', 'base_rate.json'), 'w'), indent=1)
print(out)
