"""Build the Vigilix Meridian knowledge base from the raw public sources.

Outputs (all under ``data/processed``):

* ``dictionaries.json``  drug and reaction dictionaries with synonyms, ATC
  codes, pharmacologic classes and System Organ Classes
* ``faers_scored.csv.gz`` and ``faers_priors.json``  every FAERS drug and
  preferred term pair with PRR, ROR, IC, EBGM and label status
* ``kg.json``  the pharmacovigilance knowledge graph
* ``passages.jsonl.gz``  the retrieval corpus, one passage per line
* ``labels.json``  structured label sections for the label workspace
* ``build_stats.json``  counts reported in the README and governance page
"""
from __future__ import annotations

import gzip
import json
import re
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from vigilix.config import SETTINGS
from vigilix.data import sources as S
from vigilix.kb.dictionaries import Dictionary, build_drug_dictionary, build_reaction_dictionary, save_dictionaries
from vigilix.rag.text import canonical_drug, canonical_term, sentences
from vigilix.signals.disproportionality import detect_report_clusters, score_all

SAFETY = re.compile(
    r"\b(adverse (event|effect|reaction|drug|outcome)s?|side[- ]effects?|toxicit(y|ies)|tolerab\w+|well tolerated|safety|"
    r"hepatotoxic\w*|nephrotoxic\w*|cardiotoxic\w*|ototoxic\w*|neurotoxic\w*|hypersensitivity|discontinu\w+ (due|because)|"
    r"serious adverse|treatment[- ]related|drug[- ]related|bleeding|ha?emorrhag\w+|hypoglyc\w+|QT\w*|withdrawals? due)\b",
    re.I,
)

EVIDENCE = {
    "guidance_card": (1, "Guidance digest"),
    "drug_label": (1, "Regulatory label"),
    "trial_abstract": (2, "Randomised trial"),
    "signal_summary": (3, "FAERS disproportionality"),
    "kg_fact": (3, "Curated database"),
    "interaction_monograph": (3, "Interaction monograph"),
    "cid_abstract": (4, "Literature, chemical induced disease"),
    "interaction_abstract": (4, "Literature, interaction"),
    "case_report": (4, "Case report"),
}

WORDS_PER_CHUNK = 170


def _chunk_sentences(sents: list[str], words: int = WORDS_PER_CHUNK, overlap: int = 1) -> list[list[int]]:
    """Greedy windows of sentence indices of about ``words`` words with overlap."""
    chunks, cur, n = [], [], 0
    for i, s in enumerate(sents):
        w = len(s.split())
        if cur and n + w > words:
            chunks.append(cur)
            cur = cur[-overlap:] if overlap else []
            n = sum(len(sents[j].split()) for j in cur)
        cur.append(i)
        n += w
    if cur and (not chunks or cur != chunks[-1][-len(cur):]):
        chunks.append(cur)
    return chunks


class Builder:
    def __init__(self, verbose: bool = True):
        self.paths = SETTINGS.paths.ensure()
        self.verbose = verbose
        self.stats: dict = {}
        self.passages: list[dict] = []
        self.t0 = time.time()

    def log(self, msg: str) -> None:
        if self.verbose:
            print(f"[{time.time() - self.t0:6.1f}s] {msg}", flush=True)

    # ------------------------------------------------------------------
    def load_sources(self) -> None:
        self.log("loading sources")
        self.het = S.load_hetionet()
        self.atc = S.load_atc()
        self.labels = S.load_labels()
        self.faers = S.load_faers_tables()
        self.reference = S.load_reference_sets()
        self.ade = S.load_ade_corpus()
        self.ddi = S.load_ddi_corpus()
        self.cdr = S.load_cdr()
        self.cards = json.loads((self.paths.knowledge / "knowledge_cards.json").read_text())

    def build_dictionaries(self) -> None:
        self.log("building dictionaries")
        self.drugs = build_drug_dictionary(self.het, self.atc, self.labels, self.faers, self.reference, self.ade["relations"], self.ddi)
        self.reactions, self.soc_table = build_reaction_dictionary(self.het, self.faers, self.labels, self.reference, self.ade["relations"])
        # UK SmPC identifiers are numeric: detect the substance from the text
        for lab in self.labels:
            if not lab["substance"]:
                linked = [c for c, _, _ in self.drugs.link(lab["text"][:6000])]
                if linked:
                    top, n = Counter(linked).most_common(1)[0]
                    if n >= 2 or len(set(linked)) == 1:
                        lab["substance"] = top
                        lab["substance_detected"] = True
        save_dictionaries(self.drugs, self.reactions, self.paths.processed / "dictionaries.json")
        self.stats["drugs"] = len(self.drugs.entries)
        self.stats["reactions"] = len(self.reactions.entries)

    # ------------------------------------------------------------------
    def build_signals(self) -> None:
        self.log("scoring FAERS tables")
        scored, priors = score_all(self.faers)
        scored["drug"] = scored["drug"].map(canonical_drug)
        scored["pt_canonical"] = scored["pt"].map(canonical_term)
        scored["soc"] = scored.apply(
            lambda r: r["soc"] if isinstance(r["soc"], str) and r["soc"] else (self.reactions.entries.get(r["pt_canonical"]).attrs.get("soc") if r["pt_canonical"] in self.reactions.entries else "Unclassified"),
            axis=1,
        )
        scored["soc"] = scored["soc"].str.replace(r"\s*\(incl.*\)$", "", regex=True)
        scored["cluster_flag"] = detect_report_clusters(scored)
        # Label status from SIDER and the annotated label sets
        listed = self.listed_reactions()
        scored["labelled"] = [pt in listed.get(d, set()) for d, pt in zip(scored["drug"], scored["pt_canonical"])]
        # A drug counts as label covered only when the references list a
        # meaningful number of its reactions (Hetionet's SIDER extract has no
        # entries for atorvastatin or warfarin, for example).
        covered = {d for d, terms in listed.items() if len(terms) >= 20}
        scored["label_known"] = scored["drug"].isin(covered)
        scored.to_csv(self.paths.processed / "faers_scored.csv.gz", index=False)
        (self.paths.processed / "faers_priors.json").write_text(json.dumps({"priors": priors, "notes": S.faers_dataset_notes()}, indent=2))
        self.scored = scored
        self.stats["faers_pairs"] = int(len(scored))
        self.stats["faers_signals_evans"] = int(scored["evans"].sum())
        self.stats["faers_signals_eb05"] = int(scored["eb_signal"].sum())

    def listed_reactions(self) -> dict[str, set[str]]:
        if hasattr(self, "_listed"):
            return self._listed
        listed: dict[str, set[str]] = defaultdict(set)
        for (s, t) in self.het["edges"].get("causes", []):
            drug = canonical_drug(self.het["nodes"][s]["name"])
            listed[drug].add(canonical_term(self.het["nodes"][t]["name"]))
        for lab in self.labels:
            if lab["substance"]:
                d = canonical_drug(lab["substance"])
                for ev in lab["events"]:
                    listed[d].add(canonical_term(ev["pt"]))
        self._listed = listed
        return listed

    # ------------------------------------------------------------------
    def build_graph(self) -> None:
        self.log("building knowledge graph")
        nodes: dict[str, dict] = {}
        edges: dict[tuple, dict] = {}

        def node(nid: str, kind: str, name: str, **attrs) -> str:
            if nid not in nodes:
                nodes[nid] = {"id": nid, "kind": kind, "name": name, **attrs}
            return nid

        def edge(src: str, dst: str, rel: str, source: str, weight: float = 1.0, **attrs) -> None:
            key = (src, dst, rel)
            e = edges.get(key)
            if e is None:
                e = edges[key] = {"src": src, "dst": dst, "rel": rel, "sources": [], "weight": 0.0, "evidence": 0}
            if source not in e["sources"]:
                e["sources"].append(source)
            e["weight"] = max(e["weight"], weight)
            e["evidence"] += 1
            for k, v in attrs.items():
                if isinstance(v, list):
                    cur = e.setdefault(k, [])
                    for x in v:
                        if x not in cur and len(cur) < 12:
                            cur.append(x)
                else:
                    e[k] = v

        def drug_node(name: str) -> str:
            c = canonical_drug(name)
            entry = self.drugs.entries.get(c)
            return node(f"drug:{c}", "drug", c, atc=(entry.attrs.get("atc", [None])[0] if entry else None))

        def reaction_node(name: str) -> str:
            c = canonical_term(name)
            entry = self.reactions.entries.get(c)
            return node(f"reaction:{c}", "reaction", c, soc=(entry.attrs.get("soc") if entry else "Unclassified"))

        het = self.het
        for (s, t) in het["edges"].get("causes", []):
            edge(drug_node(het["nodes"][s]["name"]), reaction_node(het["nodes"][t]["name"]), "labelled_reaction", "SIDER 4.1")
        for lab in self.labels:
            if not lab["substance"]:
                continue
            d = drug_node(lab["substance"])
            for ev in lab["events"]:
                edge(d, reaction_node(ev["pt"]), "labelled_reaction", f"{lab['region']} label", section=[lab["section"]])
        rel = self.ade["relations"]
        for r in rel.itertuples():
            c = canonical_drug(r.drug.lower())
            if c not in self.drugs.entries:
                continue
            edge(drug_node(c), reaction_node(r.effect), "case_reported", "ADE corpus", pmids=[r.pmid])
        for doc in self.cdr:
            for r in doc["relations"]:
                c = canonical_drug(r["chemical_name"].lower())
                if c not in self.drugs.entries:
                    hit = self.drugs.mentions(r["chemical_name"])
                    if not hit:
                        continue
                    c = hit[0]
                edge(drug_node(c), reaction_node(r["disease_name"]), "literature_induced", "BioCreative V CDR", pmids=[doc["pmid"]])
        for doc in self.ddi:
            for s in doc["sentences"]:
                for p in s["pairs"]:
                    if not p["ddi"]:
                        continue
                    a, b = canonical_drug(p["e1"].lower()), canonical_drug(p["e2"].lower())
                    if a == b:
                        continue
                    a_ok, b_ok = a in self.drugs.entries, b in self.drugs.entries
                    src_a = drug_node(a) if a_ok else node(f"group:{a}", "drug_group", a)
                    src_b = drug_node(b) if b_ok else node(f"group:{b}", "drug_group", b)
                    x, y = sorted([src_a, src_b])
                    edge(x, y, "interacts", f"DDI corpus ({doc['source']})", types=[p["type"] or "int"], docs=[doc["id"]])
        for r in self.scored.itertuples():
            if r.a >= 3 and (r.eb05 >= 1.0 or r.signal_votes >= 2):
                edge(
                    drug_node(r.drug),
                    reaction_node(r.pt),
                    "faers_signal",
                    f"FAERS ({r.dataset})",
                    weight=float(r.eb05),
                    ebgm=round(float(r.ebgm), 3),
                    eb05=round(float(r.eb05), 3),
                    ror=round(float(r.ror), 3),
                    cases=int(r.a),
                    dataset=r.dataset,
                    labelled=bool(r.labelled),
                )
        for e in self.drugs.entries.values():
            nid = f"drug:{e.canonical}"
            if nid not in nodes and not (e.attrs.get("atc") or e.attrs.get("drugbank")):
                continue
            node(nid, "drug", e.canonical, atc=(e.attrs.get("atc") or [None])[0])
            for cls in e.attrs.get("atc_classes", [])[1:]:
                code, name = cls.split(" ", 1)
                if name:
                    edge(nid, node(f"class:{code}", "class", name.strip(), code=code), "in_class", "WHO ATC")
            for cls in e.attrs.get("pharmacologic_classes", []):
                edge(nid, node(f"class:{cls.lower()}", "class", cls), "in_class", "DrugCentral via Hetionet")
        for (s, t) in het["edges"].get("treats", []) + het["edges"].get("palliates", []):
            dname = het["nodes"][t]["name"]
            edge(drug_node(het["nodes"][s]["name"]), node(f"disease:{dname.lower()}", "disease", dname), "treats", "PharmacotherapyDB")
        for (s, t) in het["edges"].get("binds", []):
            edge(drug_node(het["nodes"][s]["name"]), node(f"gene:{t[1]}", "target", t[1]), "targets", "DrugBank via Hetionet")

        graph = {"nodes": list(nodes.values()), "edges": list(edges.values())}
        (self.paths.processed / "kg.json").write_text(json.dumps(graph))
        rel_counts = Counter(e["rel"] for e in edges.values())
        self.stats["kg_nodes"] = len(nodes)
        self.stats["kg_edges"] = len(edges)
        self.stats["kg_relations"] = dict(rel_counts)
        self.graph = graph
        self.log(f"graph: {len(nodes)} nodes, {len(edges)} edges {dict(rel_counts)}")

    # ------------------------------------------------------------------
    def add_passage(self, doc_id: str, source_type: str, title: str, text: str, section: str = "", url: str = "", **meta) -> None:
        level, label = EVIDENCE[source_type]
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 40:
            return
        drugs = meta.pop("drugs", None) or self.drugs.mentions(title + " " + text)
        reactions = meta.pop("reactions", None) or self.reactions.mentions(text)
        self.passages.append(
            {
                "pid": None,
                "doc_id": doc_id,
                "source_type": source_type,
                "evidence_level": level,
                "evidence_label": label,
                "title": title,
                "section": section,
                "text": text,
                "url": url,
                "drugs": drugs[:12],
                "reactions": reactions[:16],
                **meta,
            }
        )

    def corpus_cards(self) -> None:
        for c in self.cards:
            text = c["body"]
            sents = sentences(text)
            for k, idx in enumerate(_chunk_sentences(sents, words=150)):
                self.add_passage(
                    c["id"],
                    "guidance_card",
                    c["title"],
                    " ".join(sents[i] for i in idx),
                    section=c["category"],
                    references=c["references"],
                    drugs=[canonical_drug(d) for d in c["drugs"]] or None,
                    reactions=[canonical_term(r) for r in c["reactions"]] or None,
                )
        self.stats["knowledge_cards"] = len(self.cards)

    def corpus_labels(self) -> None:
        out = []
        for i, lab in enumerate(self.labels):
            doc_id = f"label:{lab['region'].split()[0].lower()}:{re.sub(r'[^a-z0-9]+', '_', lab['label_id'].lower())}:{i}"
            name = lab["substance"] or lab["brand"] or f"{lab['region']} product {lab['label_id']}"
            brand = f" ({lab['brand']})" if lab["brand"] and lab["substance"] else ""
            title = f"{name.title()}{brand}: {lab['section']} [{lab['region']} label]"
            paras = [p for p in lab["text"].split("\n") if p.strip()]
            sents: list[str] = []
            for p in paras:
                sents.extend(sentences(p) if len(p) > 300 else [p])
            for idx in _chunk_sentences(sents, words=150):
                self.add_passage(
                    doc_id,
                    "drug_label",
                    title,
                    " ".join(sents[j] for j in idx),
                    section=lab["section"],
                    region=lab["region"],
                    drugs=[canonical_drug(lab["substance"])] if lab["substance"] else None,
                )
            out.append({"doc_id": doc_id, **lab})
        (self.paths.processed / "labels.json").write_text(json.dumps(out))
        self.stats["label_sections"] = len(self.labels)
        self.stats["label_annotated_events"] = sum(len(l["events"]) for l in self.labels)

    def corpus_pubmed(self) -> None:
        kept = scanned = 0
        for ab in S.iter_pubmed_rct():
            scanned += 1
            text = ab.text
            if not SAFETY.search(text):
                continue
            drugs = self.drugs.mentions(text)
            if not drugs:
                continue
            kept += 1
            roles = [r for r, _ in ab.sentences]
            sents = [s for _, s in ab.sentences]
            head_idx = next((i for i, r in enumerate(roles) if r in ("objective", "background")), 0)
            headline = sents[head_idx]
            headline = headline if len(headline) <= 220 else headline[:217].rsplit(" ", 1)[0] + "..."
            for idx in _chunk_sentences(sents):
                sec_roles = Counter(roles[j] for j in idx)
                section = "/".join(r.title() for r, _ in sec_roles.most_common(2))
                body = " ".join(sents[j] for j in idx)
                self.add_passage(
                    f"pmid:{ab.pmid}",
                    "trial_abstract",
                    headline,
                    body,
                    section=section,
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{ab.pmid}/",
                    roles=sorted(sec_roles),
                    split=ab.split,
                )
        self.stats["pubmed_scanned"] = scanned
        self.stats["pubmed_kept"] = kept
        self.log(f"pubmed: kept {kept} of {scanned} abstracts")

    def corpus_ade(self) -> None:
        rel = self.ade["relations"]
        by_pmid = rel.groupby("pmid")
        n = 0
        for pmid, doc in self.ade["documents"].items():
            sents = doc["positive"] + doc["negative"]
            if not sents:
                continue
            title = doc["positive"][0] if doc["positive"] else sents[0]
            title = title if len(title) <= 200 else title[:197].rsplit(" ", 1)[0] + "..."
            gold = []
            if pmid in by_pmid.groups:
                g = by_pmid.get_group(pmid)
                gold = sorted({(canonical_drug(d.lower()), canonical_term(e)) for d, e in zip(g["drug"], g["effect"])})
            for idx in _chunk_sentences(sents, words=150):
                self.add_passage(
                    f"ade:{pmid}",
                    "case_report",
                    title,
                    " ".join(sents[j] for j in idx),
                    section="Case report sentences",
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    gold_pairs=[list(p) for p in gold[:10]],
                )
            n += 1
        self.stats["case_reports"] = n

    def corpus_cdr(self) -> None:
        for doc in self.cdr:
            sents = sentences(doc["abstract"])
            pairs = sorted({(r["chemical_name"].lower(), r["disease_name"].lower()) for r in doc["relations"]})
            for idx in _chunk_sentences(sents):
                self.add_passage(
                    f"cdr:{doc['pmid']}",
                    "cid_abstract",
                    doc["title"],
                    " ".join(sents[j] for j in idx),
                    section="Abstract",
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{doc['pmid']}/",
                    gold_pairs=[list(p) for p in pairs[:10]],
                )
        self.stats["cdr_abstracts"] = len(self.cdr)

    def corpus_ddi(self) -> None:
        n_pos = 0
        for doc in self.ddi:
            sents = [s["text"] for s in doc["sentences"] if s["text"]]
            if not sents:
                continue
            pos = [p for s in doc["sentences"] for p in s["pairs"] if p["ddi"]]
            n_pos += len(pos)
            stype = "interaction_monograph" if doc["source"] == "DrugBank" else "interaction_abstract"
            names = Counter(canonical_drug(e["text"].lower()) for s in doc["sentences"] for e in s["entities"] if e["type"] in ("drug", "brand"))
            main = names.most_common(1)[0][0] if names else "drug"
            title = f"{main.title()}: drug interactions [{doc['source']}]" if stype == "interaction_monograph" else sents[0][:200]
            for idx in _chunk_sentences(sents, words=150):
                self.add_passage(
                    f"ddi:{doc['id']}",
                    stype,
                    title,
                    " ".join(sents[j] for j in idx),
                    section="Interactions",
                    interaction_types=sorted({p["type"] for p in pos if p["type"]}),
                )
        self.stats["ddi_documents"] = len(self.ddi)
        self.stats["ddi_positive_pairs"] = n_pos

    def corpus_kg(self) -> None:
        """Turn curated graph facts into readable passages (one per drug and SOC)."""
        by_drug: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        for (s, t) in self.het["edges"].get("causes", []):
            d = canonical_drug(self.het["nodes"][s]["name"])
            r = canonical_term(self.het["nodes"][t]["name"])
            soc = self.reactions.entries[r].attrs.get("soc", "Unclassified") if r in self.reactions.entries else "Unclassified"
            by_drug[d][soc].append(self.het["nodes"][t]["name"].lower())
        n = 0
        for d, socs in by_drug.items():
            entry = self.drugs.entries.get(d)
            cls = ""
            if entry is not None:
                atc = entry.attrs.get("atc_classes")
                if atc:
                    cls = f" ({atc[-1].split(' ', 1)[1]})"
            for soc, terms in sorted(socs.items(), key=lambda kv: -len(kv[1])):
                terms = sorted(set(terms))
                shown = terms[:45]
                more = f" and {len(terms) - len(shown)} further terms" if len(terms) > len(shown) else ""
                text = (
                    f"Side effects of {d}{cls} listed in drug labels and compiled in SIDER 4.1, System Organ Class {soc}: "
                    + ", ".join(shown)
                    + more
                    + f". A listed side effect is a labelled, expected reaction for {d}."
                )
                self.add_passage(f"kg:sider:{d}", "kg_fact", f"{d.title()}: labelled side effects ({soc})", text, section=soc, drugs=[d], reactions=[canonical_term(t) for t in shown[:16]])
                n += 1
        # Indications and classes
        for e in self.drugs.entries.values():
            bits = []
            if e.attrs.get("atc"):
                classes = "; ".join(c.split(" ", 1)[1] for c in e.attrs.get("atc_classes", []) if " " in c)
                bits.append(f"WHO ATC code {', '.join(e.attrs['atc'][:3])} ({classes}), anatomical group {e.attrs.get('anatomical_group', '').lower()}")
            if e.attrs.get("pharmacologic_classes"):
                bits.append("pharmacologic classes " + ", ".join(e.attrs["pharmacologic_classes"][:8]))
            if e.attrs.get("brands"):
                bits.append("brand names " + ", ".join(sorted(e.attrs["brands"])[:8]))
            if len(bits) >= 2:
                self.add_passage(f"kg:drug:{e.canonical}", "kg_fact", f"{e.canonical.title()}: classification", f"{e.canonical.title()}: " + "; ".join(bits) + ".", section="Classification", drugs=[e.canonical], reactions=[])
                n += 1
        self.stats["kg_passages"] = n

    def corpus_signals(self) -> None:
        sc = self.scored
        notes = S.faers_dataset_notes()
        n = 0
        for (dataset, drug), part in sc.groupby(["dataset", "drug"]):
            total = int(part["a"].sum())
            sig = part[(part["eb05"] >= 2) & (part["a"] >= 3)].sort_values("eb05", ascending=False)
            unl = sig[~sig["labelled"]] if bool(part["label_known"].iloc[0]) else sig.iloc[0:0]
            top = ", ".join(f"{r.pt} (cases {r.a}, EBGM {r.ebgm:.1f}, EB05 {r.eb05:.1f}, ROR {r.ror:.1f})" for r in sig.head(12).itertuples())
            label_line = (
                f" Of these, {len(sig) - len(unl)} are listed in label derived references and {len(unl)} are not, for example "
                + ", ".join(unl.head(6)["pt"])
                + "."
                if len(unl)
                else (" All screened signals are listed in label derived references." if len(sig) and bool(part["label_known"].iloc[0]) else "")
            )
            text = (
                f"FAERS disproportionality screen for {drug} ({notes[dataset].split(';')[0]}): {total} drug and event pairs across {len(part)} preferred terms. "
                f"{len(sig)} preferred terms reach the EB05 of at least 2 screening threshold. Strongest: {top or 'none'}.{label_line} "
                "Disproportionality reflects reporting patterns, not incidence, and requires clinical review."
            )
            self.add_passage(f"faers:{dataset}:{drug}", "signal_summary", f"{drug.title()}: FAERS signal screen ({dataset.replace('_', ' ')})", text, section="Overview", drugs=[drug], reactions=[canonical_term(p) for p in sig.head(16)["pt"]])
            n += 1
            for soc, sp in sig.groupby("soc"):
                if len(sp) < 2:
                    continue
                items = ", ".join(f"{r.pt} ({r.a} cases, EB05 {r.eb05:.1f}{', labelled' if r.labelled else ''})" for r in sp.head(15).itertuples())
                self.add_passage(
                    f"faers:{dataset}:{drug}",
                    "signal_summary",
                    f"{drug.title()}: FAERS signals in {soc}",
                    f"FAERS signals for {drug} in {soc} ({dataset.replace('_', ' ')} dataset, EB05 of at least 2): {items}.",
                    section=soc,
                    drugs=[drug],
                    reactions=[canonical_term(p) for p in sp.head(16)["pt"]],
                )
                n += 1
        self.stats["signal_passages"] = n

    # ------------------------------------------------------------------
    def finalise(self) -> None:
        counts: Counter = Counter()
        for p in self.passages:
            counts[p["doc_id"]] += 1
            p["pid"] = f"{p['doc_id']}#{counts[p['doc_id']]}"
        with gzip.open(self.paths.processed / "passages.jsonl.gz", "wt", encoding="utf8") as fh:
            for p in self.passages:
                fh.write(json.dumps(p) + "\n")
        st = Counter(p["source_type"] for p in self.passages)
        self.stats["passages"] = len(self.passages)
        self.stats["documents"] = len(counts)
        self.stats["passages_by_source"] = dict(st)
        self.stats["words"] = int(sum(len(p["text"].split()) for p in self.passages))
        self.stats["build_seconds"] = round(time.time() - self.t0, 1)
        (self.paths.processed / "build_stats.json").write_text(json.dumps(self.stats, indent=2))
        self.log(f"corpus: {len(self.passages)} passages from {len(counts)} documents {dict(st)}")

    def run(self) -> dict:
        self.load_sources()
        self.build_dictionaries()
        self.build_signals()
        self.build_graph()
        self.corpus_cards()
        self.corpus_labels()
        self.corpus_signals()
        self.corpus_kg()
        self.corpus_ddi()
        self.corpus_cdr()
        self.corpus_ade()
        self.corpus_pubmed()
        self.finalise()
        return self.stats


def build_all() -> dict:
    return Builder().run()


if __name__ == "__main__":
    build_all()
