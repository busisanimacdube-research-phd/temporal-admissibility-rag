from __future__ import annotations
import bisect, json, gzip
from collections import defaultdict
from pathlib import Path
from kg import schema as S

class EvidenceGraph:

    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.by_type: dict[str, list[str]] = defaultdict(list)
        self.out: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        self.inn: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        self.n_edges = 0
        self._t_sorted: list[str] = []
        self._t_keys: list[str] = []
        self.assertion_chain: dict[tuple, list[str]] = defaultdict(list)

    def add_node(self, nid: str, ntype: str, **attrs):
        if nid in self.nodes:
            self.nodes[nid].update(attrs)
            return nid
        attrs['_type'] = ntype
        self.nodes[nid] = attrs
        self.by_type[ntype].append(nid)
        return nid

    def add_edge(self, src: str, etype: str, dst: str):
        self.out[src][etype].append(dst)
        self.inn[dst][etype].append(src)
        self.n_edges += 1

    def finalize(self):
        timed = [(self.nodes[n].get('asserted_at') or '', n) for t in S.TEMPORAL_NODE_TYPES for n in self.by_type.get(t, [])]
        timed.sort()
        self._t_keys = [k for k, _ in timed]
        self._t_sorted = [n for _, n in timed]
        chains = defaultdict(list)
        for fid in self.by_type.get(S.FACT, []):
            f = self.nodes[fid]
            chains[f['company'], f['concept'], f['valid_key'], f.get('unit')].append((f['asserted_at'], fid))
        self.assertion_chain = {}
        for k, v in chains.items():
            v.sort()
            self.assertion_chain[k] = [fid for _, fid in v]
        return self

    def admissible(self, tau: str) -> set[str]:
        cut = bisect.bisect_right(self._t_keys, tau)
        adm = set(self._t_sorted[:cut])
        for t in (S.COMPANY, S.CONCEPT, S.PERIOD):
            adm.update(self.by_type.get(t, []))
        return adm

    def is_admissible(self, nid: str, tau: str) -> bool:
        a = self.nodes[nid].get('asserted_at')
        return True if a is None else a <= tau

    def resolve_pit(self, company: str, concept: str, valid_key: str, tau: str, unit: str | None=None):
        chain = self.assertion_chain.get((company, concept, valid_key, unit))
        if chain is None:
            cands = [k for k in self.assertion_chain if k[0] == company and k[1] == concept and (k[2] == valid_key)]
            if not cands:
                return None
            chain = self.assertion_chain[cands[0]]
        winner = None
        for fid in chain:
            if self.nodes[fid]['asserted_at'] <= tau:
                winner = fid
            else:
                break
        return winner

    def restatement_history(self, company: str, concept: str, valid_key: str, unit: str | None=None) -> list[str]:
        chain = self.assertion_chain.get((company, concept, valid_key, unit))
        if chain is None:
            cands = [k for k in self.assertion_chain if k[0] == company and k[1] == concept and (k[2] == valid_key)]
            chain = self.assertion_chain[cands[0]] if cands else []
        return list(chain)

    def neighbours(self, nid: str, etypes=None, adm: set[str] | None=None) -> list[str]:
        res = []
        for et, dsts in self.out.get(nid, {}).items():
            if etypes and et not in etypes:
                continue
            res.extend(dsts if adm is None else [d for d in dsts if d in adm])
        return res

    def predecessors(self, nid: str, etypes=None, adm: set[str] | None=None) -> list[str]:
        res = []
        for et, srcs in self.inn.get(nid, {}).items():
            if etypes and et not in etypes:
                continue
            res.extend(srcs if adm is None else [s for s in srcs if s in adm])
        return res

    def stats(self) -> dict:
        et = defaultdict(int)
        for src, d in self.out.items():
            for e, v in d.items():
                et[e] += len(v)
        return {'n_nodes': len(self.nodes), 'n_edges': self.n_edges, 'nodes_by_type': {t: len(self.by_type.get(t, [])) for t in S.NODE_TYPES}, 'edges_by_type': dict(et), 'n_chains': len(self.assertion_chain), 'n_restated_chains': sum((1 for v in self.assertion_chain.values() if len(v) > 1)), **self._revision_counts()}

    def _revision_counts(self) -> dict:
        changed = material = multi = 0
        for chain in self.assertion_chain.values():
            vals = [self.nodes[f].get('value') for f in chain]
            vals = [float(v) for v in vals if v is not None]
            if len(vals) < 2:
                continue
            if len({round(v, 6) for v in vals}) > 1:
                changed += 1
            steps = [(a, b) for a, b in zip(vals, vals[1:]) if a and abs(b - a) / abs(a) > 0.05]
            if steps:
                material += 1
            if len(steps) >= 2 and len({round(v, 6) for v in vals}) >= 3:
                multi += 1
        return {'n_value_changing_chains': changed, 'n_material_change_chains': material, 'n_multi_revision_chains': multi}

    def save(self, path: Path):
        path = Path(path)
        with gzip.open(path, 'wt') as fh:
            json.dump({'nodes': self.nodes, 'out': {k: dict(v) for k, v in self.out.items()}}, fh)

    @classmethod
    def load(cls, path: Path) -> 'EvidenceGraph':
        g = cls()
        with gzip.open(path, 'rt') as fh:
            d = json.load(fh)
        for nid, at in d['nodes'].items():
            g.add_node(nid, at.pop('_type'), **at)
        for src, ed in d['out'].items():
            for et, dsts in ed.items():
                for dst in dsts:
                    g.add_edge(src, et, dst)
        return g.finalize()
