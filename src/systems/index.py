from __future__ import annotations
import re, sys, numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C
_TOK = re.compile('[a-z0-9]+')
_ENCODER = {}

def get_encoder(name: str='BAAI/bge-m3'):
    if name not in _ENCODER:
        from sentence_transformers import SentenceTransformer
        import torch
        dev = 'mps' if torch.backends.mps.is_available() else 'cpu'
        m = SentenceTransformer(name, device=dev)
        m.max_seq_length = 512
        if dev == 'mps':
            m = m.half()
        _ENCODER[name] = m
    return _ENCODER[name]

def tok(s: str) -> list[str]:
    return _TOK.findall(s.lower())

class UnitIndex:

    def __init__(self, units: list[dict], dense: bool=True, cache: Path | None=None):
        from rank_bm25 import BM25Okapi
        self.units = units
        self.bm25 = BM25Okapi([tok(u['text']) for u in units]) if units else None
        self.emb = None
        if dense and units:
            self.emb = self._embed(cache)
        self._t = np.array([u['asserted_at'] or '' for u in units])

    def _embed(self, cache: Path | None) -> np.ndarray:
        if cache and cache.exists():
            a = np.load(cache)
            if a.shape[0] == len(self.units):
                return a
        m = get_encoder()
        a = m.encode([u['text'] for u in self.units], batch_size=64, normalize_embeddings=True, show_progress_bar=False)
        a = np.asarray(a, dtype=np.float32)
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            np.save(cache, a)
        return a

    def _mask(self, tau: str | None, kinds=None) -> np.ndarray:
        m = np.ones(len(self.units), dtype=bool)
        if tau is not None:
            m &= self._t <= tau
        if kinds:
            m &= np.array([u['kind'] in kinds for u in self.units])
        return m

    def sparse(self, q: str, k: int, tau=None, kinds=None) -> list[tuple[int, float]]:
        if self.bm25 is None:
            return []
        s = np.asarray(self.bm25.get_scores(tok(q)), dtype=np.float32)
        s[~self._mask(tau, kinds)] = -np.inf
        idx = np.argpartition(-s, min(k, len(s) - 1))[:k]
        idx = idx[np.argsort(-s[idx])]
        return [(int(i), float(s[i])) for i in idx if np.isfinite(s[i])]

    def dense_search(self, q: str, k: int, tau=None, kinds=None) -> list[tuple[int, float]]:
        if self.emb is None:
            return []
        qv = get_encoder().encode([q], normalize_embeddings=True)[0].astype(np.float32)
        s = self.emb @ qv
        s[~self._mask(tau, kinds)] = -np.inf
        idx = np.argpartition(-s, min(k, len(s) - 1))[:k]
        idx = idx[np.argsort(-s[idx])]
        return [(int(i), float(s[i])) for i in idx if np.isfinite(s[i])]

    def hybrid(self, q: str, k: int, tau=None, kinds=None, pool=None, rrf: int=60):
        pool = pool or max(k * 5, C.CANDIDATE_POOL)
        sp = self.sparse(q, pool, tau, kinds)
        dn = self.dense_search(q, pool, tau, kinds)
        score = {}
        for r, (i, _) in enumerate(sp):
            score[i] = score.get(i, 0.0) + 1.0 / (rrf + r + 1)
        for r, (i, _) in enumerate(dn):
            score[i] = score.get(i, 0.0) + 1.0 / (rrf + r + 1)
        top = sorted(score.items(), key=lambda x: -x[1])[:k]
        return [(int(i), float(s)) for i, s in top]

    def get(self, idxs) -> list[dict]:
        return [self.units[i] for i in idxs]
