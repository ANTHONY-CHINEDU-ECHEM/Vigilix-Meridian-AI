"""Parsers that turn each raw public source into tidy Python records.

Every parser is pure (raw files in, records out) so it can be unit tested
and re run without side effects. The knowledge base builder in
``vigilix.kb.build`` composes them.
"""
from __future__ import annotations

import bz2
import html
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd

from vigilix.config import SETTINGS

RAW = SETTINGS.paths.raw


# ---------------------------------------------------------------------------
# PubMed 200k RCT
# ---------------------------------------------------------------------------
@dataclass
class Abstract:
    pmid: str
    sentences: list[tuple[str, str]]  # (role, sentence)
    split: str

    @property
    def text(self) -> str:
        return " ".join(s for _, s in self.sentences)


_DETOK = [
    (re.compile(r"\s+([,.;:%)\]])"), r"\1"),
    (re.compile(r"([(\[])\s+"), r"\1"),
    (re.compile(r"\s+(-)\s+"), r"\1"),
    (re.compile(r"\s+/\s+"), "/"),
    (re.compile(r"\s+'\s*s\b"), "'s"),
]


def detokenise(text: str) -> str:
    """PubMed 200k RCT ships tokenised text ("( 95 % CI )"); restore prose."""
    for pat, rep in _DETOK:
        text = pat.sub(rep, text)
    return text.strip()


def iter_pubmed_rct(folder: Path | None = None) -> Iterator[Abstract]:
    folder = folder or RAW / "pubmed_rct"
    for split, name in (("train", "train.txt"), ("dev", "dev.txt"), ("test", "test.txt")):
        path = folder / name
        pmid, sents = None, []
        with path.open(encoding="utf8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if line.startswith("###"):
                    if pmid and sents:
                        yield Abstract(pmid, sents, split)
                    pmid, sents = line[3:].strip(), []
                elif line.strip() and "\t" in line:
                    role, sent = line.split("\t", 1)
                    sents.append((role.lower(), detokenise(sent)))
        if pmid and sents:
            yield Abstract(pmid, sents, split)


# ---------------------------------------------------------------------------
# ADE corpus (Gurulingappa 2012)
# ---------------------------------------------------------------------------
def load_ade_corpus(folder: Path | None = None) -> dict:
    """Return relations, negative sentences and documents reassembled by PMID.

    The corpus distributes sentences; offsets are given at document level,
    which lets us reconstruct the order of annotated sentences inside each
    case report. Negative sentences carry no offsets and are appended.
    """
    folder = folder or RAW / "ade_corpus"
    rel_rows = []
    for line in (folder / "DRUG-AE.rel").read_text(encoding="utf8", errors="replace").splitlines():
        parts = line.split("|")
        if len(parts) < 8:
            continue
        pmid, sent, ae, ae_b, ae_e, drug, d_b, d_e = parts[:8]
        rel_rows.append(
            dict(pmid=pmid, sentence=sent, effect=ae, effect_begin=int(ae_b), effect_end=int(ae_e), drug=drug, drug_begin=int(d_b), drug_end=int(d_e))
        )
    rel = pd.DataFrame(rel_rows)
    dose_rows = []
    for line in (folder / "DRUG-DOSE.rel").read_text(encoding="utf8", errors="replace").splitlines():
        parts = line.split("|")
        if len(parts) >= 8:
            dose_rows.append(dict(pmid=parts[0], sentence=parts[1], dose=parts[2], drug=parts[5]))
    neg_rows = []
    for line in (folder / "ADE-NEG.txt").read_text(encoding="utf8", errors="replace").splitlines():
        m = re.match(r"(\d+)\s+NEG\s+(.*)", line)
        if m:
            neg_rows.append(dict(pmid=m.group(1), sentence=m.group(2).strip()))
    neg = pd.DataFrame(neg_rows)

    docs: dict[str, dict] = {}
    pos_order: dict[str, dict[str, int]] = defaultdict(dict)
    for r in rel.itertuples():
        start = min(r.effect_begin, r.drug_begin)
        cur = pos_order[r.pmid].get(r.sentence)
        pos_order[r.pmid][r.sentence] = start if cur is None else min(cur, start)
    for pmid, sents in pos_order.items():
        ordered = [s for s, _ in sorted(sents.items(), key=lambda kv: kv[1])]
        docs[pmid] = {"pmid": pmid, "positive": ordered, "negative": []}
    for r in neg.itertuples():
        docs.setdefault(r.pmid, {"pmid": r.pmid, "positive": [], "negative": []})["negative"].append(r.sentence)
    return {"relations": rel, "doses": pd.DataFrame(dose_rows), "negatives": neg, "documents": docs}


# ---------------------------------------------------------------------------
# DDI corpus 2013
# ---------------------------------------------------------------------------
def load_ddi_corpus(path: Path | None = None) -> list[dict]:
    path = path or RAW / "ddi_corpus" / "DDICorpus-2013.zip"
    docs: dict[str, dict] = {}
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if not name.endswith(".xml") or "DrugNER" in name:
                continue
            split = "test" if "/Test/" in name else "train"
            source = "DrugBank" if "DrugBank" in name else "MedLine"
            root = ET.fromstring(zf.read(name))
            doc_id = root.get("id")
            sentences = []
            for s in root.iter("sentence"):
                ents = {e.get("id"): {"text": e.get("text"), "type": e.get("type"), "offset": e.get("charOffset")} for e in s.iter("entity")}
                pairs = []
                for p in s.iter("pair"):
                    e1, e2 = ents.get(p.get("e1")), ents.get(p.get("e2"))
                    if e1 is None or e2 is None:
                        continue
                    pairs.append({"e1": e1["text"], "e2": e2["text"], "ddi": p.get("ddi") == "true", "type": p.get("type")})
                sentences.append({"text": s.get("text", ""), "entities": list(ents.values()), "pairs": pairs})
            docs[doc_id] = {"id": doc_id, "source": source, "split": split, "sentences": sentences}
    return list(docs.values())


# ---------------------------------------------------------------------------
# BioCreative V chemical disease relation corpus
# ---------------------------------------------------------------------------
def load_cdr(path: Path | None = None) -> list[dict]:
    path = path or RAW / "cdr_corpus" / "CDR_Data.zip"
    out = []
    with zipfile.ZipFile(path) as zf:
        for split, name in (
            ("train", "CDR_Data/CDR.Corpus.v010516/CDR_TrainingSet.PubTator.txt"),
            ("dev", "CDR_Data/CDR.Corpus.v010516/CDR_DevelopmentSet.PubTator.txt"),
            ("test", "CDR_Data/CDR.Corpus.v010516/CDR_TestSet.PubTator.txt"),
        ):
            text = zf.read(name).decode("utf8")
            for block in text.strip().split("\n\n"):
                lines = block.strip().split("\n")
                if len(lines) < 2:
                    continue
                pmid = lines[0].split("|")[0]
                title = lines[0].split("|t|", 1)[1]
                abstract = lines[1].split("|a|", 1)[1] if "|a|" in lines[1] else ""
                mentions, relations = [], []
                for ln in lines[2:]:
                    f = ln.split("\t")
                    if len(f) >= 6 and f[1].isdigit():
                        mentions.append({"begin": int(f[1]), "end": int(f[2]), "text": f[3], "type": f[4], "mesh": f[5]})
                    elif len(f) >= 4 and f[1] == "CID":
                        relations.append({"chemical": f[2], "disease": f[3]})
                names: dict[str, str] = {}
                for m in mentions:
                    for mesh in m["mesh"].split("|"):
                        names.setdefault(mesh, m["text"])
                rel_named = [
                    {**r, "chemical_name": names.get(r["chemical"], r["chemical"]), "disease_name": names.get(r["disease"], r["disease"])} for r in relations
                ]
                out.append({"pmid": pmid, "split": split, "title": title, "abstract": abstract, "mentions": mentions, "relations": rel_named})
    return out


# ---------------------------------------------------------------------------
# Drug label safety sections (US, UK, EU) with annotated adverse events
# ---------------------------------------------------------------------------
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t ]+")


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?i)</(p|div|tr|li|h\d|summary|details)>", "\n", raw)
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)</t[dh]>", " | ", raw)
    text = html.unescape(_TAG.sub(" ", raw))
    lines = [_WS.sub(" ", ln).strip(" |") for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def load_labels(folder: Path | None = None, products: dict | None = None) -> list[dict]:
    folder = folder or RAW / "onsides_annot"
    products = products or json.loads((SETTINGS.paths.knowledge / "label_products.json").read_text())
    us_map = {k.lower(): v for k, v in products["us"].items()}
    eu_map = {k.lower().strip(): v for k, v in products["eu"].items()}
    files = (
        ("demner-fushman-train-labels.json", "US", "train"),
        ("demner-fushman-test-labels.json", "US", "test"),
        ("uk-annot.json", "UK", "all"),
        ("eu-annot.json", "EU", "all"),
        ("fda-pediatric-special-populations-annot.json", "US paediatric", "all"),
    )
    section_names = {
        "adverse reactions": "Adverse reactions",
        "warnings and precautions": "Warnings and precautions",
        "boxed warnings": "Boxed warning",
        "UNDESIRABLE_EFFECTS": "4.8 Undesirable effects",
        "S1": "4.8 Undesirable effects",
        "SP": "Use in specific populations (paediatric)",
    }
    out = []
    for fname, region, split in files:
        for rec in json.loads((folder / fname).read_text()):
            raw = rec["section_text"] or ""
            text = html_to_text(raw) if "<" in raw else re.sub(r"[ \t]+", " ", raw).strip()
            label_id = str(rec["label_id"])
            brand = label_id if region in ("US", "EU") else None
            substance = None
            if region == "US":
                substance = us_map.get(label_id.lower())
            elif region == "EU":
                substance = eu_map.get(label_id.lower().strip())
            events = []
            for ev in rec.get("adverse_events") or []:
                if not ev:
                    continue
                mention = ev[0]
                pt = ev[3] if len(ev) > 3 and isinstance(ev[3], str) else (ev[1] if len(ev) > 1 else mention)
                if isinstance(pt, float) or pt is None:
                    pt = ev[1] if len(ev) > 1 and isinstance(ev[1], str) else mention
                events.append({"mention": str(mention), "pt": str(pt)})
            out.append(
                {
                    "label_id": label_id,
                    "region": region,
                    "split": split,
                    "brand": brand,
                    "substance": substance,
                    "section": section_names.get(rec["section_name"], rec["section_name"]),
                    "text": text,
                    "events": events,
                }
            )
    return out


# ---------------------------------------------------------------------------
# Hetionet (SIDER side effects, indications, pharmacologic classes)
# ---------------------------------------------------------------------------
def load_hetionet(path: Path | None = None) -> dict:
    path = path or RAW / "hetionet" / "hetionet-v1.0.json.bz2"
    data = json.load(bz2.open(path))
    nodes = {(n["kind"], str(n["identifier"])): n for n in data["nodes"]}
    keep = {"Compound", "Side Effect", "Disease", "Pharmacologic Class", "Symptom"}
    out_nodes = {k: {"kind": k[0], "id": k[1], "name": v["name"]} for k, v in nodes.items() if k[0] in keep}
    edges = defaultdict(list)
    for e in data["edges"]:
        s = (e["source_id"][0], str(e["source_id"][1]))
        t = (e["target_id"][0], str(e["target_id"][1]))
        if e["kind"] in {"causes", "treats", "palliates", "includes", "resembles"} and s in out_nodes and t in out_nodes:
            edges[e["kind"]].append((s, t))
        elif e["kind"] == "binds" and s[0] == "Compound":
            gene = nodes.get(t)
            edges["binds"].append((s, ("Gene", gene["name"] if gene else t[1])))
    class_type = {str(n["identifier"]): n.get("data", {}).get("class_type", "") for n in data["nodes"] if n["kind"] == "Pharmacologic Class"}
    return {"nodes": out_nodes, "edges": dict(edges), "class_type": class_type}


# ---------------------------------------------------------------------------
# WHO ATC classification
# ---------------------------------------------------------------------------
def load_atc(path: Path | None = None) -> pd.DataFrame:
    path = path or RAW / "atc" / "WHO ATC-DDD 2026-04-25.csv"
    df = pd.read_csv(path, dtype=str)
    df["level"] = df["atc_code"].str.len().map({1: 1, 3: 2, 4: 3, 5: 4, 7: 5})
    return df.drop_duplicates(subset=["atc_code", "atc_name"])


# ---------------------------------------------------------------------------
# FAERS contingency tables
# ---------------------------------------------------------------------------
def _matrix_to_long(df: pd.DataFrame, dataset: str, period: str) -> pd.DataFrame:
    df = df.rename(columns={df.columns[0]: "pt"}).set_index("pt")
    total = df.values.sum()
    col_tot = df.sum(axis=0)
    row_tot = df.sum(axis=1)
    rows = []
    for drug in [c for c in df.columns if c.lower() != "other"]:
        for pt in df.index:
            if str(pt).lower() == "other":
                continue
            a = int(df.at[pt, drug])
            b = int(col_tot[drug] - a)
            c = int(row_tot[pt] - a)
            d = int(total - a - b - c)
            rows.append((dataset, period, drug.lower(), str(pt), a, b, c, d))
    return pd.DataFrame(rows, columns=["dataset", "period", "drug", "pt", "a", "b", "c", "d"])


def load_faers_tables(folder_mddc: Path | None = None, folder_covid: Path | None = None) -> pd.DataFrame:
    folder_mddc = folder_mddc or RAW / "faers_mddc"
    folder_covid = folder_covid or RAW / "faers_covid"
    frames = [
        _matrix_to_long(pd.read_csv(folder_mddc / "sedative1000.csv"), "sedatives", "2021Q1 to 2023Q4"),
        _matrix_to_long(pd.read_csv(folder_mddc / "betablocker500.csv"), "beta_blockers", "2021Q1 to 2023Q4"),
        _matrix_to_long(pd.read_csv(folder_mddc / "statin101.csv"), "statins", "2014Q1 to 2020Q4"),
    ]
    cov = pd.read_excel(folder_covid / "2_contigence table_4_drugs.xlsx")
    cov = cov.rename(columns={"prod_ai": "drug", "cnt_a": "a", "cnt_b": "b", "cnt_c": "c", "cnt_d": "d", "SOC": "soc"})
    cov["drug"] = cov["drug"].str.lower().str.replace("\\", " ", regex=False)
    cov["dataset"] = "covid19_fast_track"
    cov["period"] = "2020Q1 to 2022Q2"
    for col in "abcd":
        cov[col] = cov[col].fillna(0).astype(np.int64)
    frames.append(cov[["dataset", "period", "drug", "pt", "a", "b", "c", "d", "soc"]])
    out = pd.concat(frames, ignore_index=True)
    soc = cov.drop_duplicates("pt").set_index("pt")["soc"].to_dict()
    out["soc"] = out["pt"].map(soc).fillna(out.get("soc"))
    return out


def faers_dataset_notes() -> dict:
    return {
        "sedatives": "FAERS 2021Q1 to 2023Q4; 1,000 most frequent preferred terms by 10 sedatives and hypnotics; 'Off label use' and 'Drug ineffective' excluded by the curators. Cells are drug and event pair counts.",
        "beta_blockers": "FAERS 2021Q1 to 2023Q4; 500 most frequent preferred terms by 9 beta blockers.",
        "statins": "FAERS 2014Q1 to 2020Q4; 101 preferred terms by 4 statins (Ding, Markatou and Ball 2020).",
        "covid19_fast_track": "FAERS 2020Q1 to 2022Q2, 5,248,821 deduplicated cases; every preferred term reported with 4 fast track COVID 19 products.",
    }


# ---------------------------------------------------------------------------
# OHDSI reference sets
# ---------------------------------------------------------------------------
def load_reference_sets(folder: Path | None = None) -> pd.DataFrame:
    import pyreadr

    folder = folder or RAW / "ohdsi_reference"
    frames = []
    for name, label in (("omopReferenceSet", "OMOP"), ("euadrReferenceSet", "EU-ADR")):
        r = pyreadr.read_r(str(folder / f"{name}.rda"))
        df = list(r.values())[0]
        df = df[["exposureName", "outcomeName", "groundTruth"]].copy()
        df.columns = ["drug", "outcome", "positive"]
        df["drug"] = df["drug"].str.lower()
        df["outcome"] = (
            df["outcome"]
            .str.replace(r"^OMOP\s+", "", regex=True)
            .str.replace(r"\s*#\d+$", "", regex=True)
            .str.replace(r"\s+1$", "", regex=True)
            .replace(
                {
                    "HOI Upper GI": "Upper gastrointestinal bleeding",
                    "Leukopenia Including Neutropenia and Agranulocytosis": "Leukopenia",
                    "Acute myocardial Infarction": "Acute myocardial infarction",
                    "Stevens-Johnson Syndrome": "Stevens Johnson syndrome",
                }
            )
        )
        df["reference_set"] = label.replace("-", " ")
        frames.append(df)
    return pd.concat(frames, ignore_index=True)
