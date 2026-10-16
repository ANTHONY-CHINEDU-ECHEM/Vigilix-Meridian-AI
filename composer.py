"""Evidence item construction, graph evidence text and the extractive composer."""
from __future__ import annotations

import re

from vigilix.rag.text import analyse, numbers, sentences

LEVEL_PRIOR = {1: 1.0, 2: 0.8, 3: 0.65, 4: 0.45}
_SECTION_LABEL = re.compile(r"^(?:BACKGROUND|OBJECTIVES?|METHODS?|RESULTS?|CONCLUSIONS?|DISCUSSION|CASE (?:SUMMARY|SUMMARIES|REPORT|PRESENTATION)|PURPOSE|AIMS?|INTRODUCTION|SETTING|DESIGN|PATIENTS?|INTERVENTIONS?|EXCERPT)\s*:\s*")
_TABLE = re.compile(r"(\|.*){3,}|\b\d+(\.\d+)?\s+\d+(\.\d+)?\s+\d+(\.\d+)?\s+\d+(\.\d+)?\b")


def graph_evidence_text(summary: dict, graph) -> str | None:
    """Turn graph evidence into a short, data derived paragraph (cited as its own item)."""
    parts: list[str] = []
    for p in summary.get("pairs", []):
        rel = p["relations"]
        d, r = p["drug"], p["reaction"]
        if not rel:
            parts.append(f"The knowledge graph holds no labelled reaction, FAERS signal, case report or literature link between {d} and {r}.")
            continue
        bits = []
        if "labelled_reaction" in rel:
            srcs = ", ".join(rel["labelled_reaction"]["sources"][:4])
            bits.append(f"{r} is a labelled reaction of {d} ({srcs})")
        if "faers_signal" in rel:
            f = rel["faers_signal"]
            bits.append(
                f"FAERS shows disproportionate reporting of {r} with {d} in the {f.get('dataset', '').replace('_', ' ')} dataset "
                f"({f.get('cases')} drug and event pairs, EBGM {f.get('ebgm')}, EB05 {f.get('eb05')}, ROR {f.get('ror')})"
            )
        if "case_reported" in rel:
            c = rel["case_reported"]
            n = len(c.get("pmids", [])) or c["evidence"]
            bits.append(f"{n} annotated case report{'s' if n != 1 else ''} in the ADE corpus describe {r} with {d}")
        if "literature_induced" in rel:
            n = len(rel["literature_induced"].get("pmids", [])) or 1
            bits.append(f"{n} abstract{'s' if n != 1 else ''} in the BioCreative V CDR corpus annotate {r} as induced by {d}")
        sentence = "; ".join(bits)
        parts.append(sentence[0].upper() + sentence[1:] + ".")
    for it in summary.get("interactions", []):
        a, b = it["drugs"]
        bits = []
        if it["documented"]:
            types = sorted({t for d in it["documented"] for t in d.get("types", []) if t})
            srcs = sorted({s for d in it["documented"] for s in d["sources"]})
            bits.append(f"an interaction between {a} and {b} is annotated in {', '.join(srcs)}" + (f" (types: {', '.join(types)})" if types else ""))
        for g in it["shared_risk_groups"][:3]:
            bits.append(f"both drugs list reactions in the {g['group'].lower()} risk group ({a}: {', '.join(g[a][:2])}; {b}: {', '.join(g[b][:2])})")
        if it["shared_classes"]:
            bits.append(f"both belong to {', '.join(it['shared_classes'][:2])}")
        if bits:
            parts.append(("For " + a + " with " + b + ", " + "; ".join(bits)) + ".")
        else:
            parts.append(f"The knowledge graph has no documented interaction or shared pharmacodynamic risk group for {a} with {b}.")
    if not parts:
        return None
    return " ".join(parts)


def _sentence_candidates(items: list[dict]) -> list[dict]:
    out = []
    for it in items:
        if it["source_type"] == "graph":
            continue
        for s in sentences(it["text"]):
            s = _SECTION_LABEL.sub("", s).strip()
            words = len(s.split())
            if words < 7 or words > 70 or _TABLE.search(s) or s.count("[see") > 0:
                continue
            out.append({"text": s, "item": it})
    return out


def _section_prior(it: dict, s: str) -> float:
    st = it["source_type"]
    sec = (it.get("section") or "").lower()
    if st == "trial_abstract":
        return 1.0 if ("result" in sec or "conclusion" in sec) else 0.5
    if st == "drug_label":
        return 1.0 if ("warning" in sec or "boxed" in sec or "undesirable" in sec) else 0.8
    return 0.8


def compose(question_tokens: list[str], qinfo, items: list[dict], max_sentences: int = 5) -> list[dict]:
    """Select verbatim evidence sentences, each cited to its item."""
    qset = set(question_tokens)
    chosen: list[dict] = []
    graph_item = next((it for it in items if it["source_type"] == "graph"), None)
    if graph_item is not None:
        first = sentences(graph_item["text"])[0]
        chosen.append({"text": first, "citations": [graph_item["n"]], "kind": "graph"})
    scored = []
    for cand in _sentence_candidates(items):
        it = cand["item"]
        s = cand["text"]
        toks = set(analyse(s))
        if not toks:
            continue
        cov = len(qset & toks) / max(len(qset), 1)
        s_l = s.lower()
        ent = 0.0
        if qinfo.drugs:
            ent += 0.5 * any(d in s_l for d in qinfo.drugs)
        if qinfo.reactions:
            ent += 0.5 * any(r in s_l for r in qinfo.reactions)
        prior = LEVEL_PRIOR.get(it["evidence_level"], 0.4)
        rank_prior = 1.0 / (it["n"] ** 0.5)
        score = 0.42 * cov + 0.22 * ent + 0.14 * prior + 0.12 * rank_prior + 0.10 * _section_prior(it, s)
        if numbers(s) and ("frequen" in " ".join(question_tokens) or "common" in qset or "how" in qset):
            score += 0.03
        scored.append((score, s, it, toks))
    scored.sort(key=lambda x: -x[0])
    used_tokens: list[set[str]] = []
    per_item: dict[int, int] = {}
    for score, s, it, toks in scored:
        if len(chosen) >= max_sentences:
            break
        if any(len(toks & u) / max(len(toks | u), 1) > 0.5 for u in used_tokens):
            continue
        if per_item.get(it["n"], 0) >= 2:
            continue
        per_item[it["n"]] = per_item.get(it["n"], 0) + 1
        used_tokens.append(toks)
        chosen.append({"text": s, "citations": [it["n"]], "kind": "extract", "score": round(score, 3)})
    # order: graph summary, then by evidence strength, then rank
    head = [c for c in chosen if c["kind"] == "graph"]
    rest = [c for c in chosen if c["kind"] != "graph"]
    level = {it["n"]: it["evidence_level"] for it in items}
    rest.sort(key=lambda c: (level.get(c["citations"][0], 4), c["citations"][0]))
    return head + rest
