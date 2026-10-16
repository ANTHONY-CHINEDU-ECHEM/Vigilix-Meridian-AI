"""Drug and reaction dictionaries with a longest match entity linker.

The drug dictionary unifies WHO ATC substances, Hetionet (DrugBank derived)
compounds, brand names from the lexicon, the substances behind every
annotated label, FAERS product names and the drugs named in the OMOP and
EU ADR reference sets. The reaction dictionary unifies SIDER side effect
terms, FAERS preferred terms, the preferred terms used by label annotators
and the OHDSI outcome names, each with a MedDRA style System Organ Class.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from vigilix.rag.text import apply_spelling, canonical_drug, canonical_term, lexicon, raw_tokens

# Names that collide with ordinary English or with lab analytes when linked
# from free text. They stay in the dictionary for exact lookups but are not
# linked inside prose.
NON_LINKABLE = {
    "water", "oxygen", "iron", "gold", "lead", "tin", "zinc", "copper", "silver", "carbon", "nitrogen", "sulfur", "sodium", "potassium",
    "calcium", "magnesium", "glucose", "sucrose", "lactose", "alcohol", "ethanol", "air", "salt", "light", "placebo", "control",
    "vitamin", "vitamins", "protein", "proteins", "insulin", "estrogen", "estrogens", "progesterone", "hormone", "hormones", "contrast", "acid",
    "various", "combinations", "others", "cell", "cells", "plant", "plants", "factor", "colony", "agent", "agents", "test", "tests",
    "barium", "fluoride", "chlorine", "iodine", "bromide", "lithium carbonate", "sodium chloride", "potassium chloride", "nicotine", "caffeine",
    "dextrose", "creatine", "creatinine", "heparin sodium", "urea", "nitric oxide", "oxygen therapy", "omega", "collagen", "gelatin", "starch", "paraffin", "talc",
}
NON_REACTIONS = {"elderly", "adult", "child", "children", "infant", "male", "female", "pregnancy", "drug interaction", "off label use", "product use issue", "no adverse event", "drug ineffective", "unevaluable event", "therapeutic response unexpected", "product use in unapproved indication", "drug effective"}
# Reaction dictionary names that are mostly study design, procedures,
# indications or laboratory analytes when they appear in prose.
NON_LINKABLE_REACTION = {
    "blind", "pain relief", "surgery", "reaction", "reactions", "chemotherapy", "infusion", "weight", "injection", "blood pressure", "mortality",
    "anesthesia", "general anesthesia", "hemoglobin", "heart rate", "gastrointestinal", "mass", "fasting", "prophylaxis", "morbidity", "hospitalization",
    "died", "death", "deaths", "discharge", "cholesterol", "total cholesterol", "diabetic", "fatal", "radiotherapy", "ocular", "transfusion", "nervous",
    "scales", "investigation", "disability", "radiation", "blood glucose", "antibodies", "intensive care", "illness", "stress", "triglycerides",
    "diastolic blood pressure", "systolic blood pressure", "albumin", "intraocular pressure", "treatment failure", "wound", "withdrawn", "phosphate",
    "creatinine", "serum creatinine", "c reactive protein", "ejection fraction", "pregnant", "bacterial", "cancer", "tumor", "breast cancer",
    "non small cell lung cancer", "diabetes", "diabetes mellitus", "asthma", "schizophrenia", "rheumatoid arthritis", "osteoarthritis", "psoriasis",
    "copd", "hypertensive", "disease progression", "adverse event", "adverse events", "adverse reaction", "adverse drug reaction", "immune response",
    "body surface area", "discomfort", "ill defined disorder", "feeling abnormal", "condition aggravated", "drug ineffective", "therapeutic response decreased",
    "pregnancy", "labour", "labor", "delivery", "biopsy", "hiv", "hiv infection", "hepatitis c", "influenza", "covid 19", "sars cov 2 infection",
    "epilepsy", "parkinson s disease", "alzheimer s disease", "obesity", "smoking", "alcohol use", "glucose", "insulin", "potassium", "sodium", "calcium",
    "bilirubin", "platelet count", "white blood cell count", "body weight", "body mass index", "lymphoma", "leukemia", "multiple myeloma", "melanoma",
    "cardiac failure chronic", "angina pectoris", "hypercholesterolemia", "dyslipidemia", "major depression",
    "bipolar disorder", "anxiety disorder", "inflammation", "creatine", "dark", "urine",
}
LINKABLE_SHORT = {"asa", "inh", "5fu", "ddi", "mtx", "aza", "ace"}

SOC_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Hepatobiliary disorders", ("hepat", "liver", "jaundice", "cholestas", "biliar", "bilirubin", "transaminase", "cholecyst", "gallbladder")),
    ("Renal and urinary disorders", ("renal", "kidney", "nephr", "urinar", "dysuria", "hematuria", "proteinuria", "cystitis", "anuria", "oliguria", "bladder")),
    ("Cardiac disorders", ("cardiac", "heart", "myocard", "arrhythm", "tachycard", "bradycard", "atrial", "ventricular", "torsade", "angina", "palpitation", "pericard", "cardiomyopathy")),
    ("Vascular disorders", ("hypertens", "hypotens", "vascul", "thrombo", "embol", "phlebitis", "flushing", "hot flush", "hemorrhage", "haemorrhage", "hematoma", "vasculitis", "shock")),
    ("Nervous system disorders", ("neuro", "seizure", "convuls", "headache", "migraine", "dizziness", "somnolence", "tremor", "paresthesia", "neuropathy", "ataxia", "syncope", "dysgeusia", "stroke", "cerebr", "encephal", "coma", "dyskinesia", "akathisia", "parkinson", "memory", "amnesia", "sedation", "consciousness")),
    ("Psychiatric disorders", ("depress", "anxiety", "insomnia", "suicid", "halluc", "psych", "confus", "agitation", "mania", "delirium", "nightmare", "abnormal dreams", "libido", "nervousness", "mood", "aggression", "dependence")),
    ("Gastrointestinal disorders", ("nausea", "vomit", "diarrh", "constipation", "abdominal", "dyspepsia", "gastr", "colitis", "pancreat", "stomatitis", "esophag", "oesophag", "dry mouth", "flatulence", "dysphagia", "ileus", "peptic", "rectal", "gingiv", "mouth")),
    ("Skin and subcutaneous tissue disorders", ("rash", "prurit", "urticar", "dermat", "alopecia", "erythema", "stevens", "epidermal necrolysis", "skin", "hyperhidrosis", "photosens", "eczema", "acne", "angioedema", "blister")),
    ("Musculoskeletal and connective tissue disorders", ("myalg", "arthralg", "rhabdomyol", "muscle", "back pain", "musculoskeletal", "tendon", "tendin", "osteo", "bone", "joint", "myopathy", "pain in extremity", "arthritis", "fracture")),
    ("Blood and lymphatic system disorders", ("anemia", "anaemia", "neutropen", "thrombocytopen", "leukopen", "agranulocyt", "pancytopen", "lymphopen", "eosinophil", "hemoly", "haemoly", "coagulopathy", "aplastic", "bone marrow")),
    ("Respiratory, thoracic and mediastinal disorders", ("dyspn", "cough", "pneumon", "bronch", "respiratory", "pulmonary", "asthma", "epistaxis", "pleural", "lung", "nasal", "rhinorr", "apnea", "apnoea", "hypoxia", "wheez")),
    ("Infections and infestations", ("infection", "sepsis", "influenza", "nasopharyngitis", "herpes", "candid", "abscess", "covid", "viral", "bacterial", "fungal", "cellulitis", "sinusitis", "tuberc")),
    ("Immune system disorders", ("anaphyla", "hypersensitivity", "allerg", "immune", "serum sickness", "sarcoidosis")),
    ("Metabolism and nutrition disorders", ("hypoglyc", "hyperglyc", "diabet", "hyperkal", "hypokal", "hyponatr", "hypernatr", "dehydration", "appetite", "acidosis", "gout", "hyperlipid", "hypercalc", "hypocalc", "hypomagnes", "lipid", "anorexia", "weight")),
    ("Endocrine disorders", ("thyroid", "adrenal", "cushing", "pituitar", "hypogonad", "inappropriate antidiuretic")),
    ("Eye disorders", ("vision", "visual", "eye", "ocular", "cataract", "glaucoma", "retin", "macular", "conjunctiv", "blindness", "diplopia", "uveitis", "kerat", "lacrimation")),
    ("Ear and labyrinth disorders", ("ear", "tinnitus", "vertigo", "deafness", "hearing", "ototox")),
    ("Reproductive system and breast disorders", ("erectile", "menstrua", "breast", "gynecomastia", "gynaecomastia", "vagin", "ovarian", "testicular", "uterine", "amenorrh", "priapism", "ejaculation")),
    ("Pregnancy, puerperium and perinatal conditions", ("pregnan", "abortion", "fetal", "foetal", "neonatal", "premature", "stillbirth")),
    ("Congenital, familial and genetic disorders", ("congenital", "malformation", "teratogen")),
    ("Neoplasms benign, malignant and unspecified", ("neoplasm", "cancer", "carcinoma", "lymphoma", "leukemia", "leukaemia", "tumor", "tumour", "melanoma", "sarcoma", "myeloma", "malignan")),
    ("Investigations", ("increased", "decreased", "abnormal", "prolonged", "blood ", "electrocardiogram", "laboratory", "test", "count", "level", "clearance", "ratio")),
    ("Injury, poisoning and procedural complications", ("overdose", "poisoning", "fall", "injury", "toxicity to various agents", "medication error", "wrong", "accidental", "procedural", "contusion", "laceration", "intentional")),
    ("General disorders and administration site conditions", ("fatigue", "asthenia", "pyrexia", "fever", "edema", "oedema", "malaise", "chills", "injection site", "infusion", "death", "pain", "drug ineffective", "condition aggravated", "chest discomfort", "inflammation", "withdrawal syndrome", "therapeutic")),
    ("Social circumstances", ("social", "abuse", "drug dependence")),
    ("Surgical and medical procedures", ("surgery", "transplant", "hospitalisation", "hospitalization", "procedure")),
]


def assign_soc(term: str, table: dict[str, str] | None = None) -> str:
    if table:
        hit = table.get(term.lower())
        if hit:
            return hit
    t = " " + term.lower() + " "
    for soc, keys in SOC_RULES:
        if any(k in t for k in keys):
            return soc
    return "Unclassified"


def _key(name: str) -> tuple[str, ...]:
    return tuple(apply_spelling(t) for t in raw_tokens(name))


@dataclass
class Entry:
    canonical: str
    display: str
    kind: str
    synonyms: set[str] = field(default_factory=set)
    attrs: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {"canonical": self.canonical, "display": self.display, "kind": self.kind, "synonyms": sorted(self.synonyms), **self.attrs}


class Dictionary:
    """A name to canonical entry map with longest match linking in text."""

    def __init__(self, kind: str):
        self.kind = kind
        self.entries: dict[str, Entry] = {}
        self._index: dict[tuple[str, ...], str] = {}
        self._linkable: dict[tuple[str, ...], str] = {}
        self.max_len = 1

    def add(self, canonical: str, display: str | None = None, synonyms: tuple[str, ...] = (), linkable: bool = True, **attrs) -> Entry:
        canonical = canonical.strip().lower()
        if not canonical:
            raise ValueError("empty canonical name")
        e = self.entries.get(canonical)
        if e is None:
            e = Entry(canonical, display or canonical, self.kind)
            self.entries[canonical] = e
        for k, v in attrs.items():
            if isinstance(v, (list, set, tuple)):
                cur = e.attrs.setdefault(k, [])
                for x in v:
                    if x not in cur:
                        cur.append(x)
            elif v is not None and k not in e.attrs:
                e.attrs[k] = v
        for name in (canonical, *synonyms):
            name = name.strip().lower()
            if not name:
                continue
            e.synonyms.add(name)
            key = _key(name)
            if not key:
                continue
            self._index.setdefault(key, canonical)
            blocked = NON_LINKABLE_REACTION if self.kind == "reaction" else NON_LINKABLE
            ok = linkable and name not in blocked and " ".join(key) not in blocked and (len(name) >= 4 or name in LINKABLE_SHORT) and not name.isdigit()
            if ok:
                self._linkable.setdefault(key, canonical)
                self.max_len = max(self.max_len, len(key))
        return e

    def lookup(self, name: str) -> Entry | None:
        hit = self._index.get(_key(name))
        return self.entries.get(hit) if hit else None

    def link(self, text: str) -> list[tuple[str, int, int]]:
        """Return (canonical, token_start, token_end) for every mention."""
        toks = [apply_spelling(t) for t in raw_tokens(text)]
        out = []
        i = 0
        while i < len(toks):
            hit = None
            for span in range(min(self.max_len, len(toks) - i), 0, -1):
                c = self._linkable.get(tuple(toks[i : i + span]))
                if c:
                    hit = (c, i, i + span)
                    break
            if hit:
                out.append(hit)
                i = hit[2]
            else:
                i += 1
        return out

    def mentions(self, text: str) -> list[str]:
        seen, out = set(), []
        for c, _, _ in self.link(text):
            if c not in seen:
                seen.add(c)
                out.append(c)
        return out

    def to_json(self) -> dict:
        return {"kind": self.kind, "entries": [e.to_json() for e in self.entries.values()]}

    @classmethod
    def from_json(cls, data: dict) -> "Dictionary":
        d = cls(data["kind"])
        for e in data["entries"]:
            attrs = {k: v for k, v in e.items() if k not in {"canonical", "display", "kind", "synonyms"}}
            d.add(e["canonical"], e["display"], tuple(e["synonyms"]), linkable=e.get("linkable", True), **attrs)
        return d


def _clean_drug_name(name: str) -> str:
    name = name.lower().replace("\\", " ").replace("/", " ")
    name = re.sub(r"\b(and|combinations?|with|plain|comb)\b", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def build_drug_dictionary(het: dict, atc, labels: list[dict], faers, reference, ade_rel, ddi_docs) -> Dictionary:
    d = Dictionary("drug")
    lex = lexicon()
    # WHO ATC substances with their class hierarchy
    by_code = {r.atc_code: r.atc_name for r in atc.itertuples()}
    for r in atc[atc.level == 5].itertuples():
        raw_name = str(r.atc_name).lower()
        if any(w in raw_name for w in (" and ", "combination", "various")):
            continue
        canon = canonical_drug(_clean_drug_name(raw_name))
        if len(canon) < 3:
            continue
        code = r.atc_code
        d.add(
            canon,
            raw_name,
            (raw_name,),
            atc=[code],
            atc_classes=[f"{code[:4]} {by_code.get(code[:4], '').lower()}", f"{code[:5]} {by_code.get(code[:5], '').lower()}"],
            anatomical_group=by_code.get(code[:1], "").title(),
        )
    # Hetionet compounds (DrugBank identifiers) and pharmacologic classes
    for (kind, nid), node in het["nodes"].items():
        if kind == "Compound":
            canon = canonical_drug(node["name"].lower())
            d.add(canon, node["name"].lower(), (node["name"].lower(),), drugbank=nid)
    member_of = defaultdict(list)
    for (ck, cid), (dk, did) in het["edges"].get("includes", []):
        member_of[did].append(het["nodes"][(ck, cid)]["name"])
    for (kind, nid), node in het["nodes"].items():
        if kind == "Compound" and member_of.get(nid):
            d.add(canonical_drug(node["name"].lower()), pharmacologic_classes=member_of[nid])
    # Brands and synonyms from the lexicon
    for brand, generic in lex["brands"].items():
        d.add(canonical_drug(generic), None, (brand,), brands=[brand])
    for syn, generic in lex["drug_synonyms"].items():
        d.add(canonical_drug(generic), None, (syn,))
    for lab in labels:
        if lab["substance"]:
            syns = (lab["brand"].lower(),) if lab["brand"] else ()
            d.add(canonical_drug(lab["substance"]), lab["substance"], syns, brands=[lab["brand"].lower()] if lab["brand"] else [])
    for name in sorted(set(faers["drug"])):
        clean = _clean_drug_name(name)
        d.add(canonical_drug(clean), clean, (clean,), in_faers=True)
    for name in sorted(set(reference["drug"])):
        d.add(canonical_drug(_clean_drug_name(name)), None, (name,))
    counts = Counter(canonical_drug(x) for x in ade_rel["drug"].str.lower())
    for name, n in counts.items():
        if n >= 2 and len(name) >= 4:
            d.add(name, None, (), ade_case_mentions=n)
    ddi_counts = Counter()
    for doc in ddi_docs:
        for s in doc["sentences"]:
            for e in s["entities"]:
                if e["type"] in ("drug", "brand"):
                    ddi_counts[canonical_drug(e["text"].lower())] += 1
    for name, n in ddi_counts.items():
        if n >= 2 and len(name) >= 4 and not name.endswith("s"):
            d.add(name, None, ())
    return d


def build_reaction_dictionary(het: dict, faers, labels: list[dict], reference, ade_rel) -> tuple[Dictionary, dict[str, str]]:
    soc_table = {}
    if "soc" in faers.columns:
        for pt, soc in faers.dropna(subset=["soc"]).drop_duplicates("pt")[["pt", "soc"]].itertuples(index=False):
            soc_table[canonical_term(pt)] = re.sub(r"\s*\(incl.*\)$", "", soc)
    r = Dictionary("reaction")

    def add(term: str, source: str, **attrs):
        term = term.strip()
        if term.lower() in NON_REACTIONS:
            return
        if len(term) < 3:
            return
        canon = canonical_term(term)
        if len(canon) < 3:
            return
        r.add(canon, term, (term.lower(),), sources=[source], soc=assign_soc(canon, soc_table), **attrs)

    for (kind, nid), node in het["nodes"].items():
        if kind == "Side Effect":
            add(node["name"], "SIDER 4.1", umls=nid)
    for pt in sorted(set(faers["pt"])):
        add(str(pt), "FAERS")
    for lab in labels:
        for ev in lab["events"]:
            add(ev["pt"], f"{lab['region']} label annotation")
    for out in sorted(set(reference["outcome"])):
        add(out, "OHDSI reference set")
    counts = Counter(canonical_term(x) for x in ade_rel["effect"])
    for term, n in counts.items():
        if n >= 3:
            add(term, "ADE corpus", ade_case_mentions=n)
    # Lay phrases link to their clinical term
    for lay, clinical in lexicon()["lay_terms"].items():
        canon = canonical_term(clinical)
        if canon in r.entries:
            r.add(canon, None, (lay,))
    return r, soc_table


def save_dictionaries(drugs: Dictionary, reactions: Dictionary, path: Path) -> None:
    path.write_text(json.dumps({"drugs": drugs.to_json(), "reactions": reactions.to_json()}))


def load_dictionaries(path: Path) -> tuple[Dictionary, Dictionary]:
    data = json.loads(path.read_text())
    return Dictionary.from_json(data["drugs"]), Dictionary.from_json(data["reactions"])
