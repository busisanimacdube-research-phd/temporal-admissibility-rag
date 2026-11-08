import json, os, sys, time, traceback
HERE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SRC = os.path.join(HERE, 'src')
sys.path.insert(0, SRC)
from eval.run import load_items, contexts_for
from eval.metrics import score_item
from systems.baselines import HybridRAG, TimeFilteredRAG
from systems.base import PIT_RULE
from systems.tempfinrag import TempFinRAG
import systems.tempfinrag as TF
import datetime as dt
OUT = os.environ.get('VARIANT_OUT', os.path.join(HERE, 'results', 'variants'))

class HybridInstructed(HybridRAG):
    name = 'Hybrid, dates and instruction, no filter'

    def answer(self, item, ctx):
        units = self.retrieve(item, ctx)
        out = self._gen(self._pack(item, units, PIT_RULE, with_time=True))
        out['units'] = units
        return out

class Hybrid14B(HybridRAG):
    name = 'Hybrid, 14B reader'

    def _gen(self, prompt, **kw):
        kw.setdefault('model', 'qwen2.5:14b')
        return super()._gen(prompt, **kw)

class HybridQwen7B(HybridRAG):
    name = 'Hybrid, Qwen2.5-7B reader'

    def _gen(self, prompt, **kw):
        kw.setdefault('model', 'qwen2.5:7b')
        return super()._gen(prompt, **kw)

class HybridLlama8B(HybridRAG):
    name = 'Hybrid, Llama-3.1-8B reader'

    def _gen(self, prompt, **kw):
        kw.setdefault('model', 'llama3.1:8b')
        return super()._gen(prompt, **kw)

class FilterOnly(TimeFilteredRAG):
    name = 'Hybrid, filter without dates and instruction'

    def answer(self, item, ctx):
        units = self.retrieve(item, ctx)
        out = self._gen(self._pack(item, units, '', with_time=False))
        out['units'] = units
        return out

def _days(a, b):
    return (dt.date.fromisoformat(a[:10]) - dt.date.fromisoformat(b[:10])).days

class SoftRerank(HybridRAG):
    name = 'Hybrid, soft date-aware reranking'
    half_life = 90

    def retrieve(self, item, ctx, k=None):
        tau = item['as_of']
        hits = ctx.index.hybrid(item['question'], 50, tau=None, kinds=self.kinds)
        units = ctx.index.get([i for i, _ in hits])
        score = []
        for (i, s), u in zip(hits, units):
            a = u.get('asserted_at') or ''
            lead = max(0, _days(a, tau)) if a else 0
            score.append(s * 0.5 ** (lead / self.half_life))
        order = sorted(range(len(units)), key=lambda j: -score[j])
        return [units[j] for j in order[:k or 10]]

class TempFinRAGNoFilter(TempFinRAG):
    name = 'TempFinRAG without its availability filter'
    FAR = '9999-12-31T23:59:59Z'

    def answer(self, item, ctx):
        real = item['as_of']
        orig_parse, orig_hybrid = (TF.parse_query, ctx.index.hybrid)
        TF.parse_query = lambda q, tau: orig_parse(q, real)
        ctx.index.hybrid = lambda q, k, tau=None, **kw: orig_hybrid(q, k, tau=None, **kw)
        fake = dict(item, as_of=self.FAR)
        orig_gen = self._gen
        self._gen = lambda prompt, **kw: orig_gen(prompt.replace(f'As-of date: {self.FAR[:10]}', f'As-of date: {real[:10]}'), **kw)
        try:
            out = super().answer(fake, ctx)
        finally:
            TF.parse_query, ctx.index.hybrid = (orig_parse, orig_hybrid)
            del self._gen
        out = self._verify(out, item, out['units'], out.get('calc'))
        return out
VARIANTS = {'hybrid': HybridRAG, 'timefiltered': TimeFilteredRAG, 'hybrid_instr': HybridInstructed, 'hybrid_14b': Hybrid14B, 'hybrid_q7': HybridQwen7B, 'hybrid_llama8': HybridLlama8B, 'filter_only': FilterOnly, 'soft_rerank': SoftRerank, 'tempfinrag_nofilter': TempFinRAGNoFilter, 'tempfinrag': TempFinRAG}

def main():
    keys = sys.argv[1:] or ['hybrid', 'timefiltered']
    os.makedirs(OUT, exist_ok=True)
    items = load_items('test', None)
    ctxs = contexts_for(items)
    for k in keys:
        path = os.path.join(OUT, f'{k}.jsonl')
        done = {json.loads(l)['qid'] for l in open(path)} if os.path.exists(path) else set()
        sysobj = VARIANTS[k]()
        todo = [i for i in items if i['qid'] not in done]
        print(f'[{k}] {len(todo)} to run', flush=True)
        t0 = time.time()
        with open(path, 'a') as fh:
            for n, it in enumerate(todo, 1):
                try:
                    pred = sysobj.answer(it, ctxs[it['company']])
                except Exception:
                    print(f"  ERR {it['qid']}: {traceback.format_exc(limit=1)}", flush=True)
                    continue
                row = score_item(it, pred)
                row.update({'answer': str(pred.get('answer'))[:200], 'abstain': bool(pred.get('abstain')), 'citations': [str(c) for c in pred.get('citations') or []], 'uids': [u['uid'] for u in pred.get('units') or []], 'asserted': [u.get('asserted_at') for u in pred.get('units') or []]})
                fh.write(json.dumps(row) + '\n')
                fh.flush()
                if n % 25 == 0 or n == len(todo):
                    el = time.time() - t0
                    print(f'  [{k} {n}/{len(todo)}] {el / n:.1f}s/q', flush=True)
if __name__ == '__main__':
    main()
