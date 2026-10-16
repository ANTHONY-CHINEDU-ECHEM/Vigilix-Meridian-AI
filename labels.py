"""Adverse event mining from drug label safety sections.

Each label section is scanned with the reaction dictionary (longest match,
spelling folded, lay phrases mapped). Mentions in negated or exclusionary
context ("no cases of", "not observed", "was not associated with") are
dropped, as are section headings and frequency vocabulary. The predicted set
of terms is compared with the manually annotated adverse events of the same
section (Demner Fushman et al. for US labels; OnSIDES annotations for UK,
EU and US paediatric sections) at the level of normalised terms.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict

from vigilix.config import SETTINGS
from vigilix.kb.dictionaries import load_dictionaries
from vigilix.rag.text import apply_spelling, canonical_term, raw_tokens

NEGATION_WINDOW = re.compile(r"\b(no|not|without|absence of|did not|was not|were not|no cases of|none of|rule out|ruled out)\b[^.;:]{0,60}$", re.I)
GENERIC = {
    "adverse reaction", "adverse reactions", "adverse event", "adverse events", "reaction", "reactions", "toxicity", "death", "infection", "pain",
    "disorder", "disorders", "syndrome", "disease", "symptoms", "drug interaction", "overdose",
}


def _is_heading(term: str) -> bool:
    """System Organ Class names and other headings are not adverse events."""
    return term.endswith(" disorders") or term.endswith(" conditions") or term in {"investigations", "surgical and medical procedures", "social circumstances", "causality", "adrs", "adr", "antiretroviral therapy"}


def extract_terms(text: str, reactions) -> list[dict]:
    out = []
    toks_raw = raw_tokens(text)
    for canon, a, b in reactions.link(text):
        if canon in GENERIC or _is_heading(canon):
            continue
        # approximate character position for negation look back
        prefix = " ".join(toks_raw[max(0, a - 12) : a])
        negated = bool(NEGATION_WINDOW.search(prefix))
        out.append({"term": canon, "negated": negated, "token_start": a, "token_end": b})
    return out


def evaluate_labels(verbose: bool = True) -> dict:
    labels = json.loads((SETTINGS.paths.processed / "labels.json").read_text())
    _, reactions = load_dictionaries(SETTINGS.paths.processed / "dictionaries.json")
    by_group = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "sections": 0})
    examples = []
    for lab in labels:
        if lab["region"] == "US" and lab["split"] != "test":
            continue  # the US training split was used to inspect formats; score on its test split only
        gold = {canonical_term(e["pt"]) for e in lab["events"]} | {canonical_term(e["mention"]) for e in lab["events"]}
        gold_pt = {canonical_term(e["pt"]) for e in lab["events"]}
        if not gold_pt:
            continue
        pred = {t["term"] for t in extract_terms(lab["text"], reactions) if not t["negated"]}
        # a prediction is correct when it matches either the annotated mention or its preferred term
        tp = len({p for p in pred if p in gold})
        fp = len(pred) - tp
        fn = len({g for g in gold_pt if g not in pred and not any(m in pred for m in _mentions_for(lab, g))})
        key = f"{lab['region']} | {lab['section']}"
        for k in (key, lab["region"], "all"):
            g = by_group[k]
            g["tp"] += tp
            g["fp"] += fp
            g["fn"] += fn
            g["sections"] += 1
        if len(examples) < 5 and lab["region"] in ("UK", "EU"):
            examples.append({"label": lab["label_id"], "substance": lab["substance"], "missed": sorted(set(gold_pt) - pred)[:8], "extra": sorted(pred - gold)[:8]})
    out = {}
    for k, g in sorted(by_group.items()):
        p = g["tp"] / (g["tp"] + g["fp"]) if g["tp"] + g["fp"] else 0.0
        r = g["tp"] / (g["tp"] + g["fn"]) if g["tp"] + g["fn"] else 0.0
        out[k] = {"sections": g["sections"], "precision": round(p, 3), "recall": round(r, 3), "f1": round(2 * p * r / (p + r), 3) if p + r else 0.0}
    res = {"by_group": out, "examples": examples}
    (SETTINGS.paths.reports / "label_mining.json").write_text(json.dumps(res, indent=2))
    if verbose:
        for k, v in out.items():
            print(f"  {k:60s} {v}")
    return res


def _mentions_for(lab: dict, pt: str) -> set[str]:
    return {canonical_term(e["mention"]) for e in lab["events"] if canonical_term(e["pt"]) == pt}


if __name__ == "__main__":
    evaluate_labels()
