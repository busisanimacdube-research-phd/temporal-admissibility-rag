from __future__ import annotations
import json, sys, random, datetime as dt
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C
from kg.graph import EvidenceGraph
from kg import schema as S
from bench.families import F1, F2, F3, F4, F5, F6, F7, CONCEPT_NAME, RATIOS
DAY = dt.timedelta(days=1)
MIN_REVISION_GAP = 0.05
SPLIT_SENSITIVE = {'CommonStockSharesOutstanding', 'EarningsPerShareBasic', 'EarningsPerShareDiluted'}

def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(s[:10])

def _iso(d: dt.date) -> str:
    return d.isoformat() + 'T23:59:59Z'

def _period_label(g, vk: str) -> str:
    st, en = vk.split('/', 1)
    if st == 'instant':
        return f'as at {en}'
    return f'the period {st} to {en}'

def _fy_label(node) -> str:
    end = node.get('valid_end')
    if not end:
        return ''
    start = node.get('valid_start')
    if not start:
        return f'the balance as at {end}'
    try:
        days = (dt.date.fromisoformat(str(end)) - dt.date.fromisoformat(str(start))).days
    except ValueError:
        return f'the period ending {end}'
    for lo, hi, phrase in ((60, 120, 'the three months ended'), (150, 210, 'the six months ended'), (240, 300, 'the nine months ended'), (330, 400, 'the twelve months ended')):
        if lo <= days <= hi:
            return f'{phrase} {end}'
    return f'the period from {start} to {end}'

def _evidence_of(g, fid: str, tau: str | None=None) -> dict:
    n = g.nodes[fid]
    equivalent = [fid]
    if tau is not None and n.get('value') is not None:
        chain = g.restatement_history(n['company'], n['concept'], n['valid_key'], n.get('unit'))
        for other in chain:
            if other == fid:
                continue
            m = g.nodes[other]
            if m.get('asserted_at', '') > tau or m.get('value') is None:
                continue
            a, b = (float(m['value']), float(n['value']))
            if abs(a - b) <= max(abs(b) * 1e-06, 1e-09):
                equivalent.append(other)
    tabs, pages = ([], [])
    for f in equivalent:
        tabs += g.out.get(f, {}).get(S.DISPLAYED_IN, [])
        pages += g.out.get(f, {}).get(S.RENDERED_ON, [])
    return {'fact_ids': equivalent, 'table_ids': list(dict.fromkeys(tabs)), 'page_ids': list(dict.fromkeys(pages)), 'accession': n.get('accession'), 'page': n.get('page'), 'cell': n.get('cell'), 'row_text': n.get('row_text')}

def _admissible_at(g, comp, con, vk, unit, tau_iso):
    ch = g.restatement_history(comp, con, vk, unit)
    adm = [g.nodes[f] for f in ch if g.nodes[f].get('asserted_at', '') <= tau_iso]
    vals = [n['value'] for n in adm if n.get('value') is not None]
    return (len(adm), len({round(float(v), 6) for v in vals}))

def _adm_fields(g, comp, con, vk, unit, tau_iso) -> dict:
    n_adm, n_val = _admissible_at(g, comp, con, vk, unit, tau_iso)
    return {'n_admissible_assertions': n_adm, 'n_distinct_admissible_values': n_val, 'discriminating': n_val >= 2}

def _has_visual(g, fid: str) -> bool:
    return bool(g.out.get(fid, {}).get(S.RENDERED_ON))

class Generator:

    def __init__(self, g: EvidenceGraph, seed: int=C.SEED):
        self.g = g
        self.rng = random.Random(seed)
        self.items: list[dict] = []
        self._n = 0
        self.chains = {}
        accn_in = {g.nodes[l]['accession'] for l in g.by_type.get(S.FILING, [])}
        for k, ch in g.assertion_chain.items():
            keep = [f for f in ch if g.nodes[f].get('accession') in accn_in]
            if keep:
                self.chains[k] = keep
        self.accn_in = accn_in

    def _add(self, family, company, question, answer, tau, evidence, **extra):
        self._n += 1
        self.items.append({'qid': f'pf-{self._n:05d}', 'family': family, 'company': company, 'question': question, 'answer': answer, 'as_of': tau, 'evidence': evidence, **extra})

    def gen_fact_at_date(self, n: int):
        cand = [(k, ch) for k, ch in self.chains.items() if CONCEPT_NAME.get(k[1]) and any((_has_visual(self.g, f) for f in ch))]
        self.rng.shuffle(cand)
        made = 0
        for (comp, con, vk, unit), ch in cand:
            if made >= n:
                break
            fid = next((f for f in ch if _has_visual(self.g, f)), None)
            if fid is None:
                continue
            node = self.g.nodes[fid]
            if node.get('value') is None:
                continue
            a = _d(node['asserted_at'])
            later = [f for f in ch if _d(self.g.nodes[f]['asserted_at']) > a]
            hi = min((_d(self.g.nodes[f]['asserted_at']) for f in later), default=a + dt.timedelta(days=120))
            if hi <= a + DAY:
                continue
            tau = a + dt.timedelta(days=self.rng.randint(1, max(1, (hi - a).days - 1)))
            per = _fy_label(node) or _period_label(self.g, vk)
            self._add(F1, comp, f'As of {tau.isoformat()}, what did {comp} report as {CONCEPT_NAME[con]} for {per}?', node['value'], _iso(tau), _evidence_of(self.g, fid, _iso(tau)), concept=con, unit=unit, valid_key=vk, answer_type='number')
            made += 1
        return made

    def gen_restatement(self, n: int):
        revised = []
        for (comp, con, vk, unit), ch in self.chains.items():
            if len(ch) < 2 or not CONCEPT_NAME.get(con):
                continue
            vals = [self.g.nodes[f].get('value') for f in ch]
            for i in range(len(ch) - 1):
                a, b = (ch[i], ch[i + 1])
                va, vb = (vals[i], vals[i + 1])
                if va is None or vb is None or va == 0:
                    continue
                rel = abs(vb - va) / abs(va)
                if rel <= MIN_REVISION_GAP:
                    continue
                revised.append(((comp, con, vk, unit), a, b, va, vb, rel))
        self.rng.shuffle(revised)
        revised.sort(key=lambda r: r[0][1] in SPLIT_SENSITIVE)
        made = 0
        for (comp, con, vk, unit), a, b, va, vb, rel in revised:
            if made >= n:
                break
            da, db = (_d(self.g.nodes[a]['asserted_at']), _d(self.g.nodes[b]['asserted_at']))
            if db <= da + DAY:
                continue
            per = _fy_label(self.g.nodes[a]) or _period_label(self.g, vk)
            cn = CONCEPT_NAME[con]
            t1 = da + dt.timedelta(days=self.rng.randint(1, max(1, (db - da).days - 1)))
            self._add(F2, comp, f"As of {t1.isoformat()}, what was {comp}'s reported {cn} for {per}?", va, _iso(t1), _evidence_of(self.g, a, _iso(t1)), concept=con, unit=unit, valid_key=vk, answer_type='number', restatement_phase='pre_revision', superseded_value=vb, revision_gap=round(rel, 6), revision_kind='split' if con in SPLIT_SENSITIVE else 'accounting', **_adm_fields(self.g, comp, con, vk, unit, _iso(t1)))
            made += 1
            if made >= n:
                break
            t2 = db + dt.timedelta(days=self.rng.randint(1, 90))
            self._add(F2, comp, f"As of {t2.isoformat()}, what was {comp}'s reported {cn} for {per}?", vb, _iso(t2), _evidence_of(self.g, b, _iso(t2)), concept=con, unit=unit, valid_key=vk, answer_type='number', restatement_phase='post_revision', superseded_value=va, revision_gap=round(rel, 6), revision_kind='split' if con in SPLIT_SENSITIVE else 'accounting', **_adm_fields(self.g, comp, con, vk, unit, _iso(t2)))
            made += 1
        return made

    def gen_period_comparison(self, n: int):
        by_cc = defaultdict(list)
        for (comp, con, vk, unit), ch in self.chains.items():
            st, en = vk.split('/', 1)
            if st == 'instant' or not CONCEPT_NAME.get(con):
                continue
            by_cc[comp, con, unit].append((en, vk, ch))
        made = 0
        keys = list(by_cc)
        self.rng.shuffle(keys)
        for comp, con, unit in keys:
            if made >= n:
                break
            ents = sorted(by_cc[comp, con, unit])
            for i in range(len(ents) - 1):
                for j in range(i + 1, len(ents)):
                    e0, vk0, ch0 = ents[i]
                    e1, vk1, ch1 = ents[j]
                    d0, d1 = (_d(e0), _d(e1))
                    if not 330 <= (d1 - d0).days <= 400:
                        continue
                    f0, f1 = (ch0[-1], ch1[-1])
                    v0, v1 = (self.g.nodes[f0].get('value'), self.g.nodes[f1].get('value'))
                    if not v0 or not v1 or v0 == 0:
                        continue
                    tau = max(_d(self.g.nodes[f0]['asserted_at']), _d(self.g.nodes[f1]['asserted_at'])) + dt.timedelta(days=self.rng.randint(1, 60))
                    growth = (v1 - v0) / abs(v0) * 100.0
                    ev = _evidence_of(self.g, f1, _iso(tau))
                    ev0 = _evidence_of(self.g, f0, _iso(tau))
                    ev['fact_ids'] += ev0['fact_ids']
                    ev['table_ids'] += ev0['table_ids']
                    ev['page_ids'] += ev0['page_ids']
                    self._add(F3, comp, f"Using only information public as of {tau.isoformat()}, by what percentage did {comp}'s {CONCEPT_NAME[con]} change from the period ending {e0} to the period ending {e1}?", round(growth, 2), _iso(tau), ev, concept=con, unit='percent', answer_type='percent', inputs=[v0, v1], formula='(v1 - v0) / |v0| * 100')
                    made += 1
                    break
                if made >= n:
                    break
        return made

    def gen_ratio(self, n: int):
        latest = {}
        for (comp, con, vk, unit), ch in self.chains.items():
            latest[comp, con, vk] = ch[-1]
        made = 0
        keys = list(latest)
        self.rng.shuffle(keys)
        for comp, num_con, vk in keys:
            if made >= n:
                break
            for rid, (rname, num, dens) in RATIOS.items():
                if num_con != num:
                    continue
                den_fid = next((latest[comp, d, vk] for d in dens if (comp, d, vk) in latest), None)
                if den_fid is None:
                    continue
                nf = latest[comp, num_con, vk]
                nv, dv = (self.g.nodes[nf].get('value'), self.g.nodes[den_fid].get('value'))
                if not nv or not dv:
                    continue
                tau = max(_d(self.g.nodes[nf]['asserted_at']), _d(self.g.nodes[den_fid]['asserted_at'])) + dt.timedelta(days=self.rng.randint(1, 60))
                pct = rid not in ('current_ratio',)
                val = nv / dv * (100.0 if pct else 1.0)
                ev = _evidence_of(self.g, nf, _iso(tau))
                ev2 = _evidence_of(self.g, den_fid, _iso(tau))
                ev['fact_ids'] += ev2['fact_ids']
                ev['table_ids'] += ev2['table_ids']
                ev['page_ids'] += ev2['page_ids']
                per = _fy_label(self.g.nodes[nf]) or _period_label(self.g, vk)
                self._add(F4, comp, f"Based only on filings public as of {tau.isoformat()}, what was {comp}'s {rname} for {per}?", round(val, 3), _iso(tau), ev, concept=rid, unit='percent' if pct else 'ratio', answer_type='percent' if pct else 'number', inputs=[nv, dv], formula=f'{num} / {dens[0]}' + (' * 100' if pct else ''))
                made += 1
                break
        return made

    def gen_crossmodal(self, n: int):
        cand = []
        for fid in self.g.by_type.get(S.FACT, []):
            nd = self.g.nodes[fid]
            if nd.get('accession') not in self.accn_in or not _has_visual(self.g, fid):
                continue
            rt = nd.get('row_text') or ''
            if len(rt) < 12 or nd.get('value') is None or (not CONCEPT_NAME.get(nd['concept'])):
                continue
            cand.append(fid)
        self.rng.shuffle(cand)
        made = 0
        for fid in cand:
            if made >= n:
                break
            nd = self.g.nodes[fid]
            tau = _d(nd['asserted_at']) + dt.timedelta(days=self.rng.randint(1, 45))
            per = _fy_label(nd) or _period_label(self.g, nd['valid_key'])
            self._add(F5, nd['company'], f"In {nd['company']}'s filing available as of {tau.isoformat()}, locate the statement line reporting {CONCEPT_NAME[nd['concept']]} for {per} and give the reported figure.", nd['value'], _iso(tau), _evidence_of(self.g, fid, _iso(tau)), concept=nd['concept'], unit=nd.get('unit'), answer_type='number', layout_sensitive=True)
            made += 1
        return made

    def gen_multihop(self, n: int):
        by_cc = defaultdict(list)
        for (comp, con, vk, unit), ch in self.chains.items():
            st, en = vk.split('/', 1)
            if st == 'instant' or not CONCEPT_NAME.get(con):
                continue
            by_cc[comp, con, unit].append((en, vk, ch))
        made = 0
        keys = list(by_cc)
        self.rng.shuffle(keys)
        for k in keys:
            if made >= n:
                break
            comp, con, unit = k
            ents = sorted(by_cc[k])
            annual = [e for e in ents if 350 <= (_d(e[0]) - _d(e[1].split('/')[0])).days <= 380]
            if len(annual) < 3:
                continue
            pick = annual[-3:]
            fids = [p[2][-1] for p in pick]
            vals = [self.g.nodes[f].get('value') for f in fids]
            if any((v is None for v in vals)):
                continue
            tau = max((_d(self.g.nodes[f]['asserted_at']) for f in fids)) + dt.timedelta(days=self.rng.randint(1, 60))
            best = pick[max(range(3), key=lambda i: vals[i])][0]
            ev = {'fact_ids': [], 'table_ids': [], 'page_ids': [], 'accession': None, 'page': None, 'cell': None, 'row_text': None}
            for f in fids:
                e = _evidence_of(self.g, f, _iso(tau))
                ev['fact_ids'] += e['fact_ids']
                ev['table_ids'] += e['table_ids']
                ev['page_ids'] += e['page_ids']
            yrs = ', '.join((p[0] for p in pick))
            self._add(F6, comp, f'Considering only filings public as of {tau.isoformat()}, across the fiscal periods ending {yrs}, which period had the highest {CONCEPT_NAME[con]} for {comp}? Answer with the period end date.', best, _iso(tau), ev, concept=con, unit='date', answer_type='date', n_hops=len(fids), inputs=vals)
            made += 1
        return made

    def gen_unanswerable(self, n: int):
        cand = [(k, ch) for k, ch in self.chains.items() if CONCEPT_NAME.get(k[1])]
        self.rng.shuffle(cand)
        made = 0
        for (comp, con, vk, unit), ch in cand:
            if made >= n:
                break
            first = ch[0]
            nd = self.g.nodes[first]
            tau = _d(nd['asserted_at']) - dt.timedelta(days=self.rng.randint(1, 21))
            hist = self.g.restatement_history(comp, con, vk, unit)
            if any((_d(self.g.nodes[f]['asserted_at']) <= tau for f in hist)):
                continue
            per = _fy_label(nd) or _period_label(self.g, vk)
            self._add(F7, comp, f'As of {tau.isoformat()}, what did {comp} report as {CONCEPT_NAME[con]} for {per}?', 'UNANSWERABLE', _iso(tau), {'fact_ids': [], 'table_ids': [], 'page_ids': [], 'accession': None, 'page': None, 'cell': None, 'row_text': None}, concept=con, unit=unit, answer_type='abstain', first_public=nd['asserted_at'])
            made += 1
        return made
