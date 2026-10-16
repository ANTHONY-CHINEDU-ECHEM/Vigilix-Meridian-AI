"""Sparse BM25 index stored as a precomputed term weight matrix.

Each passage row holds BM25 weights for its terms, so scoring a query is a
single sparse column sum. With 131 thousand passages and about 140 thousand
terms a query takes a few milliseconds and the whole index fits in memory.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
from scipy import sparse


class BM25Index:
    def __init__(self, k1: float = 1.2, b: float = 0.72):
        self.k1 = k1
        self.b = b
        self.vocab: dict[str, int] = {}
        self.idf: np.ndarray | None = None
        self.weights: sparse.csc_matrix | None = None
        self.doc_len: np.ndarray | None = None

    def fit(self, docs: list[list[str]]) -> "BM25Index":
        df: Counter = Counter()
        for toks in docs:
            df.update(set(toks))
        self.vocab = {t: i for i, t in enumerate(sorted(df))}
        n = len(docs)
        self.idf = np.array([math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5)) for t in sorted(df)], dtype=np.float32)
        lens = np.array([len(d) for d in docs], dtype=np.float32)
        avg = float(lens.mean()) if n else 1.0
        rows, cols, vals = [], [], []
        for i, toks in enumerate(docs):
            tf = Counter(toks)
            norm = self.k1 * (1 - self.b + self.b * lens[i] / avg)
            for t, f in tf.items():
                j = self.vocab[t]
                rows.append(i)
                cols.append(j)
                vals.append(self.idf[j] * f * (self.k1 + 1) / (f + norm))
        self.weights = sparse.csc_matrix((np.array(vals, dtype=np.float32), (rows, cols)), shape=(n, len(self.vocab)))
        self.doc_len = lens
        return self

    def query_vector(self, tokens: list[str]) -> tuple[np.ndarray, np.ndarray]:
        tf = Counter(t for t in tokens if t in self.vocab)
        idx = np.array([self.vocab[t] for t in tf], dtype=np.int64)
        qw = np.array([float(c) for c in tf.values()], dtype=np.float32)
        return idx, qw

    def scores(self, tokens: list[str], subset: np.ndarray | None = None) -> np.ndarray:
        idx, qw = self.query_vector(tokens)
        n = self.weights.shape[0]
        if len(idx) == 0:
            return np.zeros(n if subset is None else len(subset), dtype=np.float32)
        cols = self.weights[:, idx]
        if subset is not None:
            cols = cols[subset]
        return np.asarray(cols @ qw).ravel()

    def search(self, tokens: list[str], k: int = 50, subset: np.ndarray | None = None) -> list[tuple[int, float]]:
        s = self.scores(tokens, subset)
        if not len(s):
            return []
        k = min(k, len(s))
        top = np.argpartition(-s, k - 1)[:k]
        top = top[np.argsort(-s[top])]
        out = [(int(i), float(s[i])) for i in top if s[i] > 0]
        if subset is not None:
            out = [(int(subset[i]), sc) for i, sc in out]
        return out

    def save(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        sparse.save_npz(folder / "bm25_weights.npz", self.weights.tocsr())
        np.save(folder / "bm25_idf.npy", self.idf)
        np.save(folder / "bm25_doclen.npy", self.doc_len)
        (folder / "bm25_vocab.json").write_text(json.dumps({"k1": self.k1, "b": self.b, "vocab": self.vocab}))

    @classmethod
    def load(cls, folder: Path) -> "BM25Index":
        meta = json.loads((folder / "bm25_vocab.json").read_text())
        idx = cls(meta["k1"], meta["b"])
        idx.vocab = meta["vocab"]
        idx.weights = sparse.load_npz(folder / "bm25_weights.npz").tocsc()
        idx.idf = np.load(folder / "bm25_idf.npy")
        idx.doc_len = np.load(folder / "bm25_doclen.npy")
        return idx
