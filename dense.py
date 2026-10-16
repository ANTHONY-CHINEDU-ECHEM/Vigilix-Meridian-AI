"""Dense retrieval trained entirely in domain.

No pretrained weights are required. Three layers are built from the corpus:

1. ``Word2Vec`` skip gram embeddings trained on the analysed text of every
   passage (about 20 million tokens of trial abstracts, labels, case
   reports and curated facts), so that "rhabdomyolysis" lands near
   "myopathy" and "creatine kinase".
2. Smooth inverse frequency (SIF) sentence vectors (Arora et al. 2017):
   a frequency weighted average of word vectors with the first principal
   component removed.
3. A dual encoder: two linear towers (query and passage) on top of the SIF
   vectors, trained with a symmetric in batch InfoNCE loss on about one
   hundred thousand query and passage pairs mined from the corpus structure
   (trial objectives against their results, card titles against card text,
   drug and reaction pairs against the case reports that describe them,
   inverse cloze sentences). Gradients are derived analytically and
   optimised with Adam in NumPy, so training runs on a laptop CPU.

A ``sentence_transformers`` backend (for example MedCPT) can replace the
whole stack with ``VIGILIX_DENSE=sentence_transformers`` when weights are
cached locally.
"""
from __future__ import annotations

import json
import math
import random
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np


# ---------------------------------------------------------------------------
# Word vectors and SIF
# ---------------------------------------------------------------------------
def train_word2vec(token_lists: list[list[str]], dim: int = 200, epochs: int = 5, seed: int = 7, workers: int = 2):
    from gensim.models import Word2Vec

    model = Word2Vec(
        sentences=token_lists,
        vector_size=dim,
        window=6,
        min_count=3,
        sg=1,
        negative=8,
        sample=1e-4,
        epochs=epochs,
        seed=seed,
        workers=workers,
    )
    return model


class SIFEncoder:
    def __init__(self, vocab: dict[str, int], vectors: np.ndarray, weights: np.ndarray, pc: np.ndarray | None = None):
        self.vocab = vocab
        self.vectors = vectors.astype(np.float32)
        self.weights = weights.astype(np.float32)
        self.pc = pc

    @classmethod
    def from_word2vec(cls, model, counts: Counter, a: float = 1e-3) -> "SIFEncoder":
        words = model.wv.index_to_key
        vocab = {w: i for i, w in enumerate(words)}
        total = sum(counts.values())
        weights = np.array([a / (a + counts.get(w, 1) / total) for w in words], dtype=np.float32)
        return cls(vocab, model.wv.vectors, weights)

    @property
    def dim(self) -> int:
        return self.vectors.shape[1]

    def _raw(self, tokens: list[str]) -> np.ndarray:
        ids = [self.vocab[t] for t in tokens if t in self.vocab]
        if not ids:
            return np.zeros(self.dim, dtype=np.float32)
        w = self.weights[ids]
        return (w[:, None] * self.vectors[ids]).sum(0) / max(len(ids), 1)

    def fit_pc(self, matrix: np.ndarray) -> None:
        sample = matrix[np.random.default_rng(0).choice(len(matrix), size=min(30000, len(matrix)), replace=False)]
        _, _, vt = np.linalg.svd(sample - 0.0, full_matrices=False)
        self.pc = vt[0].astype(np.float32)

    def encode(self, token_lists: list[list[str]]) -> np.ndarray:
        m = np.vstack([self._raw(t) for t in token_lists]).astype(np.float32)
        if self.pc is not None:
            m = m - np.outer(m @ self.pc, self.pc)
        return m

    def save(self, folder: Path, prefix: str = "sif") -> None:
        np.save(folder / f"{prefix}_vectors.npy", self.vectors.astype(np.float16))
        np.save(folder / f"{prefix}_weights.npy", self.weights)
        np.save(folder / f"{prefix}_pc.npy", self.pc if self.pc is not None else np.zeros(self.dim, dtype=np.float32))
        (folder / f"{prefix}_vocab.json").write_text(json.dumps(list(self.vocab)))

    @classmethod
    def load(cls, folder: Path, prefix: str = "sif") -> "SIFEncoder":
        words = json.loads((folder / f"{prefix}_vocab.json").read_text())
        enc = cls({w: i for i, w in enumerate(words)}, np.load(folder / f"{prefix}_vectors.npy").astype(np.float32), np.load(folder / f"{prefix}_weights.npy"))
        enc.pc = np.load(folder / f"{prefix}_pc.npy")
        return enc


# ---------------------------------------------------------------------------
# Dual encoder trained with in batch InfoNCE
# ---------------------------------------------------------------------------
def _l2(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n = np.linalg.norm(x, axis=1, keepdims=True) + 1e-8
    return x / n, n


@dataclass
class TrainLog:
    epoch: int
    loss: float
    val_mrr: float
    val_r1: float


class DualEncoder:
    """Two linear towers with L2 normalised outputs and a learned temperature."""

    def __init__(self, dim_in: int, dim_out: int = 256, seed: int = 0):
        rng = np.random.default_rng(seed)
        eye = np.eye(dim_in, dim_out, dtype=np.float32)
        self.wq = eye + 0.01 * rng.standard_normal((dim_in, dim_out)).astype(np.float32)
        self.wp = eye + 0.01 * rng.standard_normal((dim_in, dim_out)).astype(np.float32)
        self.log_tau = np.float32(math.log(0.05))
        self.history: list[TrainLog] = []
        self.mu = np.zeros(dim_in, dtype=np.float32)
        self.sd = np.ones(dim_in, dtype=np.float32)

    def _std(self, x: np.ndarray) -> np.ndarray:
        return (x - self.mu) / self.sd

    def encode_queries(self, x: np.ndarray) -> np.ndarray:
        return _l2(self._std(x) @ self.wq)[0].astype(np.float32)

    def encode_passages(self, x: np.ndarray) -> np.ndarray:
        return _l2(self._std(x) @ self.wp)[0].astype(np.float32)

    def _loss_grad(self, q: np.ndarray, p: np.ndarray, weight_decay: float):
        zq, zp = q @ self.wq, p @ self.wp
        uq, nq = _l2(zq)
        up, npn = _l2(zp)
        tau = math.exp(float(self.log_tau))
        s = (uq @ up.T) / tau
        b = len(q)
        # symmetric cross entropy, targets on the diagonal
        sr = s - s.max(1, keepdims=True)
        pr = np.exp(sr)
        pr /= pr.sum(1, keepdims=True)
        sc = s - s.max(0, keepdims=True)
        pc = np.exp(sc)
        pc /= pc.sum(0, keepdims=True)
        loss = -0.5 * (np.log(np.diag(pr) + 1e-12).mean() + np.log(np.diag(pc) + 1e-12).mean())
        eye = np.eye(b, dtype=np.float32)
        ds = 0.5 * ((pr - eye) + (pc - eye)) / b  # dL/ds
        duq = ds @ up / tau
        dup = ds.T @ uq / tau
        dlog_tau = -float((ds * s).sum())
        dzq = (duq - uq * (uq * duq).sum(1, keepdims=True)) / nq
        dzp = (dup - up * (up * dup).sum(1, keepdims=True)) / npn
        gq = q.T @ dzq + weight_decay * (self.wq - np.eye(*self.wq.shape, dtype=np.float32))
        gp = p.T @ dzp + weight_decay * (self.wp - np.eye(*self.wp.shape, dtype=np.float32))
        return float(loss), gq.astype(np.float32), gp.astype(np.float32), dlog_tau

    def evaluate(self, q: np.ndarray, p: np.ndarray, n: int = 2000) -> tuple[float, float]:
        q, p = q[:n], p[:n]
        uq = self.encode_queries(q)
        up = self.encode_passages(p)
        s = uq @ up.T
        ranks = (s > np.diag(s)[:, None]).sum(1)
        return float(np.mean(1.0 / (ranks + 1))), float(np.mean(ranks == 0))

    def fit(
        self,
        q: np.ndarray,
        p: np.ndarray,
        q_val: np.ndarray,
        p_val: np.ndarray,
        epochs: int = 6,
        batch: int = 256,
        lr: float = 2e-3,
        weight_decay: float = 1e-4,
        seed: int = 0,
        verbose: bool = True,
    ) -> "DualEncoder":
        self.mu = np.concatenate([q, p]).mean(0).astype(np.float32)
        self.sd = (np.concatenate([q, p]).std(0) + 1e-6).astype(np.float32)
        qs, ps = self._std(q), self._std(p)
        rng = np.random.default_rng(seed)
        m = {k: np.zeros_like(v) for k, v in (("wq", self.wq), ("wp", self.wp))}
        v = {k: np.zeros_like(x) for k, x in (("wq", self.wq), ("wp", self.wp))}
        mt, vt = 0.0, 0.0
        step = 0
        b1, b2 = 0.9, 0.999
        mrr0, r10 = self.evaluate(q_val, p_val)
        self.history.append(TrainLog(0, float("nan"), mrr0, r10))
        if verbose:
            print(f"    dual encoder epoch 0  val MRR {mrr0:.3f}  R@1 {r10:.3f}")
        best = (mrr0, self.wq.copy(), self.wp.copy(), self.log_tau)
        for ep in range(1, epochs + 1):
            order = rng.permutation(len(qs))
            losses = []
            for i in range(0, len(order) - batch + 1, batch):
                idx = order[i : i + batch]
                loss, gq, gp, gt = self._loss_grad(qs[idx], ps[idx], weight_decay)
                losses.append(loss)
                step += 1
                for name, g in (("wq", gq), ("wp", gp)):
                    m[name] = b1 * m[name] + (1 - b1) * g
                    v[name] = b2 * v[name] + (1 - b2) * g * g
                    mh = m[name] / (1 - b1**step)
                    vh = v[name] / (1 - b2**step)
                    setattr(self, name, (getattr(self, name) - lr * mh / (np.sqrt(vh) + 1e-8)).astype(np.float32))
                mt = b1 * mt + (1 - b1) * gt
                vt = b2 * vt + (1 - b2) * gt * gt
                self.log_tau = np.float32(np.clip(self.log_tau - lr * (mt / (1 - b1**step)) / (math.sqrt(vt / (1 - b2**step)) + 1e-8), math.log(0.01), math.log(1.0)))
            mrr, r1 = self.evaluate(q_val, p_val)
            self.history.append(TrainLog(ep, float(np.mean(losses)), mrr, r1))
            if verbose:
                print(f"    dual encoder epoch {ep}  loss {np.mean(losses):.3f}  val MRR {mrr:.3f}  R@1 {r1:.3f}  tau {math.exp(float(self.log_tau)):.3f}")
            if mrr > best[0]:
                best = (mrr, self.wq.copy(), self.wp.copy(), self.log_tau)
        _, self.wq, self.wp, self.log_tau = best
        return self

    def save(self, folder: Path) -> None:
        np.savez(folder / "dual_encoder.npz", wq=self.wq, wp=self.wp, log_tau=self.log_tau, mu=self.mu, sd=self.sd)
        (folder / "dual_encoder_history.json").write_text(json.dumps([h.__dict__ for h in self.history], indent=2))

    @classmethod
    def load(cls, folder: Path) -> "DualEncoder":
        z = np.load(folder / "dual_encoder.npz")
        enc = cls(z["wq"].shape[0], z["wq"].shape[1])
        enc.wq, enc.wp, enc.log_tau, enc.mu, enc.sd = z["wq"], z["wp"], z["log_tau"], z["mu"], z["sd"]
        return enc


# ---------------------------------------------------------------------------
# Training pair mining
# ---------------------------------------------------------------------------
def mine_pairs(passages: list[dict], tokens: list[list[str]], analyse, seed: int = 0, max_pairs: int = 140000) -> tuple[list[list[str]], list[int], list[str]]:
    """Return (query token lists, positive passage indices, pair kinds)."""
    rng = random.Random(seed)
    by_doc: dict[str, list[int]] = {}
    for i, p in enumerate(passages):
        by_doc.setdefault(p["doc_id"], []).append(i)
    qs: list[list[str]] = []
    pos: list[int] = []
    kinds: list[str] = []

    def add(q: str | list[str], i: int, kind: str) -> None:
        toks = analyse(q) if isinstance(q, str) else q
        if len(toks) >= 2:
            qs.append(toks)
            pos.append(i)
            kinds.append(kind)

    for doc, idxs in by_doc.items():
        p0 = passages[idxs[0]]
        st = p0["source_type"]
        if st == "trial_abstract":
            res = [i for i in idxs if any(r in ("results", "conclusions") for r in passages[i].get("roles", []))]
            target = res[-1] if res else idxs[-1]
            add(p0["title"], target, "objective_to_results")
            # inverse cloze: one sentence predicts the rest of its passage
            i = rng.choice(idxs)
            sents = [s for s in passages[i]["text"].split(". ") if len(s.split()) > 6]
            if len(sents) > 2:
                add(rng.choice(sents), i, "inverse_cloze")
        elif st in ("guidance_card", "kg_fact", "signal_summary", "drug_label", "interaction_monograph"):
            for i in idxs:
                add(passages[i]["title"], i, f"title_{st}")
        elif st in ("case_report", "cid_abstract"):
            gold = p0.get("gold_pairs") or []
            for d, r in gold[:3]:
                hits = [i for i in idxs if r.split()[0] in passages[i]["text"].lower()] or idxs
                add(f"{d} {r}", hits[0], f"pair_{st}")
            add(p0["title"], idxs[-1], f"title_{st}")
        elif st == "interaction_abstract":
            add(p0["title"], idxs[-1], "title_interaction")
    order = list(range(len(qs)))
    rng.shuffle(order)
    order = order[:max_pairs]
    return [qs[i] for i in order], [pos[i] for i in order], [kinds[i] for i in order]


# ---------------------------------------------------------------------------
# Question style pairs (also used to train the reranker)
# ---------------------------------------------------------------------------
QUESTION_TEMPLATES = {
    "adverse": [
        "does {drug} cause {reaction}",
        "{reaction} with {drug}",
        "can {drug} lead to {reaction}",
        "is {reaction} a known side effect of {drug}",
        "{drug} and {reaction}",
        "risk of {reaction} on {drug}",
        "{drug} induced {reaction}",
        "my patient on {drug} developed {reaction}",
    ],
    "label": [
        "{section} for {name}",
        "{name} {section}",
        "what does the {name} label say about {section}",
        "{name} prescribing information {section}",
    ],
    "signal": [
        "faers signals for {drug}",
        "{drug} spontaneous reports disproportionality",
        "is {reaction} reported more often with {drug} in faers",
        "{drug} {reaction} reporting odds ratio",
    ],
    "interaction": [
        "interaction between {a} and {b}",
        "can {a} be taken with {b}",
        "{a} plus {b}",
        "{a} {b} drug interaction",
    ],
    "card": ["what is {title}", "{title}", "explain {topic}", "{topic} guidance"],
}


def mine_question_pairs(passages: list[dict], drugs, lay_reverse: dict[str, list[str]], seed: int = 1, per_kind: int = 4000) -> list[tuple[str, int, str]]:
    """Template questions with lay terms and brand names mapped to target passages."""
    rng = random.Random(seed)

    def drug_alias(d: str) -> str:
        e = drugs.entries.get(d)
        brands = e.attrs.get("brands", []) if e else []
        if brands and rng.random() < 0.35:
            return rng.choice(brands)
        return d

    def reaction_alias(r: str) -> str:
        lay = lay_reverse.get(r)
        if lay and rng.random() < 0.4:
            return rng.choice(lay)
        return r

    out: list[tuple[str, int, str]] = []
    by_type: dict[str, list[int]] = {}
    for i, p in enumerate(passages):
        by_type.setdefault(p["source_type"], []).append(i)

    def sample(st: str, n: int) -> list[int]:
        idx = by_type.get(st, [])
        return rng.sample(idx, min(n, len(idx)))

    for i in sample("kg_fact", per_kind) + sample("case_report", per_kind // 2) + sample("cid_abstract", per_kind // 4) + sample("trial_abstract", per_kind):
        p = passages[i]
        if not p["drugs"] or not p["reactions"]:
            continue
        d = p["drugs"][0]
        r = rng.choice(p["reactions"][:8])
        if r.split()[0] not in p["text"].lower() and p["source_type"] != "kg_fact":
            continue
        out.append((rng.choice(QUESTION_TEMPLATES["adverse"]).format(drug=drug_alias(d), reaction=reaction_alias(r)), i, f"q_adverse_{p['source_type']}"))
    for i in sample("drug_label", per_kind):
        p = passages[i]
        name = p["title"].split(":")[0]
        if p["drugs"] and rng.random() < 0.5:
            name = drug_alias(p["drugs"][0])
        section = rng.choice([p.get("section", "adverse reactions").lower(), "side effects", "warnings", "undesirable effects"])
        out.append((rng.choice(QUESTION_TEMPLATES["label"]).format(name=name, section=section), i, "q_label"))
    for i in by_type.get("signal_summary", []):
        p = passages[i]
        d = p["drugs"][0] if p["drugs"] else p["title"].split(":")[0]
        r = rng.choice(p["reactions"]) if p["reactions"] else "adverse events"
        for _ in range(3):
            out.append((rng.choice(QUESTION_TEMPLATES["signal"]).format(drug=drug_alias(d), reaction=reaction_alias(r)), i, "q_signal"))
    for i in sample("interaction_monograph", per_kind // 2) + sample("interaction_abstract", 300):
        p = passages[i]
        if len(p["drugs"]) >= 2:
            a, b = rng.sample(p["drugs"][:4], 2)
            out.append((rng.choice(QUESTION_TEMPLATES["interaction"]).format(a=drug_alias(a), b=drug_alias(b)), i, "q_interaction"))
    for i in by_type.get("guidance_card", []):
        p = passages[i]
        title = p["title"].lower()
        topic = title.split(":")[0]
        for _ in range(6):
            out.append((rng.choice(QUESTION_TEMPLATES["card"]).format(title=title, topic=topic), i, "q_card"))
        for d in p["drugs"][:3]:
            for r in p["reactions"][:2]:
                out.append((rng.choice(QUESTION_TEMPLATES["adverse"]).format(drug=drug_alias(d), reaction=reaction_alias(r)), i, "q_card_pair"))
    rng.shuffle(out)
    return out
