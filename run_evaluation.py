"""Run every evaluation and regenerate reports/ and reports/figures/.

    python scripts/run_evaluation.py           development questions only
    python scripts/run_evaluation.py --blind   also score the blind set (do this once, after freezing)
"""
import argparse
import hashlib
import json
from pathlib import Path

from vigilix.config import SETTINGS
from vigilix.eval import answer_eval, figures, retrieval_eval, signal_eval
from vigilix.extraction.labels import evaluate_labels
from vigilix.rag.pipeline import Pipeline

MODES = ("bm25", "sif", "dense", "hybrid", "entity", "full")


def strip(r: dict) -> dict:
    return {k: v for k, v in r.items() if k != "per_question"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blind", action="store_true")
    args = ap.parse_args()
    rep = SETTINGS.paths.reports
    pipe = Pipeline()
    pipe.retriever.sif_matrix = __import__("numpy").load(SETTINGS.paths.artifacts / "sif_passages.npy").astype("float32")
    results: dict = {"retrieval": {}}
    sets = ["dev"] + (["blind"] if args.blind else [])
    if args.blind:
        blind_path = Path(retrieval_eval.QDIR) / "blind.json"
        digest = hashlib.sha256(blind_path.read_bytes()).hexdigest()
        recorded = (rep / "blind_hash.txt").read_text().split()[0]
        results["blind_hash_matches"] = digest == recorded
        print("blind set hash matches the frozen record:", digest == recorded)
    for s in sets:
        qs = retrieval_eval.load_questions(s)
        results["retrieval"][s] = {}
        for m in MODES:
            r = retrieval_eval.evaluate(pipe.retriever, qs, m)
            results["retrieval"][s][m] = strip(r)
            if m == "full":
                (rep / f"retrieval_{s}_per_question.json").write_text(json.dumps(r["per_question"], indent=2))
            print(f"  {s:5s} {m:7s} R@5 {r['recall_at_5']:.3f}  strict {r['strict_recall_at_5']:.3f}  MRR {r['mrr_at_10']:.3f}  nDCG {r['ndcg_at_10']:.3f}  {r['ms_per_query']} ms")
    ans = answer_eval.evaluate(pipe, tuple(sets))
    (rep / "answer_eval.json").write_text(json.dumps(ans, indent=2))
    results["answers"] = strip(ans)
    print("answers:", json.dumps(strip(ans))[:600])
    results["signals"] = signal_eval.evaluate()
    results["labels"] = evaluate_labels(verbose=False)
    results["ade"] = json.loads((rep / "ade_extraction.json").read_text())
    results["verifier"] = json.loads((SETTINGS.paths.artifacts / "verifier.json").read_text())["evaluation"]
    results["reranker"] = json.loads((SETTINGS.paths.artifacts / "reranker_info.json").read_text())
    results["index"] = json.loads((SETTINGS.paths.artifacts / "index_stats.json").read_text())
    results["kb"] = json.loads((SETTINGS.paths.processed / "build_stats.json").read_text())
    (rep / "evaluation_summary.json").write_text(json.dumps(results, indent=2))
    figures.write_all(results)
    print("reports written to", rep)


if __name__ == "__main__":
    main()
