from __future__ import annotations
import sys, math
from collections import defaultdict
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C
from systems.base import System
from systems.units import SPAN, TABLE, PAGE, FACT
from kg import schema as S

class LightRAG(System):
    name = 'LightRAG'
    uses_graph = True

    def answer(self, item, ctx):
        q = item['question']
        low = ctx.index.hybrid(q, C.TOP_K, tau=None, kinds=(SPAN, TABLE, FACT))
        low_units = ctx.index.get([i for i, _ in low])
        concept_score = defaultdict(float)
        for rank, u in enumerate(low_units):
            for cid in ctx.g.out.get(u['uid'], {}).get(S.OF_CONCEPT, []):
                concept_score[cid] += 1.0 / (rank + 1)
        extra = []
        for cid, _ in sorted(concept_score.items(), key=lambda x: -x[1])[:3]:
            for fid in ctx.g.inn.get(cid, {}).get(S.OF_CONCEPT, [])[:400]:
                pos = ctx.uid_pos.get(fid)
                if pos is not None:
                    extra.append(pos)
        seen, merged = (set(), [])
        for u in low_units:
            seen.add(u['uid'])
            merged.append(u)
        if extra:
            sub = ctx.index.get(extra[:600])
            hi = sorted(sub, key=lambda u: -_lex_overlap(q, u['text']))[:3]
            for u in hi:
                if u['uid'] not in seen:
                    merged.append(u)
                    seen.add(u['uid'])
        units = merged[:C.MAX_UNITS]
        out = self._gen(self._pack(item, units, '', with_time=False))
        out['units'] = units
        return out

def _lex_overlap(q: str, t: str) -> float:
    a = set(q.lower().split())
    b = set(t.lower().split())
    return len(a & b) / math.sqrt(len(a) + 1)

class HippoRAG(System):
    name = 'HippoRAG'
    uses_graph = True
    alpha = 0.5
    iters = 12

    def answer(self, item, ctx):
        q = item['question']
        seeds = ctx.index.hybrid(q, 10, tau=None, kinds=(SPAN, TABLE, FACT))
        seed_uids = [ctx.units[i]['uid'] for i, _ in seeds]
        pers = defaultdict(float)
        for r, u in enumerate(seed_uids):
            pers[u] = 1.0 / (r + 1)
        z = sum(pers.values()) or 1.0
        for k in pers:
            pers[k] /= z
        score = dict(pers)
        for _ in range(self.iters):
            nxt = defaultdict(float)
            for n, s in score.items():
                nb = []
                for et, dsts in ctx.g.out.get(n, {}).items():
                    if et in (S.OF_CONCEPT, S.COVERS, S.DISPLAYED_IN, S.RENDERED_ON, S.EQUIV, S.ABOUT, S.CONTAINS):
                        nb.extend(dsts)
                for et, srcs in ctx.g.inn.get(n, {}).items():
                    if et in (S.OF_CONCEPT, S.COVERS, S.DISPLAYED_IN, S.RENDERED_ON, S.EQUIV, S.CONTAINS):
                        nb.extend(srcs)
                if not nb:
                    nxt[n] += s
                    continue
                share = s * (1 - self.alpha) / len(nb)
                for m in nb:
                    nxt[m] += share
            for n, p in pers.items():
                nxt[n] += self.alpha * p
            score = nxt
        ranked = sorted(((n, s) for n, s in score.items() if n in ctx.uid_pos), key=lambda x: -x[1])[:C.TOP_K]
        units = [ctx.units[ctx.uid_pos[n]] for n, _ in ranked]
        if not units:
            units = ctx.index.get([i for i, _ in seeds[:C.TOP_K]])
        out = self._gen(self._pack(item, units, '', with_time=False))
        out['units'] = units
        return out
