"""Train the LightGBM LambdaMART reranker on synthetic, structure derived queries.

Queries are generated from the knowledge base itself (label sections, graph
facts, case report gold pairs, FAERS summaries, knowledge cards and
interaction texts) with brand names and lay phrases substituted at random.
The evaluation question sets are never used for training. Relevance is
graded: 2 for passages of the document the query was generated from, 1
for other passages that mention the same drug and reaction, 0 otherwise.
"""
from __future__ import annotations

import json
import random
import time

import numpy as np

from vigilix.config import SETTINGS
from vigilix.rag.dense import mine_question_pairs
from vigilix.rag.retriever import FEATURES, Retriever
from vigilix.rag.text import apply_spelling, canonical_term, lexicon, raw_tokens


def _norm(text: str) -> str:
    return " ".join(apply_spelling(t) for t in raw_tokens(text))


def build_training_set(retriever: Retriever, n_queries: int = 4500, seed: int = 99, verbose: bool = True):
    rng = random.Random(seed)
    store = retriever.store
    lay_reverse: dict[str, list[str]] = {}
    for lay, clinical in lexicon()["lay_terms"].items():
        lay_reverse.setdefault(canonical_term(clinical), []).append(lay)
    pairs = mine_question_pairs(store.passages, retriever.drugs, lay_reverse, seed=seed, per_kind=1800)
    by_kind: dict[str, list] = {}
    for item in pairs:
        by_kind.setdefault(item[2], []).append(item)
    # balance kinds so frequent templates do not dominate
    quota = max(60, n_queries // max(len(by_kind), 1))
    chosen = []
    for kind, items in by_kind.items():
        chosen += items[:quota]
    rng.shuffle(chosen)
    chosen = chosen[:n_queries]
    X, y, groups, meta = [], [], [], []
    t0 = time.time()
    for qi, (text, target, kind) in enumerate(chosen):
        q = retriever.understand(text)
        cands = retriever.candidates(q)
        if not cands:
            continue
        feats = retriever.featurise(q, cands)
        tdoc = store[target]["doc_id"]
        labels = []
        for c in cands.values():
            p = store[c.idx]
            if p["doc_id"] == tdoc:
                labels.append(2)
                continue
            text_n = _norm(p["title"] + " " + p["text"])
            ok_d = any(d in p.get("drugs", []) for d in q.drugs) if q.drugs else False
            ok_r = any(r in p.get("reactions", []) or _norm(r) in text_n for r in q.reactions) if q.reactions else False
            labels.append(1 if (ok_d and ok_r) else 0)
        if max(labels) == 0:
            continue
        X.append(feats)
        y.append(np.array(labels))
        groups.append(len(labels))
        meta.append({"query": text, "kind": kind})
        if verbose and qi % 500 == 0:
            print(f"    {qi} queries featurised ({time.time() - t0:.0f}s)", flush=True)
    return np.vstack(X), np.concatenate(y), np.array(groups), meta


LEXICAL_DROP = {"dense_cos", "dense_gap", "rr_dense", "rrf"}
LEXICAL_FEATURES = [f for f in FEATURES if f not in LEXICAL_DROP]


def _fit(X, y, groups, names, verbose: bool):
    import lightgbm as lgb

    n_q = len(groups)
    rng = np.random.default_rng(SETTINGS.random_seed)
    perm = rng.permutation(n_q)
    val_q = set(perm[: max(1, n_q // 10)].tolist())
    offsets = np.concatenate([[0], np.cumsum(groups)])
    tr_rows = np.concatenate([np.arange(offsets[i], offsets[i + 1]) for i in range(n_q) if i not in val_q])
    va_rows = np.concatenate([np.arange(offsets[i], offsets[i + 1]) for i in range(n_q) if i in val_q])
    g_tr = [groups[i] for i in range(n_q) if i not in val_q]
    g_va = [groups[i] for i in range(n_q) if i in val_q]
    dtrain = lgb.Dataset(X[tr_rows], y[tr_rows], group=g_tr, feature_name=list(names))
    dval = lgb.Dataset(X[va_rows], y[va_rows], group=g_va, feature_name=list(names), reference=dtrain)
    params = {
        "objective": "lambdarank", "metric": "ndcg", "ndcg_eval_at": [5, 10], "learning_rate": 0.05, "num_leaves": 31,
        "min_data_in_leaf": 40, "feature_fraction": 0.85, "bagging_fraction": 0.85, "bagging_freq": 1, "lambda_l2": 1.0,
        "verbose": -1, "seed": SETTINGS.random_seed, "num_threads": 2,
    }
    evals: dict = {}
    model = lgb.train(params, dtrain, num_boost_round=600, valid_sets=[dval], valid_names=["val"], callbacks=[lgb.early_stopping(50, verbose=False), lgb.record_evaluation(evals)])
    return model, evals


def train_lexical(verbose: bool = True) -> dict:
    """A reranker without the dense features, for the in browser engine."""
    z = np.load(SETTINGS.paths.artifacts / "reranker_train.npz")
    cols = [FEATURES.index(f) for f in LEXICAL_FEATURES]
    model, evals = _fit(z["X"][:, cols], z["y"], z["groups"], LEXICAL_FEATURES, verbose)
    model.save_model(str(SETTINGS.paths.artifacts / "reranker_lexical.txt"), num_iteration=model.best_iteration)
    info = {"features": LEXICAL_FEATURES, "best_iteration": int(model.best_iteration), "val_ndcg@10": round(float(evals["val"]["ndcg@10"][model.best_iteration - 1]), 4)}
    (SETTINGS.paths.artifacts / "reranker_lexical_info.json").write_text(json.dumps(info, indent=2))
    if verbose:
        print("lexical reranker", info["val_ndcg@10"])
    return info


def train(verbose: bool = True) -> dict:
    import lightgbm as lgb

    retriever = Retriever.load(with_reranker=False)
    X, y, groups, meta = build_training_set(retriever, verbose=verbose)
    np.savez_compressed(SETTINGS.paths.artifacts / "reranker_train.npz", X=X, y=y, groups=groups)
    n_q = len(groups)
    model, evals = _fit(X, y, groups, FEATURES, verbose)
    art = SETTINGS.paths.artifacts
    model.save_model(str(art / "reranker.txt"), num_iteration=model.best_iteration)
    gain = model.feature_importance("gain")
    imp = sorted(zip(FEATURES, (gain / gain.sum()).round(4).tolist()), key=lambda kv: -kv[1])
    info = {
        "queries": n_q,
        "rows": int(len(y)),
        "positives": int((y > 0).sum()),
        "best_iteration": int(model.best_iteration),
        "val_ndcg@5": round(float(evals["val"]["ndcg@5"][model.best_iteration - 1]), 4),
        "val_ndcg@10": round(float(evals["val"]["ndcg@10"][model.best_iteration - 1]), 4),
        "feature_importance": imp,
        "kinds": dict(__import__("collections").Counter(m["kind"] for m in meta)),
    }
    (art / "reranker_info.json").write_text(json.dumps(info, indent=2))
    if verbose:
        print(json.dumps({k: v for k, v in info.items() if k != "feature_importance"}, indent=2))
        print("top features:", imp[:12])
    train_lexical(verbose)
    return info


if __name__ == "__main__":
    train()
