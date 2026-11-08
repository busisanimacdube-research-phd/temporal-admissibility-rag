import collections, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyse_leakage import HERE, SRC, wilson, mcnemar
RUNS = os.path.join(HERE, 'results', 'variants')
VARIANTS = ['hybrid', 'timefiltered', 'hybrid_instr', 'hybrid_14b']

def main():
    items = {}
    for line in open(os.path.join(SRC, 'data', 'questions', 'questions.jsonl')):
        it = json.loads(line)
        if it['split'] == 'test':
            items[it['qid']] = it
    stored = {json.loads(l)['qid']: json.loads(l) for l in open(os.path.join(SRC, 'results', 'pipelines', 'hybrid.jsonl'))}
    rows, res = ({}, {})
    for v in VARIANTS:
        rs = [json.loads(l) for l in open(os.path.join(RUNS, f'{v}.jsonl'))]
        rows[v] = {r['qid']: r for r in rs}
        leak_q = cites = cites_late = cq = cq_late = 0
        for r in rs:
            tau = items[r['qid']]['as_of']
            late = [bool(a) and a[:10] > tau[:10] for a in r['asserted']]
            leak_q += any(late)
            idx = [int(m.group(1)) - 1 for c in r['citations'] for m in [re.fullmatch('E(\\d+)', c.strip())] if m]
            idx = [i for i in idx if 0 <= i < len(late)]
            cites += len(idx)
            cites_late += sum((late[i] for i in idx))
            if idx:
                cq += 1
                cq_late += any((late[i] for i in idx))
        pre = [r for r in rs if items[r['qid']].get('restatement_phase') == 'pre_revision' and items[r['qid']].get('superseded_value') is not None and (r.get('acl') is not None)]
        nyr = [r for r in rs if items[r['qid']]['family'] == 'unanswerable_at_tau']
        n = len(rs)
        res[v] = {'n': n, 'acc': wilson(sum((r['acc'] for r in rs)), n), 'evidence_leak_q': wilson(leak_q, n), 'answer_leak': wilson(sum((r['acl'] for r in pre)), len(pre)), 'answer_leak_n': len(pre), 'pre_revision_acc': wilson(sum((r['acc'] for r in pre)), len(pre)), 'not_yet_reported_abstain': wilson(sum((r['abstain'] for r in nyr)), len(nyr)), 'abstain_all': 100 * sum((r['abstain'] for r in rs)) / n, 'cited_units': cites, 'cited_late_share': 100 * cites_late / cites if cites else None, 'questions_citing': cq, 'questions_citing_late': wilson(cq_late, cq), 'acc_by_family': {f: wilson(sum((x['acc'] for x in g)), len(g)) + (len(g),) for f, g in sorted(collections.defaultdict(list, {k: [x for x in rs if items[x['qid']]['family'] == k] for k in {items[x['qid']]['family'] for x in rs}}).items())}}
    same = sum((1 for q, r in rows['hybrid'].items() if q in stored and r['acc'] == stored[q]['acc']))
    res['hybrid']['agreement_with_stored_run'] = [same, len(rows['hybrid'])]
    pairs = {}
    for a, b in [('hybrid', 'timefiltered'), ('hybrid', 'hybrid_instr'), ('hybrid_instr', 'timefiltered'), ('hybrid', 'hybrid_14b'), ('hybrid_14b', 'timefiltered')]:
        q = sorted(set(rows[a]) & set(rows[b]))
        x = sum((1 for i in q if rows[a][i]['acc'] == 1 and rows[b][i]['acc'] == 0))
        y = sum((1 for i in q if rows[a][i]['acc'] == 0 and rows[b][i]['acc'] == 1))
        pre = [i for i in q if items[i].get('restatement_phase') == 'pre_revision' and rows[a][i].get('acl') is not None and (rows[b][i].get('acl') is not None)]
        xa = sum((1 for i in pre if rows[a][i]['acl'] == 1 and rows[b][i]['acl'] == 0))
        ya = sum((1 for i in pre if rows[a][i]['acl'] == 0 and rows[b][i]['acl'] == 1))
        pairs[f'{a}_vs_{b}'] = {'n': len(q), 'only_first': x, 'only_second': y, 'p': mcnemar(x, y), 'answer_leak_only_first': xa, 'answer_leak_only_second': ya, 'answer_leak_p': mcnemar(xa, ya)}
    json.dump({'variants': res, 'paired': pairs}, open(os.path.join(HERE, 'results', 'variants.json'), 'w'), indent=1)
    for v, r in res.items():
        print(f"{v:13s} acc {r['acc'][0]:5.1f} [{r['acc'][1]:.1f},{r['acc'][2]:.1f}] ELq {r['evidence_leak_q'][0]:5.1f} AL {r['answer_leak'][0]:5.1f} (n={r['answer_leak_n']}) preacc {r['pre_revision_acc'][0]:5.1f} NYRabst {r['not_yet_reported_abstain'][0]:5.1f} abst {r['abstain_all']:4.1f} citedLate {r['cited_late_share'] or 0:5.1f} qCiteLate {r['questions_citing_late'][0]:5.1f} (n={r['questions_citing']})")
    print('hybrid rerun vs stored acc agreement', res['hybrid']['agreement_with_stored_run'])
    for k, p in pairs.items():
        print(k, p)
    for v in VARIANTS:
        print(v, {f: round(x[0], 1) for f, x in res[v]['acc_by_family'].items()})
if __name__ == '__main__':
    main()
