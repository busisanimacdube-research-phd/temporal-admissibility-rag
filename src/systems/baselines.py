from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C
from systems.base import System, CompanyContext, ROLE, SCHEMA, PIT_RULE, render_evidence
from systems.units import SPAN, TABLE, PAGE, FACT

class ClosedBookLLM(System):
    name = 'Closed-book LLM'

    def answer(self, item, ctx):
        p = f"{ROLE}\n\nAs-of date: {item['as_of'][:10]}\nCompany: {item['company']}\n\nNo documents are provided. Answer from your own knowledge.\n\nQuestion: {item['question']}\n\n{SCHEMA}"
        out = self._gen(p)
        out['units'] = []
        return out

class RetrievalRAG(System):
    name = 'Retrieval-RAG'
    mode = 'hybrid'
    kinds = (SPAN, TABLE, FACT)
    time_filtered = False

    def retrieve(self, item, ctx, k=None):
        k = k or C.TOP_K
        tau = item['as_of'] if self.time_filtered else None
        fn = {'sparse': ctx.index.sparse, 'dense': ctx.index.dense_search, 'hybrid': ctx.index.hybrid}[self.mode]
        hits = fn(item['question'], k, tau=tau, kinds=self.kinds)
        return ctx.index.get([i for i, _ in hits])

    def answer(self, item, ctx):
        units = self.retrieve(item, ctx)
        rule = PIT_RULE if self.time_filtered else ''
        out = self._gen(self._pack(item, units, rule, with_time=self.time_filtered))
        out['units'] = units
        return out

class BM25RAG(RetrievalRAG):
    name = 'BM25-RAG'
    mode = 'sparse'

class DenseRAG(RetrievalRAG):
    name = 'Dense-RAG'
    mode = 'dense'

class HybridRAG(RetrievalRAG):
    name = 'Hybrid-RAG'
    mode = 'hybrid'

class TimeFilteredRAG(RetrievalRAG):
    name = 'Time-filtered RAG'
    mode = 'hybrid'
    time_filtered = True
    uses_time = True

class VisRAG(System):
    name = 'VisRAG'
    uses_vision = True
    n_images = C.N_IMAGES

    def answer(self, item, ctx):
        hits = ctx.index.hybrid(item['question'], C.TOP_K, tau=None, kinds=(PAGE,))
        units = ctx.index.get([i for i, _ in hits])
        imgs = [str(C.FILINGS / u['image']) for u in units[:self.n_images] if u.get('image') and (C.FILINGS / u['image']).exists()]
        p = self._pack(item, units, '', with_time=False)
        out = self._gen(p, model=C.READER_VL, images=imgs, num_ctx=8192)
        out['units'] = units
        return out

class M3DocRAG(System):
    name = 'M3DocRAG'
    uses_vision = True
    n_images = C.N_IMAGES

    def answer(self, item, ctx):
        ph = ctx.index.hybrid(item['question'], C.TOP_K, tau=None, kinds=(PAGE,))
        th = ctx.index.hybrid(item['question'], C.TOP_K, tau=None, kinds=(TABLE,))
        units = ctx.index.get([i for i, _ in ph]) + ctx.index.get([i for i, _ in th])
        units = units[:C.MAX_UNITS]
        imgs = [str(C.FILINGS / u['image']) for u in units if u.get('image') and (C.FILINGS / u['image']).exists()][:self.n_images]
        out = self._gen(self._pack(item, units, '', with_time=False), model=C.READER_VL, images=imgs, num_ctx=8192)
        out['units'] = units
        return out
