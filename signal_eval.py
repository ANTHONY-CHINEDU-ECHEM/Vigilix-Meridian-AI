"""Evaluation of the disproportionality screen against label derived truth.

Reference: a drug and preferred term pair is positive when the reaction is
listed for that drug in SIDER 4.1 or in the annotated labels. Only drugs
with label coverage of at least 20 terms are scored (atorvastatin and the
COVID 19 products lack coverage in the reference and are excluded), and only
pairs with at least three reports, the minimum for any screening rule.
Administrative and product quality terms are removed because labels never
list them. This is the standard, if imperfect, way of benchmarking signal
detection: labels are incomplete, so some "false positives" are real but
unlisted reactions and precision is a lower bound.
"""
from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from vigilix.config import SETTINGS

ADMIN = re.compile(r"(?:off label|product|device|wrong|medication error|inappropriate|no adverse event|drug ineffective|therapy|unevaluable|intentional|use issue|dose omission|incorrect|expired|accidental|exposure|interchange|label|packaging|counterfeit|transmission|prescribed|drug abuse|drug use disorder|treatment noncompliance|death|clinical trial participant|covid-19 treatment)", re.I)
EXCLUDED_SOC = {"Product issues", "Social circumstances", "Surgical and medical procedures"}

OUTCOME_PTS = {
    "Rhabdomyolysis": ["rhabdomyolysis"],
    "Upper gastrointestinal bleeding": ["gastrointestinal haemorrhage", "upper gastrointestinal haemorrhage", "haematemesis", "melaena", "gastric ulcer haemorrhage", "duodenal ulcer haemorrhage"],
    "Acute Renal Failure": ["acute kidney injury", "renal failure", "renal failure acute", "renal impairment"],
    "Acute myocardial infarction": ["myocardial infarction", "acute myocardial infarction"],
    "Aplastic Anemia": ["aplastic anaemia", "pancytopenia"],
    "Anaphylaxis": ["anaphylactic reaction", "anaphylactic shock"],
    "Stevens Johnson syndrome": ["stevens-johnson syndrome", "toxic epidermal necrolysis"],
    "Leukopenia": ["leukopenia", "neutropenia", "agranulocytosis"],
    "Acute Liver Failure": ["hepatic failure", "acute hepatic failure", "drug-induced liver injury", "hepatotoxicity"],
}

MEASURES = {"PRR": "prr", "ROR lower 95%": "ror_lo", "IC025": "ic025", "EB05": "eb05", "Report count": "a"}
RULES = {"Evans (PRR, chi square, n)": "evans", "ROR lower limit above 1": "ror_signal", "IC025 above 0": "ic_signal", "EB05 at least 2": "eb_signal"}


def screened_pairs(scored: pd.DataFrame) -> pd.DataFrame:
    df = scored[(scored["label_known"]) & (scored["a"] >= 3)].copy()
    df = df[~df["soc"].isin(EXCLUDED_SOC)]
    df = df[~df["pt"].str.contains(ADMIN)]
    return df


def evaluate(scored: pd.DataFrame | None = None) -> dict:
    if scored is None:
        scored = pd.read_csv(SETTINGS.paths.processed / "faers_scored.csv.gz")
    df = screened_pairs(scored)
    y = df["labelled"].astype(int).to_numpy()
    out: dict = {
        "pairs": int(len(df)),
        "labelled_share": round(float(y.mean()), 3),
        "drugs": sorted(df["drug"].unique().tolist()),
        "measures": {},
        "rules": {},
        "by_dataset": {},
    }
    rng = np.random.default_rng(0)
    out["measures"]["Random"] = {"auroc": 0.5, "average_precision": round(float(y.mean()), 3)}
    for name, col in MEASURES.items():
        s = df[col].to_numpy(np.float64)
        out["measures"][name] = {"auroc": round(float(roc_auc_score(y, s)), 3), "average_precision": round(float(average_precision_score(y, s)), 3)}
    for name, col in RULES.items():
        flag = df[col].astype(bool).to_numpy()
        tp = int((flag & (y == 1)).sum())
        out["rules"][name] = {
            "flagged": int(flag.sum()),
            "precision": round(tp / max(int(flag.sum()), 1), 3),
            "recall": round(tp / max(int(y.sum()), 1), 3),
        }
    for ds, part in df.groupby("dataset"):
        yy = part["labelled"].astype(int).to_numpy()
        if yy.min() == yy.max():
            continue
        out["by_dataset"][ds] = {
            "pairs": int(len(part)),
            "labelled_share": round(float(yy.mean()), 3),
            **{f"auroc_{k}": round(float(roc_auc_score(yy, part[v])), 3) for k, v in (("EB05", "eb05"), ("ROR", "ror_lo"), ("count", "a"))},
        }
    # Stratify by how commonly the preferred term is reported across the whole
    # database: labels list very common, non specific symptoms that
    # disproportionality is designed not to flag.
    df["pt_total"] = df["a"] + df["c"]
    df["pt_pct"] = df.groupby("dataset")["pt_total"].rank(pct=True)
    strata = {}
    for name, mask in (
        ("most frequently reported 20% of terms", df["pt_pct"] > 0.8),
        ("middle 60%", (df["pt_pct"] > 0.2) & (df["pt_pct"] <= 0.8)),
        ("least frequently reported 20%", df["pt_pct"] <= 0.2),
    ):
        part = df[mask]
        yy = part["labelled"].astype(int).to_numpy()
        if len(part) and yy.min() != yy.max():
            strata[name] = {
                "pairs": int(len(part)),
                "labelled_share": round(float(yy.mean()), 3),
                "auroc_EB05": round(float(roc_auc_score(yy, part["eb05"])), 3),
                "auroc_count": round(float(roc_auc_score(yy, part["a"])), 3),
                "eb05_rule_precision": round(float(part.loc[part["eb_signal"], "labelled"].mean()), 3) if part["eb_signal"].any() else None,
            }
    out["by_term_frequency"] = strata
    if "cluster_flag" in df.columns:
        clean = df[~df["cluster_flag"].astype(bool)]
        yy = clean["labelled"].astype(int).to_numpy()
        out["without_report_clusters"] = {
            "pairs_removed": int(df["cluster_flag"].astype(bool).sum()),
            "auroc_EB05": round(float(roc_auc_score(yy, clean["eb05"])), 3),
            "eb05_rule_precision": round(float(clean.loc[clean["eb_signal"], "labelled"].mean()), 3),
            "eb05_rule_flagged": int(clean["eb_signal"].sum()),
        }
    # Top unlabelled signals (candidate new signals for review)
    cand = df[(~df["labelled"]) & (df["eb_signal"]) & (~df.get("cluster_flag", pd.Series(False, index=df.index)).astype(bool))].sort_values("eb05", ascending=False)
    out["top_unlabelled"] = [
        {"drug": r.drug, "pt": r.pt, "cases": int(r.a), "eb05": round(float(r.eb05), 2), "ror": round(float(r.ror), 2), "soc": r.soc} for r in cand.head(25).itertuples()
    ]
    out["reference_set_checks"] = reference_checks(scored)
    (SETTINGS.paths.reports / "signal_evaluation.json").write_text(json.dumps(out, indent=2))
    return out


def reference_checks(scored: pd.DataFrame) -> list[dict]:
    from vigilix.data.sources import load_reference_sets

    ref = load_reference_sets()
    rows = []
    s = scored.copy()
    s["pt_l"] = s["pt"].str.lower()
    for r in ref.itertuples():
        drug = r.drug.replace("\\", " ")
        part = s[s["drug"] == drug]
        if part.empty:
            continue
        pts = OUTCOME_PTS.get(r.outcome, [r.outcome.lower()])
        hit = part[part["pt_l"].isin(pts)]
        best = hit.sort_values("eb05", ascending=False).head(1)
        rows.append(
            {
                "reference_set": r.reference_set,
                "drug": drug,
                "outcome": r.outcome,
                "ground_truth": "positive control" if r.positive else "negative control",
                "matched_pt": best["pt"].iloc[0] if len(best) else None,
                "cases": int(best["a"].iloc[0]) if len(best) else 0,
                "eb05": round(float(best["eb05"].iloc[0]), 2) if len(best) else None,
                "signal": bool(best["eb_signal"].iloc[0]) if len(best) else False,
                "agrees": (bool(best["eb_signal"].iloc[0]) if len(best) else False) == bool(r.positive),
            }
        )
    return rows


if __name__ == "__main__":
    res = evaluate()
    print(json.dumps({k: v for k, v in res.items() if k not in ("drugs", "top_unlabelled")}, indent=2))
