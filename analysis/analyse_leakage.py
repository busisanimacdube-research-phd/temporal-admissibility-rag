from graph_io import load_nodes
import collections, gzip, json, math, os, statistics
HERE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SRC = HERE
RUNS = os.path.join(SRC, 'results', 'pipelines')
OUT = os.path.join(HERE, 'results')
SYSTEMS = ['closedbook', 'bm25', 'dense', 'hybrid', 'lightrag', 'hipporag', 'visrag', 'm3docrag', 'timefiltered', 'tempfinrag']

def wilson(k, n, z=1.96):
    if not n:
        return (float('nan'),) * 3
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (100 * p, 100 * (c - h), 100 * (c + h))

def mcnemar(b, c):
    n = b + c
    if not n:
        return 1.0
    k = min(b, c)
    p = sum((math.comb(n, i) for i in range(k + 1))) / 2 ** n
    return min(1.0, 2 * p)

def main():
    os.makedirs(OUT, exist_ok=True)
    items = {}
    for line in open(os.path.join(SRC, 'data', 'questions', 'questions.jsonl')):
        it = json.loads(line)
        if it['split'] == 'test':
            items[it['qid']] = it
    nodes = load_nodes(os.path.join(SRC, 'data', 'graph'))
    res, rows, lead_all = ({}, {}, {})
    for s in SYSTEMS:
        rs = [json.loads(l) for l in open(os.path.join(RUNS, f'{s}.jsonl'))]
        rows[s] = {r['qid']: r for r in rs}
        leak_q, unit_share, leads, unknown = (0, [], [], 0)
        for r in rs:
            tau = items[r['qid']]['as_of']
            dates = [(nodes.get(u) or {}).get('asserted_at') for u in r.get('uids') or []]
            unknown += sum((d is None for d in dates))
            dates = [d for d in dates if d]
            late = [d for d in dates if d > tau]
            leak_q += bool(late)
            if dates:
                unit_share.append(len(late) / len(dates))
            for d in late:
                leads.append((datetime(d) - datetime(tau)).days)
        lead_all[s] = leads
        fam = collections.defaultdict(list)
        for r in rs:
            fam[items[r['qid']]['family']].append(r['acc'])
        pre = [r for r in rs if items[r['qid']].get('restatement_phase') == 'pre_revision' and items[r['qid']].get('superseded_value') is not None]
        acl = [r for r in pre if r.get('acl') is not None]
        kinds = collections.defaultdict(list)
        for r in acl:
            kinds[items[r['qid']].get('revision_kind') or 'other'].append(r['acl'])
        n = len(rs)
        res[s] = {'n': n, 'acc': wilson(sum((r['acc'] for r in rs)), n), 'evidence_leak_q': wilson(leak_q, n), 'leaked_unit_share': 100 * statistics.mean(unit_share) if unit_share else 0.0, 'lead_days_median': statistics.median(leads) if leads else None, 'lead_days_q1_q3': (statistics.quantiles(leads, n=4)[0], statistics.quantiles(leads, n=4)[2]) if len(leads) > 3 else None, 'units_without_date': unknown, 'answer_leak': wilson(sum((r['acl'] for r in acl)), len(acl)), 'answer_leak_n': len(acl), 'pre_revision_n': len(pre), 'pre_revision_acc': wilson(sum((r['acc'] for r in pre)), len(pre)), 'answer_leak_by_kind': {k: wilson(sum(v), len(v)) + (len(v),) for k, v in sorted(kinds.items())}, 'acc_by_family': {k: wilson(sum(v), len(v)) + (len(v),) for k, v in sorted(fam.items())}, 'abstain': 100 * sum((bool(r.get('abstain')) for r in rs)) / n}
    pairs = {}
    for a, b in [('hybrid', 'timefiltered'), ('dense', 'timefiltered'), ('lightrag', 'timefiltered')]:
        q = sorted(set(rows[a]) & set(rows[b]))
        x = sum((1 for i in q if rows[a][i]['acc'] == 1 and rows[b][i]['acc'] == 0))
        y = sum((1 for i in q if rows[a][i]['acc'] == 0 and rows[b][i]['acc'] == 1))
        fam = collections.defaultdict(lambda: [0, 0, 0])
        for i in q:
            f = fam[items[i]['family']]
            f[0] += 1
            f[1] += rows[a][i]['acc']
            f[2] += rows[b][i]['acc']
        pairs[f'{a}_vs_{b}'] = {'n': len(q), 'only_first': x, 'only_second': y, 'p': mcnemar(x, y), 'by_family': {k: {'n': v[0], 'first': 100 * v[1] / v[0], 'second': 100 * v[2] / v[0]} for k, v in sorted(fam.items())}}
    kinds = collections.Counter((it.get('revision_kind') for it in items.values() if it.get('restatement_phase') == 'pre_revision'))
    fams = collections.Counter((it['family'] for it in items.values()))
    out = {'systems': res, 'paired': pairs, 'test_items': len(items), 'families': fams, 'pre_revision_kinds': kinds}
    json.dump(out, open(os.path.join(OUT, 'leakage.json'), 'w'), indent=1)
    json.dump(lead_all, open(os.path.join(OUT, 'lead_days.json'), 'w'))
    print(f"{'system':14s} {'acc':>6s} {'leakQ':>6s} {'unit%':>6s} {'lead':>5s} {'ansLeak':>8s} {'n':>4s}")
    for s, r in res.items():
        print(f"{s:14s} {r['acc'][0]:6.1f} {r['evidence_leak_q'][0]:6.1f} {r['leaked_unit_share']:6.1f} {r['lead_days_median'] or 0:5.0f} {r['answer_leak'][0]:8.1f} {r['answer_leak_n']:4d}")
    for k, v in pairs.items():
        print(k, {kk: vv for kk, vv in v.items() if kk != 'by_family'})
    print('pre-revision kinds', dict(kinds), 'families', dict(fams))

def datetime(d):
    import datetime as dt
    return dt.date.fromisoformat(d[:10])
if __name__ == '__main__':
    main()
