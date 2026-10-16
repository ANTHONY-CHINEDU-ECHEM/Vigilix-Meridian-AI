"""Pharmacovigilance knowledge graph: loading, lookups and evidence summaries.

Edges carry their provenance so every statement the interface makes about
the graph can be traced: ``labelled_reaction`` (SIDER 4.1 and annotated
labels), ``case_reported`` (ADE corpus), ``literature_induced`` (BioCreative
CDR), ``faers_signal`` (disproportionality with EBGM and EB05),
``interacts`` (DDI corpus), ``in_class`` (WHO ATC and DrugCentral),
``treats`` (PharmacotherapyDB) and ``targets`` (DrugBank).
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

from vigilix.config import SETTINGS

# Pharmacodynamic risk groups used to explain additive interactions
PD_GROUPS = {
    "QT prolongation": ("qt prolongation", "electrocardiogram qt prolonged", "electrocardiogram qt corrected interval prolonged", "torsade de pointes", "long qt syndrome"),
    "Bleeding": ("gastrointestinal hemorrhage", "intracranial hemorrhage", "cerebral hemorrhage", "hemorrhage", "bleeding", "melena", "hematemesis"),
    "Serotonin toxicity": ("serotonin syndrome",),
    "CNS and respiratory depression": ("respiratory depression", "coma", "depressed level of consciousness", "respiratory arrest"),
    "Hyperkalaemia": ("hyperkalemia", "blood potassium increased"),
    "Hyponatraemia": ("hyponatremia", "syndrome of inappropriate antidiuretic hormone", "inappropriate antidiuretic hormone secretion"),
    "Nephrotoxicity": ("acute kidney injury", "renal failure acute", "nephrotoxicity", "acute renal failure"),
    "Hepatotoxicity": ("hepatic failure", "hepatitis", "drug induced liver injury", "liver injury", "hepatotoxicity", "hepatic necrosis"),
    "Myelosuppression": ("agranulocytosis", "pancytopenia", "bone marrow failure", "aplastic anemia", "bone marrow depression"),
    "Hypotension": ("hypotension", "orthostatic hypotension"),
    "Bradycardia": ("bradycardia", "atrioventricular block", "atrioventricular block complete", "sinus arrest"),
    "Hypoglycaemia": ("hypoglycemia",),
    "Seizure threshold": ("seizure", "convulsion", "grand mal convulsion"),
    "Anticholinergic effects": ("urinary retention", "paralytic ileus", "ileus"),
    "Myopathy": ("rhabdomyolysis", "myopathy"),
}

REL_LABEL = {
    "labelled_reaction": "Listed in labels",
    "case_reported": "Case reports",
    "literature_induced": "Literature (chemical induced disease)",
    "faers_signal": "FAERS disproportionality",
    "interacts": "Documented interaction",
    "in_class": "Class",
    "treats": "Indication",
    "targets": "Target",
}


class KnowledgeGraph:
    def __init__(self, data: dict):
        self.nodes = {n["id"]: n for n in data["nodes"]}
        self.edges = data["edges"]
        self.out: dict[str, list[dict]] = defaultdict(list)
        self.inc: dict[str, list[dict]] = defaultdict(list)
        self.pair: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for e in self.edges:
            self.out[e["src"]].append(e)
            self.inc[e["dst"]].append(e)
            self.pair[(e["src"], e["dst"])].append(e)
            if e["rel"] == "interacts":
                self.pair[(e["dst"], e["src"])].append(e)

    @classmethod
    @lru_cache(maxsize=1)
    def load(cls, path: str | None = None) -> "KnowledgeGraph":
        p = Path(path) if path else SETTINGS.paths.processed / "kg.json"
        return cls(json.loads(p.read_text()))

    def stats(self) -> dict:
        return {"nodes": len(self.nodes), "edges": len(self.edges), "by_relation": dict(Counter(e["rel"] for e in self.edges)), "by_kind": dict(Counter(n["kind"] for n in self.nodes.values()))}

    # ------------------------------------------------------------------
    def reactions_of(self, drug: str, rel: str | None = None) -> list[dict]:
        out = []
        for e in self.out.get(f"drug:{drug}", []):
            if e["dst"].startswith("reaction:") and (rel is None or e["rel"] == rel):
                out.append(e)
        return out

    def pair_evidence(self, drug: str, reaction: str) -> dict:
        edges = self.pair.get((f"drug:{drug}", f"reaction:{reaction}"), [])
        ev = {"drug": drug, "reaction": reaction, "found": bool(edges), "relations": {}}
        for e in edges:
            item = {"sources": e["sources"], "evidence": e["evidence"]}
            for k in ("ebgm", "eb05", "ror", "cases", "dataset", "labelled", "pmids", "section"):
                if k in e:
                    item[k] = e[k]
            ev["relations"][e["rel"]] = item
        return ev

    def interaction(self, a: str, b: str) -> dict:
        na, nb = f"drug:{a}", f"drug:{b}"
        direct = [e for e in self.pair.get((na, nb), []) if e["rel"] == "interacts"]
        ra = {e["dst"].split(":", 1)[1] for e in self.reactions_of(a, "labelled_reaction")}
        rb = {e["dst"].split(":", 1)[1] for e in self.reactions_of(b, "labelled_reaction")}
        shared_groups = []
        for group, terms in PD_GROUPS.items():
            ha = sorted(ra.intersection(terms))
            hb = sorted(rb.intersection(terms))
            if ha and hb:
                shared_groups.append({"group": group, a: ha[:4], b: hb[:4]})
        ca = {e["dst"] for e in self.out.get(na, []) if e["rel"] == "in_class"}
        cb = {e["dst"] for e in self.out.get(nb, []) if e["rel"] == "in_class"}
        shared_classes = [self.nodes[c]["name"] for c in sorted(ca & cb)]
        return {
            "drugs": [a, b],
            "documented": [{"sources": e["sources"], "types": e.get("types", []), "evidence": e["evidence"], "docs": e.get("docs", [])} for e in direct],
            "shared_risk_groups": shared_groups,
            "shared_classes": shared_classes,
            "known": {a: f"drug:{a}" in self.nodes, b: f"drug:{b}" in self.nodes},
        }

    def drug_profile(self, drug: str, top: int = 25) -> dict:
        nid = f"drug:{drug}"
        node = self.nodes.get(nid)
        if node is None:
            return {"drug": drug, "found": False}
        by_rel: dict[str, list[dict]] = defaultdict(list)
        for e in self.out.get(nid, []):
            by_rel[e["rel"]].append(e)
        for e in self.inc.get(nid, []):
            if e["rel"] == "interacts":
                by_rel["interacts"].append({**e, "src": e["dst"], "dst": e["src"]})
        soc_counts: Counter = Counter()
        for e in by_rel.get("labelled_reaction", []):
            soc_counts[self.nodes[e["dst"]].get("soc", "Unclassified")] += 1

        def name(nid2: str) -> str:
            return self.nodes.get(nid2, {}).get("name", nid2.split(":", 1)[-1])

        signals = sorted(by_rel.get("faers_signal", []), key=lambda e: -e.get("eb05", 0))
        return {
            "drug": drug,
            "found": True,
            "atc": node.get("atc"),
            "counts": {REL_LABEL.get(k, k): len(v) for k, v in by_rel.items()},
            "labelled_by_soc": dict(soc_counts.most_common()),
            "faers_signals": [
                {"reaction": name(e["dst"]), "eb05": e.get("eb05"), "ebgm": e.get("ebgm"), "cases": e.get("cases"), "labelled": e.get("labelled"), "dataset": e.get("dataset")} for e in signals[:top]
            ],
            "case_reported": sorted(({"reaction": name(e["dst"]), "reports": len(e.get("pmids", [])) or e["evidence"], "pmids": e.get("pmids", [])[:5]} for e in by_rel.get("case_reported", [])), key=lambda x: -x["reports"])[:top],
            "literature": sorted(({"reaction": name(e["dst"]), "pmids": e.get("pmids", [])[:5]} for e in by_rel.get("literature_induced", [])), key=lambda x: -len(x["pmids"]))[:top],
            "interactions": sorted(({"drug": name(e["dst"]), "types": e.get("types", []), "evidence": e["evidence"]} for e in by_rel.get("interacts", [])), key=lambda x: -x["evidence"])[:top],
            "classes": [name(e["dst"]) for e in by_rel.get("in_class", [])][:12],
            "indications": [name(e["dst"]) for e in by_rel.get("treats", [])][:12],
            "targets": [name(e["dst"]) for e in by_rel.get("targets", [])][:16],
        }

    def subgraph(self, drug: str, limit: int = 40) -> dict:
        """A small neighbourhood for visualisation, prioritising safety relations."""
        nid = f"drug:{drug}"
        if nid not in self.nodes:
            return {"nodes": [], "edges": []}
        priority = {"faers_signal": 0, "case_reported": 1, "interacts": 2, "literature_induced": 3, "labelled_reaction": 4, "in_class": 5, "treats": 6, "targets": 7}
        cand = list(self.out.get(nid, [])) + [e for e in self.inc.get(nid, []) if e["rel"] == "interacts"]
        cand.sort(key=lambda e: (priority.get(e["rel"], 9), -e.get("weight", 0), -e["evidence"]))
        quota = Counter()
        caps = {"faers_signal": 12, "case_reported": 8, "interacts": 8, "literature_induced": 6, "labelled_reaction": 10, "in_class": 4, "treats": 4, "targets": 4}
        keep = []
        for e in cand:
            if quota[e["rel"]] >= caps.get(e["rel"], 3):
                continue
            quota[e["rel"]] += 1
            keep.append(e)
            if len(keep) >= limit:
                break
        ids = {nid}
        for e in keep:
            ids.add(e["src"])
            ids.add(e["dst"])
        return {
            "nodes": [self.nodes[i] for i in ids if i in self.nodes],
            "edges": [{"src": e["src"], "dst": e["dst"], "rel": e["rel"], "label": REL_LABEL.get(e["rel"], e["rel"]), "weight": e.get("weight", 1.0), "sources": e["sources"]} for e in keep],
        }

    def reaction_profile(self, reaction: str, top: int = 30) -> dict:
        nid = f"reaction:{reaction}"
        if nid not in self.nodes:
            return {"reaction": reaction, "found": False}
        by_drug: dict[str, dict] = defaultdict(lambda: {"relations": set(), "eb05": None})
        for e in self.inc.get(nid, []):
            d = self.nodes[e["src"]]["name"]
            by_drug[d]["relations"].add(e["rel"])
            if e["rel"] == "faers_signal":
                by_drug[d]["eb05"] = e.get("eb05")
        rows = [{"drug": d, "relations": sorted(v["relations"]), "eb05": v["eb05"]} for d, v in by_drug.items()]
        rows.sort(key=lambda r: (-len(r["relations"]), -(r["eb05"] or 0)))
        return {"reaction": reaction, "found": True, "soc": self.nodes[nid].get("soc"), "drugs": rows[:top], "total_drugs": len(rows)}

    def evidence_summary(self, drugs: list[str], reactions: list[str]) -> dict:
        """Structured graph evidence used by the answer pipeline and as reranker features."""
        pairs = [self.pair_evidence(d, r) for d in drugs[:3] for r in reactions[:3]]
        inter = [self.interaction(drugs[i], drugs[j]) for i in range(min(3, len(drugs))) for j in range(i + 1, min(3, len(drugs)))]
        flags = {"labelled": False, "faers": False, "case": False, "literature": False, "interaction": False}
        for p in pairs:
            rel = p["relations"]
            flags["labelled"] |= "labelled_reaction" in rel
            flags["faers"] |= "faers_signal" in rel
            flags["case"] |= "case_reported" in rel
            flags["literature"] |= "literature_induced" in rel
        for it in inter:
            flags["interaction"] |= bool(it["documented"]) or bool(it["shared_risk_groups"])
        return {"pairs": pairs, "interactions": inter, "flags": flags}
