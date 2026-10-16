"""Static report figures (PNG) for the README and the governance page.

Colours follow a validated categorical order (blue, orange, aqua, yellow)
on a near white surface, with thin marks, a recessive grid and one axis per
chart.
"""
from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from vigilix.config import SETTINGS  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e4e3df"
S1, S2, S3, S4 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
MUTED = "#b5b3ad"


def _style():
    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "axes.edgecolor": GRID,
            "axes.labelcolor": INK2,
            "axes.titlecolor": INK,
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.color": GRID,
            "grid.linewidth": 0.8,
            "xtick.color": INK2,
            "ytick.color": INK2,
            "font.size": 10,
            "legend.frameon": False,
            "savefig.dpi": 150,
            "savefig.bbox": "tight",
        }
    )


def _save(fig, name: str) -> None:
    SETTINGS.paths.figures.mkdir(parents=True, exist_ok=True)
    fig.savefig(SETTINGS.paths.figures / name)
    plt.close(fig)


def retrieval_ablation(results: dict) -> None:
    """Grouped horizontal bars: MRR@10 by retriever for development and blind sets."""
    _style()
    modes = [m for m in ("bm25", "sif", "dense", "hybrid", "entity", "full") if m in results.get("dev", {})]
    names = {
        "bm25": "BM25",
        "sif": "SIF word vectors",
        "dense": "Dual encoder",
        "hybrid": "Hybrid fusion",
        "entity": "Fusion with entity routing",
        "full": "Full pipeline with reranker",
    }
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    y = np.arange(len(modes))
    h = 0.36
    dev = [results["dev"][m]["mrr_at_10"] for m in modes]
    ax.barh(y - h / 2, dev, height=h, color=S1, label="Development questions (60)", edgecolor=SURFACE, linewidth=2)
    if "blind" in results:
        blind = [results["blind"][m]["mrr_at_10"] for m in modes]
        ax.barh(y + h / 2, blind, height=h, color=S2, label="Blind questions (30)", edgecolor=SURFACE, linewidth=2)
        for yi, v in zip(y, blind):
            ax.text(v + 0.01, yi + h / 2, f"{v:.2f}", va="center", color=INK2, fontsize=8)
    for yi, v in zip(y, dev):
        ax.text(v + 0.01, yi - h / 2, f"{v:.2f}", va="center", color=INK2, fontsize=8)
    ax.set_yticks(y, [names[m] for m in modes])
    ax.invert_yaxis()
    ax.set_xlim(0, 1.08)
    ax.set_xlabel("Mean reciprocal rank at 10")
    ax.grid(axis="y", visible=False)
    ax.set_title("Retrieval ablation")
    ax.legend(loc="upper center", bbox_to_anchor=(0.45, -0.18), ncol=2, fontsize=8)
    _save(fig, "retrieval_ablation.png")


def dense_training(history: list[dict]) -> None:
    _style()
    fig, ax = plt.subplots(figsize=(6, 3.2))
    ep = [h["epoch"] for h in history]
    ax.plot(ep, [h["val_mrr"] for h in history], color=S1, lw=2, marker="o", ms=5, label="Validation MRR (in batch, 2,000 candidates)")
    ax.plot(ep, [h["val_r1"] for h in history], color=S2, lw=2, marker="o", ms=5, label="Validation recall at 1")
    ax.set_xlabel("Epoch")
    ax.set_ylim(0.4, 0.9)
    ax.set_title("Dual encoder training")
    ax.legend(fontsize=8, loc="lower right")
    _save(fig, "dense_training.png")


def reranker_importance(info: dict, top: int = 14) -> None:
    _style()
    imp = info["feature_importance"][:top][::-1]
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    ax.barh([k for k, _ in imp], [v for _, v in imp], color=S1, height=0.6, edgecolor=SURFACE, linewidth=2)
    ax.set_xlabel("Share of total split gain")
    ax.grid(axis="y", visible=False)
    ax.set_title("LambdaMART reranker: most used features")
    _save(fig, "reranker_importance.png")


def verifier_perturbations(ver: dict) -> None:
    _style()
    per = ver["evaluation"]["per_perturbation"]
    order = ["verbatim", "paraphrase", "number_change", "drug_swap", "reaction_swap", "negation_flip", "wrong_citation"]
    labels = {
        "verbatim": "Verbatim (should pass)",
        "paraphrase": "Paraphrase (should pass)",
        "number_change": "Changed number",
        "drug_swap": "Swapped drug",
        "reaction_swap": "Swapped reaction",
        "negation_flip": "Flipped negation",
        "wrong_citation": "Wrong citation",
    }
    ks = [k for k in order if k in per]
    vals = [per[k]["accuracy"] for k in ks]
    colors = [S3 if k in ("verbatim", "paraphrase") else S1 for k in ks]
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    ax.barh([labels[k] for k in ks][::-1], vals[::-1], color=colors[::-1], height=0.6, edgecolor=SURFACE, linewidth=2)
    for i, v in enumerate(vals[::-1]):
        ax.text(v - 0.01, i, f"{v:.3f}", va="center", ha="right", color="white", fontsize=8, fontweight="bold")
    ax.set_xlim(0, 1.0)
    ax.set_xlabel("Accuracy on held out examples")
    ax.grid(axis="y", visible=False)
    ax.set_title("Claim verifier by perturbation type")
    _save(fig, "verifier_perturbations.png")


def signal_auroc(sig: dict) -> None:
    _style()
    names = ["Report count", "PRR", "ROR lower 95%", "IC025", "EB05"]
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    vals = [sig["measures"][n]["auroc"] for n in names]
    ax.barh(names[::-1], vals[::-1], color=S1, height=0.6, edgecolor=SURFACE, linewidth=2)
    ax.axvline(0.5, color=INK2, lw=1, ls="--")
    ax.text(0.505, len(names) - 0.6, "chance", color=INK2, fontsize=8)
    for i, v in enumerate(vals[::-1]):
        ax.text(v + 0.005, i, f"{v:.3f}", va="center", color=INK2, fontsize=8)
    ax.set_xlim(0.45, 0.75)
    ax.set_xlabel("AUROC against label derived reference")
    ax.grid(axis="y", visible=False)
    ax.set_title(f"Ranking labelled reactions ({sig['pairs']:,} drug and term pairs)")
    _save(fig, "signal_auroc.png")


def signal_volcano(scored: pd.DataFrame, drug: str = "atorvastatin") -> None:
    """ROR against case count for one drug, labelled reactions highlighted."""
    _style()
    part = scored[(scored["drug"] == drug) & (scored["a"] > 0)].copy()
    if part.empty:
        return
    fig, ax = plt.subplots(figsize=(6.6, 4.0))
    sig = part[part["eb_signal"]]
    non = part[~part["eb_signal"]]
    ax.scatter(non["a"], non["ror"], s=22, color=MUTED, edgecolor=SURFACE, linewidth=1.5, label="Below EB05 threshold", zorder=2)
    ax.scatter(sig["a"], sig["ror"], s=36, color=S2, edgecolor=SURFACE, linewidth=1.5, label="EB05 at least 2", zorder=3)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.axhline(1, color=INK2, lw=1, ls="--")
    # Label the strongest signals, dropping any label whose box would collide
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    boxes = []
    shown = 0
    for r in sig.sort_values("eb05", ascending=False).head(14).itertuples():
        right = np.log10(r.a) > np.log10(part["a"].max()) - 1.0
        t = ax.annotate(r.pt, (r.a, r.ror), textcoords="offset points", xytext=(-6 if right else 6, 4), ha="right" if right else "left", fontsize=8, color=INK)
        bb = t.get_window_extent(renderer).expanded(1.05, 1.25)
        if any(bb.overlaps(o) for o in boxes):
            t.remove()
            continue
        boxes.append(bb)
        shown += 1
        if shown >= 6:
            break
    ax.set_xlabel("Drug and event pairs (log scale)")
    ax.set_ylabel("Reporting odds ratio (log scale)")
    ax.set_title(f"{drug.title()} in FAERS: signal screen")
    ax.legend(fontsize=8, loc="lower right")
    _save(fig, f"signal_screen_{drug.replace(' ', '_')}.png")


def extraction_scores(ade: dict) -> None:
    _style()
    rows = [
        ("Drug spans", ade["drug_spans_dictionary"]["f1"], ade["drug_spans_crf"]["f1"]),
        ("Adverse effect spans", ade["effect_spans_dictionary"]["f1"], ade["effect_spans_crf"]["f1"]),
        ("Drug and effect relations", ade["relations_end_to_end_dictionary"]["f1"], ade["relations_end_to_end_crf"]["f1"]),
    ]
    fig, ax = plt.subplots(figsize=(6.4, 3.0))
    y = np.arange(len(rows))
    h = 0.36
    ax.barh(y - h / 2, [r[1] for r in rows], height=h, color=MUTED, label="Dictionary baseline", edgecolor=SURFACE, linewidth=2)
    ax.barh(y + h / 2, [r[2] for r in rows], height=h, color=S1, label="Trained CRF and relation model", edgecolor=SURFACE, linewidth=2)
    for yi, r in zip(y, rows):
        ax.text(r[1] + 0.01, yi - h / 2, f"{r[1]:.2f}", va="center", fontsize=8, color=INK2)
        ax.text(r[2] + 0.01, yi + h / 2, f"{r[2]:.2f}", va="center", fontsize=8, color=INK2)
    ax.set_yticks(y, [r[0] for r in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xlabel("F1, exact span match, held out case reports")
    ax.grid(axis="y", visible=False)
    ax.legend(fontsize=8, loc="lower right")
    ax.set_title("Adverse event extraction from case narratives")
    _save(fig, "extraction_f1.png")


def kb_composition(stats: dict) -> None:
    _style()
    names = {
        "trial_abstract": "Randomised trial abstracts",
        "kg_fact": "Curated graph facts",
        "drug_label": "Drug label sections",
        "case_report": "Case reports",
        "cid_abstract": "Chemical induced disease abstracts",
        "interaction_monograph": "Interaction monographs",
        "interaction_abstract": "Interaction abstracts",
        "signal_summary": "FAERS signal summaries",
        "guidance_card": "Guidance digests",
    }
    items = sorted(stats["passages_by_source"].items(), key=lambda kv: kv[1])
    fig, ax = plt.subplots(figsize=(6.6, 3.6))
    ax.barh([names.get(k, k) for k, _ in items], [v for _, v in items], color=S1, height=0.6, edgecolor=SURFACE, linewidth=2)
    ax.set_xscale("log")
    for i, (_, v) in enumerate(items):
        ax.text(v * 1.08, i, f"{v:,}", va="center", fontsize=8, color=INK2)
    ax.set_xlabel("Passages (log scale)")
    ax.grid(axis="y", visible=False)
    ax.set_title(f"Knowledge base: {stats['passages']:,} passages from {stats['documents']:,} documents")
    _save(fig, "kb_composition.png")


def label_mining(lm: dict) -> None:
    _style()
    groups = ["US | Adverse reactions", "US | Warnings and precautions", "US | Boxed warning", "UK", "EU", "US paediatric"]
    g = [x for x in groups if x in lm["by_group"]]
    p = [lm["by_group"][x]["precision"] for x in g]
    r = [lm["by_group"][x]["recall"] for x in g]
    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    y = np.arange(len(g))
    h = 0.36
    ax.barh(y - h / 2, p, height=h, color=S1, label="Precision", edgecolor=SURFACE, linewidth=2)
    ax.barh(y + h / 2, r, height=h, color=S3, label="Recall", edgecolor=SURFACE, linewidth=2)
    ax.set_yticks(y, [x.replace(" | ", ": ") for x in g])
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.grid(axis="y", visible=False)
    ax.legend(fontsize=8, loc="lower right")
    ax.set_xlabel("Against manually annotated adverse events")
    ax.set_title("Mining adverse events from label sections")
    _save(fig, "label_mining.png")


def write_all(results: dict) -> None:
    art = SETTINGS.paths.artifacts
    if "retrieval" in results:
        retrieval_ablation(results["retrieval"])
    idx = json.loads((art / "index_stats.json").read_text())
    dense_training(idx["dual_encoder_history"])
    reranker_importance(json.loads((art / "reranker_info.json").read_text()))
    verifier_perturbations(json.loads((art / "verifier.json").read_text()))
    if "signals" in results:
        signal_auroc(results["signals"])
    scored = pd.read_csv(SETTINGS.paths.processed / "faers_scored.csv.gz")
    for d in ("atorvastatin", "nirmatrelvir ritonavir", "clonazepam"):
        signal_volcano(scored, d)
    if "ade" in results:
        extraction_scores(results["ade"])
    kb_composition(json.loads((SETTINGS.paths.processed / "build_stats.json").read_text()))
    if "labels" in results:
        label_mining(results["labels"])
