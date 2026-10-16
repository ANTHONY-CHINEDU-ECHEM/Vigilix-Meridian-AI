"""Multi drug interaction and polypharmacy risk checker.

For every pair in a medication list the checker combines three independent
lines of evidence and shows each one separately:

* documented interactions annotated in the DDI corpus (DrugBank monographs
  and MEDLINE abstracts), with the exact sentences and interaction type
  (mechanism, effect, advise, int)
* pharmacokinetic mechanisms from a curated table of CYP450, P
  glycoprotein, OATP1B1 and renal clearance perpetrators and victims
* pharmacodynamic overlap: both drugs list reactions in the same risk group
  (QT prolongation, bleeding, serotonin toxicity, CNS depression and so on)
  according to SIDER and the annotated labels

The pairwise heuristic level (major, moderate, minor, none found) is a
triage aid that ranks pairs for review; it is not a validated severity scale.
"""
from __future__ import annotations

import json
from collections import defaultdict
from functools import lru_cache
from itertools import combinations

from vigilix.config import SETTINGS
from vigilix.rag.graph import PD_GROUPS, KnowledgeGraph
from vigilix.rag.text import canonical_drug

HIGH_RISK_GROUPS = {"QT prolongation", "Bleeding", "Serotonin toxicity", "CNS and respiratory depression", "Hyperkalaemia", "Myelosuppression", "Nephrotoxicity"}


@lru_cache(maxsize=1)
def pk_table() -> dict:
    return json.loads((SETTINGS.paths.knowledge / "pk_interactions.json").read_text())["mechanisms"]


@lru_cache(maxsize=1)
def ddi_sentences() -> dict[str, list[dict]]:
    """Index of DDI corpus sentences by sorted canonical drug pair (built once, cached on disk)."""
    path = SETTINGS.paths.processed / "ddi_pairs.json"
    if path.exists():
        return json.loads(path.read_text())
    from vigilix.data.sources import load_ddi_corpus

    index: dict[str, list[dict]] = defaultdict(list)
    for doc in load_ddi_corpus():
        for s in doc["sentences"]:
            for p in s["pairs"]:
                if not p["ddi"]:
                    continue
                a, b = sorted([canonical_drug(p["e1"].lower()), canonical_drug(p["e2"].lower())])
                if a == b:
                    continue
                key = f"{a}|{b}"
                if len(index[key]) < 6 and not any(x["sentence"] == s["text"] for x in index[key]):
                    index[key].append({"sentence": s["text"], "type": p["type"] or "int", "source": doc["source"], "doc": doc["id"]})
    path.write_text(json.dumps(index))
    return dict(index)


def pk_mechanisms(a: str, b: str) -> list[dict]:
    out = []
    for mech, roles in pk_table().items():
        for x, y in ((a, b), (b, a)):
            def has(role: str, drug: str) -> bool:
                return drug in roles.get(role, [])

            victim_sens = has("sensitive_substrates", y) or has("narrow_index_substrates", y)
            narrow = has("narrow_index_substrates", y)
            if has("strong_inhibitors", x) and victim_sens:
                out.append({"mechanism": mech, "perpetrator": x, "victim": y, "effect": f"{x} is a strong {mech} inhibitor and may markedly increase exposure to {y}", "strength": 3 if not narrow else 4})
            elif (has("moderate_inhibitors", x) or has("inhibitors", x)) and victim_sens:
                out.append({"mechanism": mech, "perpetrator": x, "victim": y, "effect": f"{x} inhibits {mech} and may increase exposure to {y}", "strength": 2 if not narrow else 3})
            if (has("strong_inducers", x) or has("inducers", x)) and victim_sens:
                out.append({"mechanism": mech, "perpetrator": x, "victim": y, "effect": f"{x} induces {mech} and may reduce exposure to {y}, risking loss of effect", "strength": 3})
            elif has("moderate_inducers", x) and victim_sens:
                out.append({"mechanism": mech, "perpetrator": x, "victim": y, "effect": f"{x} is a moderate {mech} inducer and may reduce exposure to {y}", "strength": 2})
            if has("prodrugs", y) and (has("strong_inhibitors", x) or has("moderate_inhibitors", x)):
                out.append({"mechanism": mech, "perpetrator": x, "victim": y, "effect": f"{y} needs {mech} activation; {x} may reduce its active metabolite and effect", "strength": 2})
            if has("reducers", x) and has("renally_cleared_narrow_index", y):
                out.append({"mechanism": mech, "perpetrator": x, "victim": y, "effect": f"{x} can reduce renal clearance of {y}, a renally cleared drug with a narrow therapeutic index", "strength": 2})
    return out


def check_pair(a: str, b: str, graph: KnowledgeGraph) -> dict:
    a, b = canonical_drug(a), canonical_drug(b)
    g = graph.interaction(a, b)
    key = "|".join(sorted([a, b]))
    docs = ddi_sentences().get(key, [])
    pk = pk_mechanisms(a, b)
    score = 0
    reasons = []
    if docs or g["documented"]:
        types = sorted({d["type"] for d in docs} | {t for d in g["documented"] for t in d.get("types", [])})
        score += 2 if set(types) & {"mechanism", "effect", "advise"} else 1
        reasons.append("documented interaction (" + ", ".join(types or ["int"]) + ")")
    if pk:
        best = max(m["strength"] for m in pk)
        score += best
        reasons.append("pharmacokinetic mechanism (" + ", ".join(sorted({m["mechanism"] for m in pk})) + ")")
    pd_score = 0
    for grp in g["shared_risk_groups"]:
        pd_score += 2 if grp["group"] in HIGH_RISK_GROUPS else 1
    if g["shared_risk_groups"]:
        score += min(pd_score, 3)
        reasons.append("shared risk groups (" + ", ".join(x["group"] for x in g["shared_risk_groups"]) + ")")
    level = "major" if score >= 5 else "moderate" if score >= 3 else "minor" if score >= 1 else "none found"
    return {
        "drugs": [a, b],
        "level": level,
        "score": score,
        "reasons": reasons,
        "documented": docs,
        "pharmacokinetic": pk,
        "pharmacodynamic": g["shared_risk_groups"],
        "shared_classes": g["shared_classes"],
        "known": g["known"],
    }


def check_regimen(drugs: list[str], graph: KnowledgeGraph | None = None) -> dict:
    graph = graph or KnowledgeGraph.load()
    canon = []
    for d in drugs:
        c = canonical_drug(d)
        if c and c not in canon:
            canon.append(c)
    pairs = [check_pair(a, b, graph) for a, b in combinations(canon, 2)]
    order = {"major": 0, "moderate": 1, "minor": 2, "none found": 3}
    pairs.sort(key=lambda p: (order[p["level"]], -p["score"]))
    burden: dict[str, list[str]] = defaultdict(list)
    for d in canon:
        rx = {e["dst"].split(":", 1)[1] for e in graph.reactions_of(d, "labelled_reaction")}
        for group, terms in PD_GROUPS.items():
            if rx.intersection(terms):
                burden[group].append(d)
    cumulative = sorted(({"group": g, "drugs": ds, "high_risk": g in HIGH_RISK_GROUPS} for g, ds in burden.items() if len(ds) >= 2), key=lambda x: (-x["high_risk"], -len(x["drugs"])))
    return {
        "drugs": canon,
        "unknown": [d for d in canon if f"drug:{d}" not in graph.nodes],
        "pairs": pairs,
        "cumulative_burden": cumulative,
        "summary": {lvl: sum(1 for p in pairs if p["level"] == lvl) for lvl in order},
        "disclaimer": "Heuristic triage from public sources. Always confirm with a full interaction reference and the product information.",
    }
