"""Hybrid retrieval with entity routing, graph features and learned reranking.

Three candidate generators run in parallel:

* BM25 over the whole corpus (lexical precision, exact drug names, numbers)
* the in domain dual encoder (semantic matches such as lay phrasing)
* entity routed BM25 restricted to passages that mention the linked query
  drug (and reaction when present), so a question about a rarely discussed
  drug is not drowned by passages about common ones

Candidates are fused by reciprocal rank fusion, described by 47 features
(lexical, semantic, entity, graph, source and intent) and reordered by a
LightGBM LambdaMART model. A diversity step caps passages per document.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from vigilix.config import SETTINGS
from vigilix.kb.dictionaries import Dictionary, load_dictionaries
from vigilix.rag.bm25 import BM25Index
from vigilix.rag.dense import DualEncoder, SIFEncoder
from vigilix.rag.graph import KnowledgeGraph
from vigilix.rag.query import INTENTS, QueryInfo, _POP_COMPILED, understand
from vigilix.rag.store import PassageStore
from vigilix.rag.text import analyse

SOURCE_TYPES = (
    "guidance_card",
    "drug_label",
    "trial_abstract",
    "signal_summary",
    "kg_fact",
    "interaction_monograph",
    "cid_abstract",
    "interaction_abstract",
    "case_report",
)

FEATURES = (
    ["bm25", "bm25_norm", "dense_cos", "dense_gap", "rrf", "rr_bm25", "rr_dense", "rr_entity", "rr_card", "rr_label", "q_coverage", "title_coverage", "bigram_overlap"]
    + ["drug_match", "drug_in_title", "reaction_match", "pair_match", "evidence_level", "log_len", "results_section"]
    + [f"src_{s}" for s in SOURCE_TYPES]
    + [f"intent_{i}" for i in INTENTS]
    + ["n_query_drugs", "n_query_reactions", "kg_labelled", "kg_faers", "kg_case", "kg_literature", "kg_interaction", "population_match", "query_len"]
)


@dataclass
class Candidate:
    idx: int
    bm25: float = 0.0
    dense: float = 0.0
    rank_bm25: int | None = None
    rank_dense: int | None = None
    rank_entity: int | None = None
    rank_card: int | None = None
    rank_label: int | None = None
    rrf: float = 0.0
    score: float = 0.0
    features: list[float] = field(default_factory=list)


class Retriever:
    def __init__(
        self,
        store: PassageStore,
        bm25: BM25Index,
        sif: SIFEncoder,
        dual: DualEncoder | None,
        dense_matrix: np.ndarray,
        graph: KnowledgeGraph,
        drugs: Dictionary,
        reactions: Dictionary,
        reranker=None,
        sif_matrix: np.ndarray | None = None,
    ):
        self.store = store
        self.bm25 = bm25
        self.sif = sif
        self.dual = dual
        self.dense = dense_matrix
        self.sif_matrix = sif_matrix
        self.graph = graph
        self.drugs = drugs
        self.reactions = reactions
        self.reranker = reranker
        self.cfg = SETTINGS.retrieval
        self._title_tokens: dict[int, set[str]] = {}
        self._ptok_cache: dict[int, list[str]] = {}
        self.card_idx = np.array([i for i, p in enumerate(store.passages) if p["source_type"] == "guidance_card"], dtype=np.int64)
        self.label_set = {i for i, p in enumerate(store.passages) if p["source_type"] == "drug_label"}

    # ------------------------------------------------------------------
    @classmethod
    def load(cls, with_reranker: bool = True, with_sif_matrix: bool = False) -> "Retriever":
        art = SETTINGS.paths.artifacts
        store = PassageStore.load()
        bm25 = BM25Index.load(art)
        sif = SIFEncoder.load(art)
        dual = DualEncoder.load(art)
        dense = np.load(art / "dense_passages.npy").astype(np.float32)
        drugs, reactions = load_dictionaries(SETTINGS.paths.processed / "dictionaries.json")
        graph = KnowledgeGraph.load()
        reranker = None
        if with_reranker and (art / "reranker.txt").exists():
            import lightgbm as lgb

            reranker = lgb.Booster(model_file=str(art / "reranker.txt"))
        sif_m = np.load(art / "sif_passages.npy").astype(np.float32) if with_sif_matrix else None
        return cls(store, bm25, sif, dual, dense, graph, drugs, reactions, reranker, sif_m)

    def understand(self, text: str) -> QueryInfo:
        return understand(text, self.drugs, self.reactions)

    # ------------------------------------------------------------------
    def dense_query(self, tokens: list[str], use_dual: bool = True) -> np.ndarray:
        v = self.sif.encode([tokens])
        if use_dual and self.dual is not None:
            return self.dual.encode_queries(v)[0]
        return (v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-8))[0]

    def dense_search(self, tokens: list[str], k: int, use_dual: bool = True) -> list[tuple[int, float]]:
        q = self.dense_query(tokens, use_dual)
        mat = self.dense if use_dual or self.sif_matrix is None else self.sif_matrix
        s = mat @ q
        k = min(k, len(s))
        top = np.argpartition(-s, k - 1)[:k]
        top = top[np.argsort(-s[top])]
        return [(int(i), float(s[i])) for i in top]

    def candidates(self, q: QueryInfo, k: int | None = None) -> dict[int, Candidate]:
        k = k or self.cfg.candidates_per_retriever
        cands: dict[int, Candidate] = {}
        for r, (i, s) in enumerate(self.bm25.search(q.tokens, k)):
            c = cands.setdefault(i, Candidate(i))
            c.bm25, c.rank_bm25 = s, r
        for r, (i, s) in enumerate(self.dense_search(q.tokens, k)):
            c = cands.setdefault(i, Candidate(i))
            c.dense, c.rank_dense = s, r
        if q.drugs or q.reactions:
            subset = self.store.entity_subset(q.drugs, q.reactions)
            if len(subset):
                for r, (i, s) in enumerate(self.bm25.search(q.tokens, max(20, k // 2), subset=subset)):
                    c = cands.setdefault(i, Candidate(i))
                    c.bm25 = max(c.bm25, s)
                    c.rank_entity = r
        # Source routing: the best guidance digests and, for drug questions, the best label sections
        for r, (i, s) in enumerate(self.bm25.search(q.tokens, 6, subset=self.card_idx)):
            cands.setdefault(i, Candidate(i)).rank_card = r
        if q.drugs:
            lab = np.array(sorted(set(self.store.entity_subset(q.drugs, []).tolist()) & self.label_set), dtype=np.int64)
            if len(lab):
                for r, (i, s) in enumerate(self.bm25.search(q.tokens, 6, subset=lab)):
                    cands.setdefault(i, Candidate(i)).rank_label = r
        if cands:
            qv = self.dense_query(q.tokens)
            idx = np.array(list(cands))
            dense_scores = self.dense[idx] @ qv
            bm = self.bm25.scores(q.tokens, subset=idx)
            for j, i in enumerate(idx):
                cands[int(i)].dense = float(dense_scores[j])
                cands[int(i)].bm25 = float(bm[j])
        for c in cands.values():
            c.rrf = sum(1.0 / (self.cfg.rrf_k + r + 1) for r in (c.rank_bm25, c.rank_dense, c.rank_entity) if r is not None)
        return cands

    # ------------------------------------------------------------------
    def _passage_tokens(self, i: int) -> list[str]:
        t = self._ptok_cache.get(i)
        if t is None:
            t = analyse(self.store[i]["text"])
            if len(self._ptok_cache) > 60000:
                self._ptok_cache.clear()
            self._ptok_cache[i] = t
        return t

    def _title_toks(self, i: int) -> set[str]:
        t = self._title_tokens.get(i)
        if t is None:
            t = set(analyse(self.store[i]["title"]))
            self._title_tokens[i] = t
        return t

    def featurise(self, q: QueryInfo, cands: dict[int, Candidate], graph_flags: dict | None = None) -> np.ndarray:
        if not cands:
            return np.zeros((0, len(FEATURES)), dtype=np.float32)
        qset = set(q.tokens)
        qbi = set(zip(q.tokens, q.tokens[1:]))
        max_bm = max((c.bm25 for c in cands.values()), default=1.0) or 1.0
        max_dense = max((c.dense for c in cands.values()), default=0.0)
        flags = graph_flags if graph_flags is not None else (self.graph.evidence_summary(q.drugs, q.reactions)["flags"] if (q.drugs and (q.reactions or len(q.drugs) > 1)) else {})
        intents = set(q.intents)
        pops = [_POP_COMPILED[p] for p in q.populations]
        rows = []
        for c in cands.values():
            p = self.store[c.idx]
            text_l = p["text"].lower()
            ptoks_list = self._passage_tokens(c.idx)
            ptoks = set(ptoks_list) | self._title_toks(c.idx)
            title_t = self._title_toks(c.idx)
            pdr = set(p.get("drugs", []))
            prx = set(p.get("reactions", []))
            title_l = p["title"].lower()
            dm = sum(1 for d in q.drugs if d in pdr or d in title_l) / len(q.drugs) if q.drugs else 0.0
            dt = float(any(d in title_l for d in q.drugs)) if q.drugs else 0.0
            rm = sum(1 for r in q.reactions if r in prx or r in text_l) / len(q.reactions) if q.reactions else 0.0
            pm = float(dm > 0 and rm > 0)
            roles = p.get("roles", [])
            pbi = set(zip(ptoks_list, ptoks_list[1:]))
            row = [
                c.bm25,
                c.bm25 / max_bm,
                c.dense,
                c.dense - max_dense,
                c.rrf * 100,
                1.0 / (c.rank_bm25 + 1) if c.rank_bm25 is not None else 0.0,
                1.0 / (c.rank_dense + 1) if c.rank_dense is not None else 0.0,
                1.0 / (c.rank_entity + 1) if c.rank_entity is not None else 0.0,
                1.0 / (c.rank_card + 1) if c.rank_card is not None else 0.0,
                1.0 / (c.rank_label + 1) if c.rank_label is not None else 0.0,
                len(qset & ptoks) / max(len(qset), 1),
                len(qset & title_t) / max(len(qset), 1),
                len(qbi & pbi) / max(len(qbi), 1),
                dm,
                dt,
                rm,
                pm,
                float(p["evidence_level"]),
                math.log1p(len(p["text"].split())),
                float(p["source_type"] == "trial_abstract" and any(r in ("results", "conclusions") for r in roles)),
            ]
            row += [float(p["source_type"] == s) for s in SOURCE_TYPES]
            row += [float(i in intents) for i in INTENTS]
            row += [
                float(len(q.drugs)),
                float(len(q.reactions)),
                float(flags.get("labelled", False)),
                float(flags.get("faers", False)),
                float(flags.get("case", False)),
                float(flags.get("literature", False)),
                float(flags.get("interaction", False)),
                float(any(pt.search(p["text"]) for pt in pops)) if pops else 0.0,
                float(len(q.tokens)),
            ]
            c.features = row
            rows.append(row)
        return np.array(rows, dtype=np.float32)

    # ------------------------------------------------------------------
    def _diversify(self, ranked: list[Candidate], k: int) -> list[Candidate]:
        out, per_doc = [], {}
        for c in ranked:
            d = self.store[c.idx]["doc_id"]
            if per_doc.get(d, 0) >= self.cfg.max_per_document:
                continue
            per_doc[d] = per_doc.get(d, 0) + 1
            out.append(c)
            if len(out) >= k:
                break
        return out

    def search(self, query: str | QueryInfo, k: int | None = None, mode: str = "full") -> tuple[QueryInfo, list[Candidate]]:
        """Modes: bm25, sif, dense, hybrid (RRF of bm25 and dense), entity (RRF with entity routing), full (reranked)."""
        q = query if isinstance(query, QueryInfo) else self.understand(query)
        k = k or self.cfg.final_k
        n = self.cfg.candidates_per_retriever
        if mode == "bm25":
            res = [Candidate(i, bm25=s, score=s) for i, s in self.bm25.search(q.tokens, n)]
            return q, self._diversify(res, k)
        if mode in ("sif", "dense"):
            res = [Candidate(i, dense=s, score=s) for i, s in self.dense_search(q.tokens, n, use_dual=(mode == "dense"))]
            return q, self._diversify(res, k)
        if mode == "hybrid":
            cands: dict[int, Candidate] = {}
            for r, (i, s) in enumerate(self.bm25.search(q.tokens, n)):
                cands.setdefault(i, Candidate(i)).rank_bm25 = r
            for r, (i, s) in enumerate(self.dense_search(q.tokens, n)):
                cands.setdefault(i, Candidate(i)).rank_dense = r
            for c in cands.values():
                c.score = sum(1.0 / (self.cfg.rrf_k + r + 1) for r in (c.rank_bm25, c.rank_dense) if r is not None)
            return q, self._diversify(sorted(cands.values(), key=lambda c: -c.score), k)
        cands = self.candidates(q, n)
        if mode == "entity" or self.reranker is None:
            for c in cands.values():
                c.score = c.rrf
            return q, self._diversify(sorted(cands.values(), key=lambda c: -c.score), k)
        X = self.featurise(q, cands)
        scores = self.reranker.predict(X)
        for c, s in zip(cands.values(), scores):
            c.score = float(s)
        return q, self._diversify(sorted(cands.values(), key=lambda c: -c.score), k)

    def result_dict(self, c: Candidate, rank: int) -> dict:
        p = self.store[c.idx]
        return {
            "rank": rank,
            "pid": p["pid"],
            "doc_id": p["doc_id"],
            "source_type": p["source_type"],
            "evidence_level": p["evidence_level"],
            "evidence_label": p["evidence_label"],
            "title": p["title"],
            "section": p.get("section", ""),
            "text": p["text"],
            "url": p.get("url", ""),
            "drugs": p.get("drugs", []),
            "reactions": p.get("reactions", []),
            "region": p.get("region"),
            "references": p.get("references"),
            "score": round(c.score, 4),
            "scores": {"bm25": round(c.bm25, 3), "dense": round(c.dense, 3), "rrf": round(c.rrf, 4)},
        }
