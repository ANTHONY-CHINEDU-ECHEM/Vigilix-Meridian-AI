"""Build the retrieval artefacts: BM25, word vectors, SIF and the dual encoder."""
from __future__ import annotations

import gzip
import json
import pickle
import random
import time
from collections import Counter

import numpy as np

from vigilix.config import SETTINGS
from vigilix.rag.bm25 import BM25Index
from vigilix.kb.dictionaries import load_dictionaries
from vigilix.rag.dense import DualEncoder, SIFEncoder, mine_pairs, mine_question_pairs, train_word2vec
from vigilix.rag.text import canonical_term, lexicon
from vigilix.rag.store import PassageStore
from vigilix.rag.text import analyse


def passage_tokens(store: PassageStore, cache: bool = True) -> tuple[list[list[str]], list[list[str]]]:
    """(title plus text tokens for indexing, text only tokens for dense training)."""
    path = SETTINGS.paths.processed / "tokens.pkl"
    if cache and path.exists():
        return pickle.loads(path.read_bytes())
    full, text_only = [], []
    for p in store.passages:
        t = analyse(p["text"])
        title = analyse(p["title"]) if p["title"] else []
        text_only.append(t)
        full.append(title + t)
    path.write_bytes(pickle.dumps((full, text_only)))
    return full, text_only


def build_index(verbose: bool = True) -> dict:
    t0 = time.time()
    art = SETTINGS.paths.artifacts
    art.mkdir(parents=True, exist_ok=True)

    def log(msg: str) -> None:
        if verbose:
            print(f"[{time.time() - t0:6.1f}s] {msg}", flush=True)

    store = PassageStore.load()
    log(f"loaded {len(store)} passages")
    full, text_only = passage_tokens(store)
    log("tokenised")

    bm25 = BM25Index(SETTINGS.retrieval.bm25_k1, SETTINGS.retrieval.bm25_b).fit(full)
    bm25.save(art)
    log(f"bm25: {len(bm25.vocab)} terms")

    w2v_path = art / "word2vec.model"
    if w2v_path.exists():
        from gensim.models import Word2Vec

        w2v = Word2Vec.load(str(w2v_path))
    else:
        w2v = train_word2vec(full, dim=200, epochs=5)
        w2v.save(str(w2v_path))
    counts = Counter(t for toks in full for t in toks)
    sif = SIFEncoder.from_word2vec(w2v, counts)
    log(f"word2vec: {len(sif.vocab)} words")
    raw_full = sif.encode(full)
    sif.fit_pc(raw_full)
    sif.save(art)
    sif_full = sif.encode(full)
    sif_text = sif.encode(text_only)
    log("sif encoded")

    q_tokens, pos, kinds = mine_pairs(store.passages, full, analyse, seed=SETTINGS.random_seed)
    drugs, _ = load_dictionaries(SETTINGS.paths.processed / "dictionaries.json")
    lay_reverse: dict[str, list[str]] = {}
    for lay, clinical in lexicon()["lay_terms"].items():
        lay_reverse.setdefault(canonical_term(clinical), []).append(lay)
    for text, i, kind in mine_question_pairs(store.passages, drugs, lay_reverse, seed=SETTINGS.random_seed):
        toks = analyse(text)
        if len(toks) >= 2:
            q_tokens.append(toks)
            pos.append(i)
            kinds.append(kind)
    docs = [store.passages[i]["doc_id"] for i in pos]
    rng = random.Random(SETTINGS.random_seed)
    uniq = sorted(set(docs))
    rng.shuffle(uniq)
    val_docs = set(uniq[: max(1, len(uniq) // 20)])
    tr = [k for k, d in enumerate(docs) if d not in val_docs]
    va = [k for k, d in enumerate(docs) if d in val_docs]
    qv = sif.encode(q_tokens)
    pv = sif_text[np.array(pos)]
    log(f"mined {len(q_tokens)} pairs ({len(tr)} train, {len(va)} validation) kinds {dict(Counter(kinds))}")
    enc = DualEncoder(sif.dim, 256, seed=SETTINGS.random_seed).fit(qv[tr], pv[tr], qv[va], pv[va], epochs=6, verbose=verbose)
    enc.save(art)
    emb = enc.encode_passages(sif_full).astype(np.float16)
    np.save(art / "dense_passages.npy", emb)
    log("dual encoder trained and passages embedded")

    # Raw SIF cosine baseline for the ablation
    sif_norm = sif_full / (np.linalg.norm(sif_full, axis=1, keepdims=True) + 1e-8)
    np.save(art / "sif_passages.npy", sif_norm.astype(np.float16))
    stats = {
        "passages": len(store),
        "bm25_terms": len(bm25.vocab),
        "word2vec_vocab": len(sif.vocab),
        "training_pairs": len(tr),
        "validation_pairs": len(va),
        "pair_kinds": dict(Counter(kinds)),
        "dual_encoder_history": [h.__dict__ for h in enc.history],
        "seconds": round(time.time() - t0, 1),
    }
    (art / "index_stats.json").write_text(json.dumps(stats, indent=2))
    return stats


if __name__ == "__main__":
    build_index()
