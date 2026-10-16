"""Application services shared by the API routes and the demo exporter."""
from __future__ import annotations

import json
import math
import re
from functools import cached_property

import numpy as np
import pandas as pd

from vigilix.config import SETTINGS
from vigilix.eval.signal_eval import ADMIN
from vigilix.data.sources import faers_dataset_notes
from vigilix.extraction.labels import extract_terms
from vigilix.rag.text import canonical_drug, canonical_term
from vigilix.signals import disproportionality as dp


def _clean(v):
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else round(f, 4)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


class Services:
    def __init__(self, pipeline=None):
        from vigilix.rag.pipeline import Pipeline

        self.pipeline = pipeline or Pipeline()
        self.retriever = self.pipeline.retriever
        self.graph = self.retriever.graph
        self.drugs = self.retriever.drugs
        self.reactions = self.retriever.reactions

    # ------------------------------------------------------------------ data
    @cached_property
    def scored(self) -> pd.DataFrame:
        df = pd.read_csv(SETTINGS.paths.processed / "faers_scored.csv.gz")
        if "cluster_flag" not in df.columns:
            df["cluster_flag"] = dp.detect_report_clusters(df)
        return df

    @cached_property
    def priors(self) -> dict:
        return json.loads((SETTINGS.paths.processed / "faers_priors.json").read_text())

    @cached_property
    def labels(self) -> list[dict]:
        return json.loads((SETTINGS.paths.processed / "labels.json").read_text())

    @cached_property
    def labels_by_id(self) -> dict:
        return {l["doc_id"]: l for l in self.labels}

    @cached_property
    def build_stats(self) -> dict:
        return json.loads((SETTINGS.paths.processed / "build_stats.json").read_text())

    @cached_property
    def evaluation(self) -> dict:
        p = SETTINGS.paths.reports / "evaluation_summary.json"
        return json.loads(p.read_text()) if p.exists() else {}

    @cached_property
    def extractor(self):
        from vigilix.extraction.ade import ADEExtractor

        p = SETTINGS.paths.artifacts / "ade_extractor.pkl"
        return ADEExtractor.load(self.drugs, self.reactions, p) if p.exists() else None

    # ------------------------------------------------------------- overview
    def overview(self) -> dict:
        s = self.build_stats
        ev = self.evaluation
        sc = self.scored
        top = sc[(sc["eb_signal"]) & (~sc["labelled"]) & (sc["label_known"]) & (~sc["cluster_flag"]) & (sc["a"] >= 10) & (~sc["pt"].str.contains(ADMIN))].sort_values("eb05", ascending=False).head(12)
        retrieval = ev.get("retrieval", {})
        return {
            "kb": {k: s.get(k) for k in ("passages", "documents", "words", "drugs", "reactions", "kg_nodes", "kg_edges", "faers_pairs", "faers_signals_eb05", "label_sections", "label_annotated_events", "case_reports", "cdr_abstracts", "ddi_documents", "pubmed_kept", "knowledge_cards")},
            "passages_by_source": s.get("passages_by_source", {}),
            "kg_relations": s.get("kg_relations", {}),
            "datasets": self.datasets(),
            "evaluation": {
                "retrieval_dev": retrieval.get("dev", {}).get("full"),
                "retrieval_blind": retrieval.get("blind", {}).get("full"),
                "answers": {k: v for k, v in ev.get("answers", {}).items() if k != "safety_probes"},
                "safety_probes": ev.get("answers", {}).get("safety_probes", []),
                "verifier_auroc": ev.get("verifier", {}).get("auroc"),
                "ade": {k: ev.get("ade", {}).get(k, {}).get("f1") for k in ("drug_spans_crf", "effect_spans_crf", "relations_end_to_end_crf")},
                "labels_f1": ev.get("labels", {}).get("by_group", {}).get("all", {}).get("f1"),
            },
            "top_unlabelled_signals": [self._row(r) for r in top.to_dict("records")],
        }

    # ---------------------------------------------------------------- drugs
    def suggest(self, q: str, kind: str = "drug", limit: int = 12) -> list[dict]:
        q = q.strip().lower()
        if len(q) < 2:
            return []
        d = self.drugs if kind == "drug" else self.reactions
        hits = []
        for e in d.entries.values():
            names = [e.canonical] + [s for s in e.synonyms if s != e.canonical]
            best = None
            for n in names:
                if n.startswith(q):
                    best = (0 if n == e.canonical else 1, len(n))
                    break
                if q in n and best is None:
                    best = (2, len(n))
            if best is not None:
                in_graph = f"{kind}:{e.canonical}" in self.graph.nodes
                hits.append((best[0], -int(in_graph), best[1], e))
        hits.sort(key=lambda x: x[:3])
        return [{"name": e.canonical, "display": e.display, "match": [s for s in e.synonyms if q in s][:2], "atc": (e.attrs.get("atc") or [None])[0], "soc": e.attrs.get("soc")} for *_, e in hits[:limit]]

    def drug(self, name: str) -> dict:
        c = canonical_drug(name)
        entry = self.drugs.lookup(name) or self.drugs.entries.get(c)
        if entry is not None:
            c = entry.canonical
        prof = self.graph.drug_profile(c)
        labels = [
            {"doc_id": l["doc_id"], "region": l["region"], "section": l["section"], "brand": l["brand"], "events": len(l["events"])}
            for l in self.labels
            if l["substance"] and canonical_drug(l["substance"]) == c
        ]
        sig = self.scored[self.scored["drug"] == c]
        faers = []
        for ds, part in sig.groupby("dataset"):
            faers.append(
                {
                    "dataset": ds,
                    "pairs": int(part["a"].sum()),
                    "terms": int(len(part)),
                    "signals": int(part["eb_signal"].sum()),
                    "unlabelled_signals": int((part["eb_signal"] & ~part["labelled"]).sum()) if bool(part["label_known"].iloc[0]) else None,
                    "label_coverage": bool(part["label_known"].iloc[0]),
                }
            )
        return {
            "drug": c,
            "entry": entry.to_json() if entry else None,
            "profile": prof,
            "labels": labels,
            "faers": faers,
            "subgraph": self.graph.subgraph(c),
        }

    def reaction(self, name: str) -> dict:
        c = canonical_term(name)
        entry = self.reactions.lookup(name)
        if entry is not None:
            c = entry.canonical
        prof = self.graph.reaction_profile(c)
        sig = self.scored[self.scored["pt"].str.lower().map(canonical_term) == c] if c else self.scored.iloc[0:0]
        return {"reaction": c, "entry": entry.to_json() if entry else None, "profile": prof, "faers": [self._row(r) for r in sig.sort_values("eb05", ascending=False).head(30).to_dict("records")]}

    # -------------------------------------------------------------- signals
    def datasets(self) -> list[dict]:
        notes = faers_dataset_notes()
        out = []
        for ds, part in self.scored.groupby("dataset"):
            out.append(
                {
                    "dataset": ds,
                    "note": notes.get(ds, ""),
                    "period": part["period"].iloc[0],
                    "drugs": sorted(part["drug"].unique().tolist()),
                    "terms": int(part["pt"].nunique()),
                    "pairs": int(len(part)),
                    "signals": int(part["eb_signal"].sum()),
                    "prior": self.priors["priors"].get(ds),
                }
            )
        return out

    @staticmethod
    def _row(r: dict) -> dict:
        keys = ("dataset", "drug", "pt", "soc", "a", "b", "c", "d", "expected", "prr", "prr_lo", "prr_hi", "ror", "ror_lo", "ror_hi", "chi2", "q_value", "ic", "ic025", "ic975", "ebgm", "eb05", "eb95", "evans", "ror_signal", "ic_signal", "eb_signal", "signal_votes", "labelled", "label_known", "cluster_flag")
        return {k: _clean(r.get(k)) for k in keys}

    def signals(self, dataset: str | None = None, drug: str | None = None, min_cases: int = 0, only_signals: bool = False, unlabelled: bool = False, hide_clusters: bool = False, soc: str | None = None, q: str | None = None, sort: str = "eb05", limit: int = 500) -> dict:
        df = self.scored
        if dataset:
            df = df[df["dataset"] == dataset]
        if drug:
            df = df[df["drug"] == canonical_drug(drug)]
        if min_cases:
            df = df[df["a"] >= min_cases]
        if only_signals:
            df = df[df["eb_signal"]]
        if unlabelled:
            df = df[(~df["labelled"]) & (df["label_known"])]
        if hide_clusters:
            df = df[~df["cluster_flag"]]
        if soc:
            df = df[df["soc"] == soc]
        if q:
            df = df[df["pt"].str.contains(q, case=False, regex=False)]
        sort = sort if sort in df.columns else "eb05"
        df = df.sort_values(sort, ascending=False)
        return {"total": int(len(df)), "rows": [self._row(r) for r in df.head(limit).to_dict("records")], "socs": sorted(self.scored["soc"].dropna().unique().tolist())}

    def compute(self, a: int, b: int, c: int, d: int, dataset: str | None = None) -> dict:
        df = pd.DataFrame([{"a": a, "b": b, "c": c, "d": d}])
        prior_d = self.priors["priors"].get(dataset or "sedatives")
        prior = dp.GammaMixturePrior(prior_d["alpha1"], prior_d["beta1"], prior_d["alpha2"], prior_d["beta2"], prior_d["p"], prior_d["loglik"])
        scored, _ = dp.score_table(df, prior=prior)
        row = {k: _clean(v) for k, v in scored.iloc[0].to_dict().items()}
        row["prior_dataset"] = dataset or "sedatives"
        return row

    # --------------------------------------------------------------- labels
    def label_list(self, region: str | None = None, q: str | None = None, limit: int = 400) -> list[dict]:
        out = []
        for l in self.labels:
            if region and l["region"] != region:
                continue
            name = l["substance"] or l["brand"] or l["label_id"]
            if q and q.lower() not in (name + " " + (l["brand"] or "")).lower():
                continue
            out.append({"doc_id": l["doc_id"], "region": l["region"], "section": l["section"], "substance": l["substance"], "brand": l["brand"], "events": len(l["events"]), "chars": len(l["text"])})
        out.sort(key=lambda x: ((x["substance"] or x["brand"] or "zzz").lower(), x["section"]))
        return out[:limit]

    def label(self, doc_id: str) -> dict:
        l = self.labels_by_id[doc_id]
        mined = extract_terms(l["text"], self.reactions)
        gold = {canonical_term(e["pt"]) for e in l["events"]} | {canonical_term(e["mention"]) for e in l["events"]}
        gold_pt = sorted({canonical_term(e["pt"]) for e in l["events"]})
        pred = {m["term"] for m in mined if not m["negated"]}
        # character offsets for highlighting: find the first occurrence after a running cursor
        text = l["text"]
        low = text.lower()
        spans, cursor = [], 0
        for m in mined:
            for syn in sorted(self.reactions.entries[m["term"]].synonyms, key=len, reverse=True) if m["term"] in self.reactions.entries else [m["term"]]:
                i = low.find(syn, cursor)
                if i < 0:
                    i = low.find(syn)
                if i >= 0:
                    spans.append({"start": i, "end": i + len(syn), "term": m["term"], "negated": m["negated"], "gold": m["term"] in gold})
                    cursor = i + len(syn)
                    break
        conc = []
        if l["substance"]:
            sig = self.scored[self.scored["drug"] == canonical_drug(l["substance"])]
            if len(sig):
                sig = sig.assign(ptc=sig["pt"].map(canonical_term))
                for t in sorted(pred):
                    hit = sig[sig["ptc"] == t]
                    if len(hit):
                        r = hit.iloc[0]
                        conc.append({"term": t, "cases": int(r["a"]), "eb05": _clean(r["eb05"]), "signal": bool(r["eb_signal"])})
        tp = len(pred & gold)
        return {
            **{k: l[k] for k in ("doc_id", "region", "section", "substance", "brand", "label_id")},
            "text": text,
            "spans": spans,
            "gold_terms": gold_pt,
            "mined_terms": sorted(pred),
            "missed": sorted(t for t in gold_pt if t not in pred),
            "extra": sorted(t for t in pred if t not in gold),
            "precision": round(tp / len(pred), 3) if pred else None,
            "recall": round(len([t for t in gold_pt if t in pred]) / len(gold_pt), 3) if gold_pt else None,
            "faers_concordance": conc,
        }

    # ------------------------------------------------------- interactions
    def interactions(self, drugs: list[str]) -> dict:
        from vigilix.interactions.checker import check_regimen

        return check_regimen(drugs, self.graph)

    # ---------------------------------------------------------------- case
    def case_intake(self, narrative: str) -> dict:
        from vigilix.causality.assess import intake

        return intake(narrative, self.extractor, self.graph, self.drugs, self.reactions)

    def documents(self, doc_id: str) -> dict:
        idx = self.retriever.store.doc_to_idx.get(doc_id, [])
        ps = [self.retriever.store[i] for i in idx]
        if not ps:
            return {"doc_id": doc_id, "found": False}
        return {"doc_id": doc_id, "found": True, "title": ps[0]["title"], "source_type": ps[0]["source_type"], "url": ps[0].get("url"), "passages": [{"pid": p["pid"], "section": p.get("section"), "text": p["text"]} for p in ps]}
