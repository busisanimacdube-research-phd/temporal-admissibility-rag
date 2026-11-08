from graph_io import load_nodes
import ast, collections, gzip, json, os, re
HERE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SRC = HERE
ORDER = ['premature', 'computation', 'abstention', 'later value', 'earlier value', 'not retrieved', 'multi-hop', 'other period', 'other']

def num(x):
    m = re.search('-?\\d[\\d,]*\\.?\\d*', str(x).replace('$', ''))
    return float(m.group(0).replace(',', '')) if m else None

def close(a, b):
    return a is not None and b is not None and (abs(a - b) <= 0.01 * max(abs(a), abs(b)) or abs(abs(a) - abs(b)) <= 0.01 * max(abs(a), abs(b)))

def key(fid):
    return ':'.join(fid.split(':')[:4])

def classify(it, r, nodes):
    if it['family'] == 'unanswerable_at_tau':
        return 'premature'
    if it['family'] in ('ratio', 'period_comparison'):
        return 'computation'
    if r['abstain']:
        return 'abstention'
    a = num(r['answer'])
    if r.get('acl') == 1:
        return 'later value'
    sv = it.get('superseded_value')
    if sv not in (None, '', 'None') and it.get('restatement_phase') == 'post_revision' and close(a, num(sv)):
        return 'earlier value'
    ev = it.get('evidence')
    ev = ast.literal_eval(ev) if isinstance(ev, str) else ev or {}
    gold = {key(f) for f in ev.get('fact_ids', [])}
    if not gold & {key(u) for u in r['uids'] if u.startswith('F:')}:
        return 'not retrieved'
    if it['family'] == 'multihop_temporal':
        return 'multi-hop'
    for u in r['uids']:
        n = nodes.get(u) or {}
        if u.startswith('F:') and n.get('concept') == it.get('concept') and (n.get('valid_key') != it.get('valid_key')) and close(a, num(n.get('value'))):
            return 'other period'
    return 'other'

def main():
    items = {}
    for line in open(os.path.join(SRC, 'data', 'questions', 'questions.jsonl')):
        it = json.loads(line)
        if it['split'] == 'test':
            items[it['qid']] = it
    nodes = load_nodes(os.path.join(SRC, 'data', 'graph'))
    out = {}
    for v in ['hybrid', 'timefiltered']:
        rs = [json.loads(l) for l in open(os.path.join(HERE, 'results', 'variants', f'{v}.jsonl'))]
        wrong = [r for r in rs if r['acc'] == 0]
        c = collections.Counter((classify(items[r['qid']], r, nodes) for r in wrong))
        out[v] = {'errors': len(wrong), 'categories': {k: c.get(k, 0) for k in ORDER}}
        print(v, out[v])
    json.dump(out, open(os.path.join(HERE, 'results', 'errors.json'), 'w'), indent=1)
if __name__ == '__main__':
    main()
