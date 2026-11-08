from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C
from systems.base import System, PIT_RULE, CALC_NOTE, ROLE, SCHEMA, render_evidence
from systems.units import SPAN, TABLE, PAGE, FACT
from systems.parser import parse_query
from systems.answer import to_number, looks_like_date
from systems.calculator import compute, render_trace, duration_matches
TEMPFIN_RULE = PIT_RULE + '\n' + CALC_NOTE
RERANKER_LOAD_TIMEOUT = 300.0
_RERANK = {}

def reranker():
    if 'm' not in _RERANK:
        _RERANK['m'] = None

        def _load():
            import os
            os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
            from sentence_transformers import CrossEncoder
            import torch
            dev = 'mps' if torch.backends.mps.is_available() else 'cpu'
            return CrossEncoder('BAAI/bge-reranker-v2-m3', device=dev, max_length=512)
        import threading
        box = {}

        def _target():
            try:
                box['m'] = _load()
            except Exception as e:
                box['e'] = e
        t = threading.Thread(target=_target, daemon=True)
        t.start()
        t.join(RERANKER_LOAD_TIMEOUT)
        if 'm' in box:
            _RERANK['m'] = box['m']
            print('[TempFinRAG] cross-encoder reranker loaded', flush=True)
        elif 'e' in box:
            print(f"[TempFinRAG] reranker unavailable ({type(box['e']).__name__}); falling back to bi-encoder scoring", flush=True)
        else:
            print(f'[TempFinRAG] reranker did not load within {RERANKER_LOAD_TIMEOUT:.0f}s; falling back to bi-encoder scoring for every system in this run', flush=True)
    return _RERANK['m']

class TempFinRAG(System):
    name = 'TempFinRAG'
    uses_time = True
    uses_vision = True
    n_images = C.N_IMAGES
    assertion_recency = False

    def _relevance_order(self, q, units):
        return self._rerank(q, units, len(units))

    def _rerank(self, q, units, k):
        m = reranker()
        if not units:
            return units[:k]
        if m is None:
            from systems.index import get_encoder
            import numpy as np
            enc = get_encoder()
            qv = enc.encode([q], normalize_embeddings=True)[0]
            uv = enc.encode([u['text'][:1500] for u in units], batch_size=32, normalize_embeddings=True, show_progress_bar=False)
            order = np.argsort(-(np.asarray(uv) @ np.asarray(qv)))
            return [units[i] for i in order[:k]]
        scores = m.predict([(q, u['text'][:1500]) for u in units], batch_size=16, show_progress_bar=False)
        order = sorted(range(len(units)), key=lambda i: -float(scores[i]))
        return [units[i] for i in order[:k]]

    def _calculate(self, item, ctx, q):
        tau = item['as_of']
        p = parse_query(item['question'], tau)
        if p['operation'] not in ('lookup', 'growth', 'ratio'):
            return None
        cache = {}

        def pick(concept, period_end):
            if not concept:
                return None
            key = (concept, period_end)
            if key in cache:
                return cache[key]
            months = p.get('duration_months')
            cands = [u for u in ctx.units if u['kind'] == FACT and u.get('concept') == concept and ((u.get('asserted_at') or '') <= tau) and duration_matches(u.get('valid_key') or '', months)]
            if period_end:
                narrowed = [u for u in cands if (u.get('valid_key') or '').endswith(period_end)]
                if not narrowed and cands:
                    import datetime as _dt
                    try:
                        want = _dt.date.fromisoformat(period_end)

                        def _d(u):
                            return _dt.date.fromisoformat((u.get('valid_key') or '/1900-01-01').split('/')[-1])
                        nearest = min(cands, key=lambda u: abs((_d(u) - want).days))
                        if abs((_d(nearest) - want).days) <= C.NEAR_DAYS:
                            narrowed = [u for u in cands if u.get('valid_key') == nearest.get('valid_key')]
                        else:
                            narrowed = []
                    except ValueError:
                        narrowed = []
                cands = narrowed
            if not cands:
                cache[key] = None
                return None
            if self.assertion_recency:
                best = max(cands, key=lambda u: u.get('asserted_at') or '')
            else:
                order = self._relevance_order(q, cands[:60])
                best = order[0] if order else cands[0]
            cache[key] = {'value': best.get('value'), 'valid_key': best.get('valid_key'), 'unit': best.get('unit'), 'concept': best.get('concept'), 'asserted_at': best.get('asserted_at')}
            return cache[key]
        return compute(p['operation'], p, pick)

    def answer(self, item, ctx):
        q, tau = (item['question'], item['as_of'])
        pool = ctx.index.hybrid(q, C.CANDIDATE_POOL, tau=tau, kinds=(SPAN, TABLE, FACT))
        cand = ctx.index.get([i for i, _ in pool])
        units = self._rerank(q, cand, C.TOP_K)
        pages = []
        seen = set()
        for u in units:
            for pu in ctx.units:
                if pu['kind'] == PAGE and pu['accession'] == u['accession'] and (pu['page'] == u.get('page')) and (pu['uid'] not in seen) and ((pu.get('asserted_at') or '') <= tau):
                    pages.append(pu)
                    seen.add(pu['uid'])
                    break
        imgs = [str(C.FILINGS / p['image']) for p in pages[:self.n_images] if p.get('image') and (C.FILINGS / p['image']).exists()]
        calc = self._calculate(item, ctx, q)
        calc_txt = render_trace(calc) if calc else ''
        shown = units + pages[:self.n_images]
        prompt = f"{ROLE}\n\n{TEMPFIN_RULE}\n\nAs-of date: {tau[:10]}\nCompany: {item['company']}\n\nEvidence:\n{render_evidence(shown, with_time=True)}\n{calc_txt}\nQuestion: {item['question']}\n\n{SCHEMA}"
        out = self._gen(prompt, model=C.READER_VL if imgs else C.READER_TEXT, images=imgs, num_ctx=8192)
        out = self._verify(out, item, shown, calc)
        out['units'] = shown
        out['calc'] = calc
        return out

    def _verify(self, out, item, units, calc):
        tau = item['as_of']
        leaked = [u for u in units if (u.get('asserted_at') or '') > tau]
        out['verifier'] = {'temporal_ok': not leaked, 'n_leaked': len(leaked)}
        if not units and (not calc):
            out['abstain'] = True
        if looks_like_date(out.get('answer')):
            return out
        v = to_number(out.get('answer'))
        if calc and calc['value'] is not None and (v is not None):
            g = float(calc['value'])
            if g != 0 and abs(v - g) > abs(g) * 0.01:
                for s in (1000.0, 1000000.0, 1000000000.0, 1e-06):
                    if abs(v * s - g) <= abs(g) * 0.01:
                        break
                else:
                    out['answer'] = calc['value']
                    out['verifier']['recalculated'] = True
        return out
