"""Retrieval evaluation against the authored clinical question sets."""
from __future__ import annotations

import json
import math
import time
from pathlib import Path

import numpy as np

from vigilix.rag.text import apply_spelling, raw_tokens

QDIR = Path(__file__).resolve().parent / "questions"


def load_questions(name: str) -> list[dict]:
    return json.loads((QDIR / f"{name}.json").read_text())["questions"]


def _norm(text: str) -> str:
    return " ".join(apply_spelling(t) for t in raw_tokens(text))


def grade(question: dict, passage: dict) -> int:
    """Graded relevance of one passage for one question (0, 1 or 2)."""
    for prefix in question.get("docs", []):
        if passage["doc_id"].startswith(prefix):
            return 2
    sources = question.get("sources")
    if sources and passage["source_type"] not in sources:
        return 0
    text = _norm(passage["title"] + " " + passage["text"])
    for drug, terms in question.get("pairs", []):
        in_drug = drug in passage.get("drugs", []) or _norm(drug) in text
        if in_drug and any(_norm(t) in text for t in terms):
            return 1
    for group in question.get("terms", []):
        if all(_norm(t) in text for t in group):
            return 1
    return 0


def metrics_for(question: dict, passages: list[dict], k_recall: int = 5, k_rank: int = 10) -> dict:
    grades = [grade(question, p) for p in passages[:k_rank]]
    first = next((i for i, g in enumerate(grades) if g > 0), None)
    dcg = sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(grades))
    ideal = sorted(grades, reverse=True)
    # ideal assumes at least one grade 2 document exists for questions that name docs
    if question.get("docs") and 2 not in ideal:
        ideal = [2] + ideal[:-1]
    idcg = sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(sorted(ideal, reverse=True))) or 1.0
    return {
        "recall": float(any(g > 0 for g in grades[:k_recall])),
        "mrr": 1.0 / (first + 1) if first is not None else 0.0,
        "ndcg": dcg / idcg,
        "strict_recall": float(any(g == 2 for g in grades[:k_recall])) if question.get("docs") else float(any(g > 0 for g in grades[:k_recall])),
    }


def evaluate(retriever, questions: list[dict], mode: str = "full", k: int = 10) -> dict:
    rows = []
    t0 = time.time()
    for q in questions:
        _, res = retriever.search(q["question"], k=k, mode=mode)
        passages = [retriever.store[c.idx] for c in res]
        m = metrics_for(q, passages)
        m["id"] = q["id"]
        m["top"] = [p["doc_id"] for p in passages[:5]]
        rows.append(m)
    n = max(len(rows), 1)
    return {
        "mode": mode,
        "n": len(rows),
        "recall_at_5": round(sum(r["recall"] for r in rows) / n, 3),
        "strict_recall_at_5": round(sum(r["strict_recall"] for r in rows) / n, 3),
        "mrr_at_10": round(sum(r["mrr"] for r in rows) / n, 3),
        "ndcg_at_10": round(sum(r["ndcg"] for r in rows) / n, 3),
        "ms_per_query": round(1000 * (time.time() - t0) / n, 1),
        "per_question": rows,
    }
