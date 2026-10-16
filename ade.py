"""Adverse drug event extraction from case narratives.

Three trained components, all evaluated on PubMed identifiers held out from
training (an 80/20 split by article, so sentences of one case report never
straddle the split):

1. ``SentenceClassifier``  TF IDF word and character n grams with logistic
   regression: does this sentence describe a drug related adverse effect?
2. ``SpanTagger``  a linear chain conditional random field over BIO tags for
   DRUG and EFFECT spans, with lexical, shape, context and dictionary
   features (the drug and reaction dictionaries of the knowledge base).
3. ``RelationClassifier``  logistic regression over drug and effect pairs
   inside a sentence (token distance, order, causal cue words between the
   two mentions, number of competing mentions).

A dictionary baseline that links drugs and reactions with the knowledge base
dictionaries alone is reported alongside, so the value of learning is visible.
"""
from __future__ import annotations

import json
import pickle
import random
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from vigilix.config import SETTINGS

TOKEN = re.compile(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*|[^\sA-Za-z0-9]")
CUES = ("induced", "induce", "associated", "after", "following", "due", "caused", "causing", "related", "secondary", "developed", "during", "from", "with", "on", "toxicity", "reaction")


def tokenize(text: str) -> list[tuple[str, int, int]]:
    return [(m.group(0), m.start(), m.end()) for m in TOKEN.finditer(text)]


@dataclass
class Sentence:
    pmid: str
    text: str
    drugs: list[tuple[int, int]]
    effects: list[tuple[int, int]]
    relations: list[tuple[tuple[int, int], tuple[int, int]]]
    positive: bool


def load_sentences(ade: dict) -> list[Sentence]:
    """Turn the ADE corpus into sentences with character spans (sentence level)."""
    rel = ade["relations"]
    groups: dict[tuple[str, str], dict] = {}
    for r in rel.itertuples():
        key = (r.pmid, r.sentence)
        g = groups.setdefault(key, {"drugs": set(), "effects": set(), "relations": set()})
        di = r.sentence.find(r.drug)
        ei = r.sentence.find(r.effect)
        if di < 0 or ei < 0:
            # fall back to case insensitive search
            di = r.sentence.lower().find(r.drug.lower())
            ei = r.sentence.lower().find(r.effect.lower())
        if di < 0 or ei < 0:
            continue
        d = (di, di + len(r.drug))
        e = (ei, ei + len(r.effect))
        g["drugs"].add(d)
        g["effects"].add(e)
        g["relations"].add((d, e))
    out = [Sentence(p, s, sorted(g["drugs"]), sorted(g["effects"]), sorted(g["relations"]), True) for (p, s), g in groups.items()]
    for r in ade["negatives"].itertuples():
        out.append(Sentence(r.pmid, r.sentence, [], [], [], False))
    return out


def split_by_pmid(sents: list[Sentence], seed: int, test_frac: float = 0.2) -> tuple[list[Sentence], list[Sentence]]:
    pmids = sorted({s.pmid for s in sents})
    rng = random.Random(seed)
    rng.shuffle(pmids)
    test = set(pmids[: int(len(pmids) * test_frac)])
    return [s for s in sents if s.pmid not in test], [s for s in sents if s.pmid in test]


# ---------------------------------------------------------------------------
# BIO tagging
# ---------------------------------------------------------------------------
def bio_labels(sent: Sentence) -> tuple[list[tuple[str, int, int]], list[str]]:
    toks = tokenize(sent.text)
    labels = ["O"] * len(toks)
    # effects first, then drugs (drug spans win on overlap, they are short and precise)
    for kind, spans in (("EFFECT", sent.effects), ("DRUG", sent.drugs)):
        for b, e in spans:
            inside = [i for i, (_, s, t) in enumerate(toks) if s >= b and t <= e]
            for j, i in enumerate(inside):
                labels[i] = ("B-" if j == 0 else "I-") + kind
    return toks, labels


def _shape(w: str) -> str:
    s = re.sub(r"[A-Z]", "X", w)
    s = re.sub(r"[a-z]", "x", s)
    s = re.sub(r"[0-9]", "d", s)
    return re.sub(r"(.)\1+", r"\1\1", s)


class DictFlags:
    """Token level flags from the knowledge base dictionaries."""

    def __init__(self, drugs, reactions):
        self.drugs = drugs
        self.reactions = reactions

    def flags(self, text: str, toks: list[tuple[str, int, int]]) -> tuple[list[str], list[str]]:
        """B/I/O flags from a longest match lookup of token n grams in each dictionary."""
        dflag = ["O"] * len(toks)
        rflag = ["O"] * len(toks)
        words = [w.lower() for w, _, _ in toks]
        from vigilix.kb.dictionaries import _key

        for dic, arr in ((self.drugs, dflag), (self.reactions, rflag)):
            i = 0
            while i < len(words):
                hit = 0
                for n in range(min(6, len(words) - i), 0, -1):
                    phrase = " ".join(words[i : i + n])
                    k = _key(phrase)
                    if k and k in dic._linkable:
                        hit = n
                        break
                if hit:
                    for j in range(i, i + hit):
                        arr[j] = "B" if j == i else "I"
                    i += hit
                else:
                    i += 1
        return dflag, rflag


def token_features(toks: list[tuple[str, int, int]], dflag: list[str], rflag: list[str]) -> list[dict]:
    feats = []
    words = [w for w, _, _ in toks]
    for i, w in enumerate(words):
        lw = w.lower()
        f = {
            "bias": 1.0,
            "w": lw,
            "suf3": lw[-3:],
            "suf4": lw[-4:],
            "pre3": lw[:3],
            "shape": _shape(w),
            "title": w.istitle(),
            "upper": w.isupper(),
            "digit": w.isdigit(),
            "len": min(len(w), 12),
            "dict_drug": dflag[i],
            "dict_rx": rflag[i],
            "drug_suffix": bool(re.search(r"(mab|nib|pril|sartan|olol|statin|azole|mycin|cillin|floxacin|vir|pine|pam|lam|tide|parin|dronate|tinib|zumab|ximab)$", lw)),
            "rx_suffix": bool(re.search(r"(itis|osis|emia|aemia|pathy|algia|penia|plasia|rrhea|oea|uria|ism|oma|edema|oedema)$", lw)),
        }
        for off in (-2, -1, 1, 2):
            j = i + off
            if 0 <= j < len(words):
                f[f"{off}:w"] = words[j].lower()
                f[f"{off}:dd"] = dflag[j]
                f[f"{off}:dr"] = rflag[j]
            else:
                f[f"{off}:w"] = "<pad>"
        feats.append(f)
    return feats


def spans_from_bio(toks: list[tuple[str, int, int]], labels: list[str]) -> list[tuple[str, int, int]]:
    out = []
    cur = None
    for (w, s, e), lab in zip(toks, labels):
        if lab.startswith("B-") or (lab.startswith("I-") and (cur is None or cur[0] != lab[2:])):
            if cur:
                out.append(tuple(cur))
            cur = [lab[2:], s, e]
        elif lab.startswith("I-") and cur:
            cur[2] = e
        else:
            if cur:
                out.append(tuple(cur))
            cur = None
    if cur:
        out.append(tuple(cur))
    return out


# ---------------------------------------------------------------------------
# Relation features
# ---------------------------------------------------------------------------
def pair_features(text: str, d: tuple[int, int], e: tuple[int, int], n_drugs: int, n_effects: int) -> list[float]:
    a, b = sorted([d, e])
    between = text[a[1] : b[0]].lower()
    words_between = len(between.split())
    feats = [
        float(words_between),
        float(d[0] < e[0]),
        float(n_drugs),
        float(n_effects),
        float("induced" in text[e[0] - 2 : e[1] + 12].lower() or "induced" in between),
    ]
    feats += [float(c in between.split() or f"{c} " in between) for c in CUES]
    feats.append(float(";" in between or "," in between))
    feats.append(float(" and " in between))
    return feats


# ---------------------------------------------------------------------------
class ADEExtractor:
    def __init__(self, sentence_model=None, vectorizer=None, crf=None, relation_model=None, dict_flags: DictFlags | None = None):
        self.sentence_model = sentence_model
        self.vectorizer = vectorizer
        self.crf = crf
        self.relation_model = relation_model
        self.dict_flags = dict_flags

    def sentence_probability(self, texts: list[str]) -> np.ndarray:
        return self.sentence_model.predict_proba(self.vectorizer.transform(texts))[:, 1]

    def tag(self, text: str) -> list[tuple[str, int, int]]:
        toks = tokenize(text)
        if not toks:
            return []
        dflag, rflag = self.dict_flags.flags(text, toks)
        labels = self.crf.predict_single(token_features(toks, dflag, rflag))
        return spans_from_bio(toks, labels)

    def extract(self, text: str, threshold: float = 0.5) -> dict:
        from vigilix.rag.text import sentences as split_sentences

        out = {"sentences": [], "pairs": []}
        sents = split_sentences(text) or [text]
        probs = self.sentence_probability(sents)
        offset = 0
        for s, p in zip(sents, probs):
            start = text.find(s, offset)
            offset = max(offset, start + len(s)) if start >= 0 else offset
            spans = self.tag(s)
            drugs = [(b, e) for k, b, e in spans if k == "DRUG"]
            effects = [(b, e) for k, b, e in spans if k == "EFFECT"]
            pairs = []
            if drugs and effects and p >= threshold * 0.6:
                for d in drugs:
                    for e in effects:
                        x = np.array([pair_features(s, d, e, len(drugs), len(effects))])
                        rp = float(self.relation_model.predict_proba(x)[0, 1])
                        if rp >= 0.5:
                            pairs.append({"drug": s[d[0] : d[1]], "effect": s[e[0] : e[1]], "probability": round(rp * float(p) ** 0.5, 3)})
            out["sentences"].append(
                {
                    "text": s,
                    "start": start,
                    "ade_probability": round(float(p), 3),
                    "spans": [{"type": k, "text": s[b:e], "start": b, "end": e} for k, b, e in spans],
                    "pairs": pairs,
                }
            )
            out["pairs"].extend(pairs)
        return out

    def save(self, path: Path | None = None) -> None:
        path = path or SETTINGS.paths.artifacts / "ade_extractor.pkl"
        path.write_bytes(pickle.dumps({"sentence_model": self.sentence_model, "vectorizer": self.vectorizer, "crf": self.crf, "relation_model": self.relation_model}))

    @classmethod
    def load(cls, drugs, reactions, path: Path | None = None) -> "ADEExtractor":
        path = path or SETTINGS.paths.artifacts / "ade_extractor.pkl"
        d = pickle.loads(path.read_bytes())
        return cls(d["sentence_model"], d["vectorizer"], d["crf"], d["relation_model"], DictFlags(drugs, reactions))


# ---------------------------------------------------------------------------
def _span_prf(gold: list[set], pred: list[set]) -> dict:
    tp = sum(len(g & p) for g, p in zip(gold, pred))
    fp = sum(len(p - g) for g, p in zip(gold, pred))
    fn = sum(len(g - p) for g, p in zip(gold, pred))
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3), "support": tp + fn}


def _span_prf_lenient(gold: list[set], pred: list[set]) -> dict:
    """Overlap matching: a predicted span counts if it overlaps a gold span of the same sentence."""

    def ov(a, b):
        return a[0] < b[1] and b[0] < a[1]

    tp_p = sum(sum(1 for p in P if any(ov(p, g) for g in G)) for G, P in zip(gold, pred))
    n_p = sum(len(P) for P in pred)
    tp_g = sum(sum(1 for g in G if any(ov(p, g) for p in P)) for G, P in zip(gold, pred))
    n_g = sum(len(G) for G in gold)
    prec = tp_p / n_p if n_p else 0.0
    rec = tp_g / n_g if n_g else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3), "support": n_g}


def train_and_evaluate(verbose: bool = True) -> dict:
    import sklearn_crfsuite
    from scipy.sparse import hstack
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
    from sklearn.pipeline import FeatureUnion

    from vigilix.data.sources import load_ade_corpus
    from vigilix.kb.dictionaries import load_dictionaries

    drugs, reactions = load_dictionaries(SETTINGS.paths.processed / "dictionaries.json")
    flags = DictFlags(drugs, reactions)
    sents = load_sentences(load_ade_corpus())
    train, test = split_by_pmid(sents, SETTINGS.random_seed)
    if verbose:
        print(f"  ADE sentences: {len(train)} train, {len(test)} test ({sum(s.positive for s in test)} positive in test)")

    # 1. sentence classifier
    vec = FeatureUnion(
        [
            ("w", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)),
            ("c", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=3, sublinear_tf=True, max_features=150000)),
        ]
    )
    Xtr = vec.fit_transform([s.text for s in train])
    Xte = vec.transform([s.text for s in test])
    ytr = np.array([s.positive for s in train])
    yte = np.array([s.positive for s in test])
    clf = LogisticRegression(max_iter=3000, C=8.0, class_weight="balanced")
    clf.fit(Xtr, ytr)
    pte = clf.predict_proba(Xte)[:, 1]
    sent_metrics = {
        "precision": round(float(precision_score(yte, pte >= 0.5)), 3),
        "recall": round(float(recall_score(yte, pte >= 0.5)), 3),
        "f1": round(float(f1_score(yte, pte >= 0.5)), 3),
        "auroc": round(float(roc_auc_score(yte, pte)), 4),
    }

    # 2. CRF span tagger (trained on positive sentences plus a sample of negatives)
    rng = random.Random(SETTINGS.random_seed)
    # Spans are only annotated inside ADE sentences (drugs in negative sentences
    # are left unlabelled by the corpus design), so the tagger is trained on
    # positive sentences and gated at inference by the sentence classifier.
    tr_crf = [s for s in train if s.positive]

    def feats_labels(s: Sentence):
        toks, labels = bio_labels(s)
        dflag, rflag = flags.flags(s.text, toks)
        return token_features(toks, dflag, rflag), labels, toks

    data_tr = [feats_labels(s) for s in tr_crf]
    crf = sklearn_crfsuite.CRF(algorithm="lbfgs", c1=0.02, c2=0.02, max_iterations=250, all_possible_transitions=True)
    crf.fit([d[0] for d in data_tr], [d[1] for d in data_tr])

    pos_test = [s for s in test if s.positive]
    gold_d, gold_e, pred_d, pred_e, dict_d, dict_e = [], [], [], [], [], []
    gold_pairs, pred_pairs, oracle_pairs, dict_pairs = [], [], [], []
    rel_X, rel_y = [], []
    for s in train:
        if not s.positive:
            continue
        for d in s.drugs:
            for e in s.effects:
                rel_X.append(pair_features(s.text, d, e, len(s.drugs), len(s.effects)))
                rel_y.append(int((d, e) in s.relations))
    rel = LogisticRegression(max_iter=2000, C=1.0)
    rel.fit(np.array(rel_X), np.array(rel_y))
    ext = ADEExtractor(clf, vec, crf, rel, flags)

    for s in pos_test:
        toks = tokenize(s.text)
        dflag, rflag = flags.flags(s.text, toks)
        spans = spans_from_bio(toks, crf.predict_single(token_features(toks, dflag, rflag)))
        pd_ = {(b, e) for k, b, e in spans if k == "DRUG"}
        pe_ = {(b, e) for k, b, e in spans if k == "EFFECT"}
        gold_d.append(set(s.drugs))
        gold_e.append(set(s.effects))
        pred_d.append(pd_)
        pred_e.append(pe_)
        # dictionary baseline
        bd = {(toks[i][1], toks[j][2]) for i, j in _runs(dflag)}
        be = {(toks[i][1], toks[j][2]) for i, j in _runs(rflag)}
        dict_d.append(bd)
        dict_e.append(be)
        gp = set(s.relations)
        pp = set()
        for d in pd_:
            for e in pe_:
                if rel.predict_proba(np.array([pair_features(s.text, d, e, len(pd_), len(pe_))]))[0, 1] >= 0.5:
                    pp.add((d, e))
        gold_pairs.append(gp)
        pred_pairs.append(pp)
        dict_pairs.append({(d, e) for d in bd for e in be})
    # relation classifier with gold entities (isolates relation quality)
    rX, ry = [], []
    for s in pos_test:
        for d in s.drugs:
            for e in s.effects:
                rX.append(pair_features(s.text, d, e, len(s.drugs), len(s.effects)))
                ry.append(int((d, e) in s.relations))
    rpred = rel.predict(np.array(rX))
    relation_gold_entities = {
        "precision": round(float(precision_score(ry, rpred)), 3),
        "recall": round(float(recall_score(ry, rpred)), 3),
        "f1": round(float(f1_score(ry, rpred)), 3),
        "candidate_pairs": len(ry),
        "majority_baseline_f1": round(float(f1_score(ry, np.ones(len(ry)))), 3),
    }
    results = {
        "split": {"train_sentences": len(train), "test_sentences": len(test), "test_positive_sentences": len(pos_test), "test_pmids": len({s.pmid for s in test})},
        "sentence_classification": sent_metrics,
        "drug_spans_crf": _span_prf(gold_d, pred_d),
        "effect_spans_crf": _span_prf(gold_e, pred_e),
        "drug_spans_crf_overlap": _span_prf_lenient(gold_d, pred_d),
        "effect_spans_crf_overlap": _span_prf_lenient(gold_e, pred_e),
        "drug_spans_dictionary": _span_prf(gold_d, dict_d),
        "effect_spans_dictionary": _span_prf(gold_e, dict_e),
        "relations_end_to_end_crf": _span_prf(gold_pairs, pred_pairs),
        "relations_end_to_end_dictionary": _span_prf(gold_pairs, dict_pairs),
        "relations_given_gold_entities": relation_gold_entities,
        "crf_transitions_top": [f"{a} -> {b}: {w:.2f}" for (a, b), w in sorted(crf.transition_features_.items(), key=lambda kv: -kv[1])[:6]],
    }
    ext.save()
    (SETTINGS.paths.reports / "ade_extraction.json").write_text(json.dumps(results, indent=2))
    if verbose:
        print(json.dumps({k: v for k, v in results.items() if k != "crf_transitions_top"}, indent=2))
    return results


def _runs(flags: list[str]) -> list[tuple[int, int]]:
    out, start = [], None
    for i, f in enumerate(flags + ["O"]):
        if f == "B" or f == "O":
            if start is not None:
                out.append((start, i - 1))
                start = None
            if f == "B":
                start = i
    return out


if __name__ == "__main__":
    train_and_evaluate()
