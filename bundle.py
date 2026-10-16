"""Export the offline browser bundle used by the hosted demo.

The bundle lets the React interface run the whole system in a visitor's
browser with no server: a subset of the corpus with a packed BM25 index, the
lexical LightGBM reranker, the claim verifier, the full knowledge graph, all
FAERS signal scores, every label section, the interaction tables, the
dictionaries and the evaluation reports. Large files are gzip compressed and
decompressed in the browser with DecompressionStream.
"""
from __future__ import annotations

import gzip
import json
import random
import shutil
import struct
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from vigilix.config import SETTINGS
from vigilix.rag.bm25 import BM25Index
from vigilix.rag.build_index import passage_tokens
from vigilix.rag.store import PassageStore

SOURCE_TYPES = ["guidance_card", "drug_label", "trial_abstract", "signal_summary", "kg_fact", "interaction_monograph", "cid_abstract", "interaction_abstract", "case_report"]
TRIAL_SAMPLE = 7000


def _gz(path: Path, obj) -> int:
    data = json.dumps(obj, separators=(",", ":")).encode()
    with gzip.open(path, "wb", compresslevel=9) as fh:
        fh.write(data)
    return path.stat().st_size


def select_passages(store: PassageStore, seed: int) -> list[int]:
    rng = random.Random(seed)
    keep = [i for i, p in enumerate(store.passages) if p["source_type"] != "trial_abstract"]
    trials = [
        i
        for i, p in enumerate(store.passages)
        if p["source_type"] == "trial_abstract" and p["drugs"] and p["reactions"] and any(r in ("results", "conclusions") for r in p.get("roles", []))
    ]
    keep += sorted(rng.sample(trials, min(TRIAL_SAMPLE, len(trials))))
    return sorted(keep)


def pack_bm25(index: BM25Index) -> tuple[list[str], bytes]:
    w = index.weights.tocsc()
    terms = sorted(index.vocab, key=index.vocab.get)
    V = len(terms)
    offsets = w.indptr.astype(np.uint32)
    scales = np.zeros(V, dtype=np.float32)
    weights = np.zeros(len(w.data), dtype=np.uint8)
    for j in range(V):
        a, b = w.indptr[j], w.indptr[j + 1]
        if b > a:
            mx = float(w.data[a:b].max())
            scales[j] = mx
            weights[a:b] = np.clip(np.round(w.data[a:b] / mx * 255), 1, 255).astype(np.uint8)
    docs = w.indices.astype(np.uint16)
    return terms, offsets.tobytes() + scales.tobytes() + docs.tobytes() + weights.tobytes()


def dict_payload(d) -> dict:
    keep_attrs = {"drug": ("atc", "atc_classes", "brands", "pharmacologic_classes", "anatomical_group"), "reaction": ("soc",)}[d.kind]
    entries = {}
    for c, e in d.entries.items():
        item = {"display": e.display, "synonyms": sorted(e.synonyms)}
        for k in keep_attrs:
            if k in e.attrs:
                item[k] = e.attrs[k]
        entries[c] = item
    return {
        "kind": d.kind,
        "entries": entries,
        "index": {" ".join(k): v for k, v in d._index.items()},
        "linkable": {" ".join(k): v for k, v in d._linkable.items()},
        "max_len": d.max_len,
    }


def graph_payload(kg: dict) -> dict:
    ids = {n["id"]: i for i, n in enumerate(kg["nodes"])}
    nodes = [[n["id"], n["kind"], n["name"], n.get("soc") if n["kind"] == "reaction" else n.get("atc") if n["kind"] == "drug" else n.get("code")] for n in kg["nodes"]]
    rels = sorted({e["rel"] for e in kg["edges"]})
    sources = sorted({s for e in kg["edges"] for s in e["sources"]})
    ri = {r: i for i, r in enumerate(rels)}
    si = {s: i for i, s in enumerate(sources)}
    edges = []
    for e in kg["edges"]:
        attrs = {k: v for k, v in e.items() if k not in ("src", "dst", "rel", "sources", "evidence", "weight")}
        row = [ids[e["src"]], ids[e["dst"]], ri[e["rel"]], [si[s] for s in e["sources"]], e["evidence"], round(float(e["weight"]), 3)]
        if attrs:
            row.append(attrs)
        edges.append(row)
    return {"nodes": nodes, "rels": rels, "sources": sources, "edges": edges}


def export(out_dir: Path | None = None, verbose: bool = True) -> dict:
    from vigilix.api.services import Services
    from vigilix.kb.dictionaries import load_dictionaries

    t0 = time.time()
    out = out_dir or SETTINGS.paths.frontend_public / "data"
    if out.exists():
        shutil.rmtree(out)
    (out / "figures").mkdir(parents=True)
    paths = SETTINGS.paths
    sizes: dict[str, int] = {}

    store = PassageStore.load()
    full, _ = passage_tokens(store)
    sel = select_passages(store, SETTINGS.random_seed)
    if len(sel) >= 65535:
        raise ValueError("browser subset too large for 16 bit document ids")
    sub_tokens = [full[i] for i in sel]
    bm = BM25Index(SETTINGS.retrieval.bm25_k1, SETTINGS.retrieval.bm25_b).fit(sub_tokens)
    terms, blob = pack_bm25(bm)
    sizes["bm25_terms.json.gz"] = _gz(out / "bm25_terms.json.gz", terms)
    with gzip.open(out / "bm25.bin.gz", "wb", compresslevel=9) as fh:
        fh.write(blob)
    sizes["bm25.bin.gz"] = (out / "bm25.bin.gz").stat().st_size
    labels_of = {st: (p["evidence_level"], p["evidence_label"]) for p in store.passages for st in [p["source_type"]]}
    rows = []
    for i in sel:
        p = store.passages[i]
        rows.append([p["pid"], p["doc_id"], SOURCE_TYPES.index(p["source_type"]), p["title"], p.get("section", ""), p["text"], p.get("url", ""), p["drugs"], p["reactions"], p.get("roles", []), p.get("region"), p.get("references")])
    sizes["passages.json.gz"] = _gz(out / "passages.json.gz", {"source_types": SOURCE_TYPES, "levels": {k: v for k, v in labels_of.items()}, "rows": rows})

    drugs, reactions = load_dictionaries(paths.processed / "dictionaries.json")
    sizes["dicts.json.gz"] = _gz(out / "dicts.json.gz", {"drugs": dict_payload(drugs), "reactions": dict_payload(reactions)})
    shutil.copy(paths.knowledge / "lexicon.json", out / "lexicon.json")
    shutil.copy(paths.knowledge / "pk_interactions.json", out / "pk.json")
    shutil.copy(paths.artifacts / "verifier.json", out / "verifier.json")

    import lightgbm as lgb

    model = lgb.Booster(model_file=str(paths.artifacts / "reranker_lexical.txt")).dump_model()
    sizes["reranker.json.gz"] = _gz(out / "reranker.json.gz", {"feature_names": model["feature_names"], "tree_info": [{"tree_structure": t["tree_structure"]} for t in model["tree_info"]]})

    kg = json.loads((paths.processed / "kg.json").read_text())
    sizes["graph.json.gz"] = _gz(out / "graph.json.gz", graph_payload(kg))

    svc = Services()
    sc = svc.scored
    cols = ["dataset", "drug", "pt", "soc", "a", "b", "c", "d", "expected", "prr", "prr_lo", "prr_hi", "ror", "ror_lo", "ror_hi", "chi2", "q_value", "ic", "ic025", "ic975", "ebgm", "eb05", "eb95", "evans", "ror_signal", "ic_signal", "eb_signal", "signal_votes", "labelled", "label_known", "cluster_flag"]
    data = []
    for r in sc[cols].itertuples(index=False):
        row = []
        for v in r:
            if isinstance(v, (float, np.floating)):
                row.append(None if not np.isfinite(v) else round(float(v), 4))
            elif isinstance(v, (bool, np.bool_)):
                row.append(int(v))
            elif isinstance(v, (np.integer,)):
                row.append(int(v))
            else:
                row.append(v)
        data.append(row)
    sizes["signals.json.gz"] = _gz(out / "signals.json.gz", {"columns": cols, "rows": data, "datasets": svc.datasets(), "priors": svc.priors["priors"]})
    sizes["labels.json.gz"] = _gz(out / "labels.json.gz", svc.labels)
    from vigilix.interactions.checker import ddi_sentences

    sizes["ddi.json.gz"] = _gz(out / "ddi.json.gz", ddi_sentences())
    (out / "overview.json").write_text(json.dumps(svc.overview()))
    ev = paths.reports / "evaluation_summary.json"
    if ev.exists():
        shutil.copy(ev, out / "evaluation.json")
    for f in paths.figures.glob("*.png"):
        shutil.copy(f, out / "figures" / f.name)
    # parity fixture for the TypeScript port of the normaliser
    probes = [
        "Does Lipitor cause muscle pain and rhabdomyolysis?",
        "QT-prolongation with Cipralex in elderly patients",
        "Haemorrhage risk of Xarelto plus NSAIDs; angio-oedema and lymphoedema",
        "SJS after co-trimoxazole, diarrhoea, oedema, paediatric hospitalised",
        "HR 0.85 (95% CI 0.70 to 1.02), 12.5% vs 5,248,821 reports",
        "Low blood sugar with glibenclamide in renal impairment",
        "St John's wort and ciclosporin; paracetamol overdose in children",
    ]
    from vigilix.rag.text import analyse, canonical_drug, canonical_term, numbers

    fixture = [{"text": t, "analyse": analyse(t), "numbers": numbers(t), "drug": canonical_drug(t.split()[0]), "term": canonical_term(t.split(";")[0])} for t in probes]
    (out / "parity_fixture.json").write_text(json.dumps(fixture, indent=1))
    manifest = {
        "version": "1.0.0",
        "built": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "passages": len(sel),
        "passages_by_source": dict(Counter(store.passages[i]["source_type"] for i in sel)),
        "full_corpus_passages": len(store),
        "files": sizes,
        "total_bytes": int(sum(sizes.values())),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    if verbose:
        print(json.dumps(manifest, indent=2), f"\n{time.time() - t0:.1f}s")
    return manifest


if __name__ == "__main__":
    export()
