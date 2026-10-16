"""Sentence level claim verification with a learned, interpretable model.

For every answer sentence the verifier computes eleven features against
the evidence it cites: content token support, best single sentence support,
bigram support, numeric fidelity, drug and reaction consistency, negation
agreement, citation validity and length. A logistic regression trained on
synthetic perturbations of real corpus sentences (number changes, drug
swaps, reaction swaps, negation flips, wrong citations and topically related
but unsupported sentences) turns them into a support probability. Hard
rules sit on top: any number absent from the cited evidence or any drug the
evidence does not mention marks the sentence as unsupported whatever the
probability, because invented numbers and misattributed drugs are the most
dangerous errors in drug safety.
"""
from __future__ import annotations

import json
import math
import random
import re
from pathlib import Path

import numpy as np

from vigilix.config import SETTINGS
from vigilix.rag.text import analyse, apply_spelling, numbers, raw_tokens, rewrite, sentences


def _spelled(text: str) -> str:
    """Token normalised text (spelling folded, brands mapped) for entity comparisons."""
    return " ".join(rewrite([apply_spelling(t) for t in raw_tokens(text)]))

NEG = re.compile(r"\b(no|not|never|without|none|neither|nor|absence|absent|did not|does not|was not|were not|cannot|unlikely|failed to)\b", re.I)

FEATURES = [
    "token_support",
    "best_sentence_support",
    "bigram_support",
    "numbers_present",
    "numbers_fraction",
    "drug_consistency",
    "reaction_consistency",
    "negation_agreement",
    "citation_valid",
    "log_length",
    "best_sentence_jaccard",
]

_STOP_EXTRA = {"report", "reported", "patient", "includ", "may", "associat"}


def _tok(text: str) -> list[str]:
    return [t for t in analyse(text) if t not in _STOP_EXTRA]


def featurise(claim: str, cited: list[str], drugs_in_claim: list[str], reactions_in_claim: list[str], valid: bool) -> list[float]:
    ct = _tok(claim)
    cset = set(ct)
    evid = " ".join(cited)
    et = set(_tok(evid))
    ebi = set()
    best_rec = best_jac = 0.0
    best_sentence = ""
    for s in sentences(evid) if evid else []:
        st = _tok(s)
        ss = set(st)
        ebi |= set(zip(st, st[1:]))
        if cset:
            rec = len(cset & ss) / len(cset)
            jac = len(cset & ss) / max(len(cset | ss), 1)
            if rec > best_rec:
                best_sentence = s
            best_rec, best_jac = max(best_rec, rec), max(best_jac, jac)
    cbi = set(zip(ct, ct[1:]))
    nums = numbers(claim)
    evid_nums = set(numbers(evid))
    num_frac = sum(1 for n in nums if n in evid_nums) / len(nums) if nums else 1.0
    ev_l = " " + _spelled(evid) + " "
    drug_c = sum(1 for d in drugs_in_claim if f" {_spelled(d)} " in ev_l) / len(drugs_in_claim) if drugs_in_claim else 1.0
    rx_c = sum(1 for r in reactions_in_claim if f" {_spelled(r)} " in ev_l) / len(reactions_in_claim) if reactions_in_claim else 1.0
    # negation must agree with the evidence sentence that best supports the claim
    neg_claim = len(NEG.findall(claim))
    neg_best = len(NEG.findall(best_sentence)) if best_sentence else len(NEG.findall(evid))
    neg_agree = 1.0 if (neg_claim > 0) == (neg_best > 0) and (best_rec < 0.95 or neg_claim == neg_best) else 0.0
    return [
        len(cset & et) / max(len(cset), 1),
        best_rec,
        len(cbi & ebi) / max(len(cbi), 1) if cbi else 1.0,
        float(num_frac == 1.0),
        num_frac,
        drug_c,
        rx_c,
        neg_agree,
        float(valid),
        math.log1p(len(ct)),
        best_jac,
    ]


class Verifier:
    def __init__(self, coef: np.ndarray, intercept: float, mean: np.ndarray, scale: np.ndarray, thresholds=(0.75, 0.45)):
        self.coef = coef
        self.intercept = intercept
        self.mean = mean
        self.scale = scale
        self.supported, self.partial = thresholds

    @classmethod
    def load(cls, path: Path | None = None) -> "Verifier":
        path = path or SETTINGS.paths.artifacts / "verifier.json"
        d = json.loads(path.read_text())
        return cls(np.array(d["coef"]), d["intercept"], np.array(d["mean"]), np.array(d["scale"]), tuple(d["thresholds"]))

    def probability(self, feats: list[float]) -> float:
        x = (np.array(feats) - self.mean) / self.scale
        z = float(x @ self.coef + self.intercept)
        return 1 / (1 + math.exp(-z))

    def verify(self, claim: str, cited: list[str], drugs_dict=None, reactions_dict=None, valid: bool = True) -> dict:
        drugs = drugs_dict.mentions(claim) if drugs_dict is not None else []
        rx = reactions_dict.mentions(claim) if reactions_dict is not None else []
        feats = featurise(claim, cited, drugs, rx, valid)
        p = self.probability(feats) if valid and cited else 0.0
        issues = []
        if feats[3] < 1:
            issues.append("number not found in cited evidence")
        if feats[5] < 1:
            issues.append("drug not mentioned in cited evidence")
        if feats[6] < 1:
            issues.append("reaction not mentioned in cited evidence")
        if feats[7] < 1:
            issues.append("negation not supported")
        if not valid or not cited:
            issues.append("missing or invalid citation")
        if issues and any(i.startswith(("number", "drug", "missing")) for i in issues):
            status = "unsupported"
        elif p >= self.supported:
            status = "supported"
        elif p >= self.partial:
            status = "partial"
        else:
            status = "unsupported"
        return {"status": status, "probability": round(p, 3), "issues": issues, "features": dict(zip(FEATURES, [round(f, 3) for f in feats]))}

    def to_json(self) -> dict:
        return {"features": FEATURES, "coef": self.coef.tolist(), "intercept": self.intercept, "mean": self.mean.tolist(), "scale": self.scale.tolist(), "thresholds": [self.supported, self.partial]}


# ---------------------------------------------------------------------------
# Synthetic training data
# ---------------------------------------------------------------------------
def _perturb_number(s: str, rng: random.Random) -> str | None:
    m = list(re.finditer(r"\b\d+(\.\d+)?\b", s))
    if not m:
        return None
    x = rng.choice(m)
    val = float(x.group(0))
    new = val * rng.choice([1.5, 2.0, 0.5, 3.0]) + rng.choice([0, 1, 7])
    rep = f"{new:.1f}" if "." in x.group(0) else str(int(round(new)))
    if rep == x.group(0):
        rep = str(int(val) + 11)
    return s[: x.start()] + rep + s[x.end() :]


def _swap_entity(s: str, ents: list[str], pool: list[str], rng: random.Random) -> str | None:
    present = [e for e in ents if e in s.lower()]
    if not present:
        return None
    e = rng.choice(present)
    other = rng.choice([p for p in pool if p != e and p not in s.lower()] or [None])
    if not other:
        return None
    return re.sub(re.escape(e), other, s, count=1, flags=re.I)


def _negate(s: str, rng: random.Random) -> str | None:
    if NEG.search(s):
        return re.sub(r"\s{2,}", " ", NEG.sub("", s, count=1))
    past = {" caused ": " did not cause ", " increased ": " did not increase ", " reduced ": " did not reduce ", " improved ": " did not improve "}
    for verb, rep in past.items():
        if verb in s:
            return s.replace(verb, rep, 1)
    for verb in (" was ", " were ", " is ", " are "):
        if verb in s:
            return s.replace(verb, verb.rstrip() + " not ", 1)
    return None


def _paraphrase(s: str, rng: random.Random) -> str:
    words = s.split()
    if len(words) > 12:
        keep = [w for w in words if rng.random() > 0.12 or any(ch.isdigit() for ch in w)]
        return " ".join(keep)
    return s


def build_training(passages: list[dict], drugs_dict, reactions_dict, n: int = 9000, seed: int = 5):
    rng = random.Random(seed)
    pool_d = sorted({d for p in passages for d in p.get("drugs", [])})
    pool_r = sorted({r for p in passages for r in p.get("reactions", [])})
    X, y, kinds = [], [], []
    idx = [i for i, p in enumerate(passages) if p["source_type"] in ("trial_abstract", "drug_label", "guidance_card", "case_report", "cid_abstract", "signal_summary", "kg_fact")]
    for i in rng.sample(idx, min(len(idx), n)):
        p = passages[i]
        sents = [s for s in sentences(p["text"]) if 8 <= len(s.split()) <= 60]
        if not sents:
            continue
        s = rng.choice(sents)
        evid = [p["text"]]
        d_claim = [d for d in p.get("drugs", []) if d in s.lower()]
        r_claim = [r for r in p.get("reactions", []) if r in s.lower()]
        variants = [(s, 1, "verbatim"), (_paraphrase(s, rng), 1, "paraphrase")]
        num = _perturb_number(s, rng)
        if num:
            variants.append((num, 0, "number_change"))
        sw = _swap_entity(s, p.get("drugs", []), pool_d, rng)
        if sw:
            variants.append((sw, 0, "drug_swap"))
        sr = _swap_entity(s, p.get("reactions", []), pool_r, rng)
        if sr:
            variants.append((sr, 0, "reaction_swap"))
        ng = _negate(s, rng)
        if ng and ng != s:
            variants.append((ng, 0, "negation_flip"))
        other = passages[rng.choice(idx)]
        variants.append((s, 0, "wrong_citation"))
        for claim, label, kind in variants:
            ev = [other["text"]] if kind == "wrong_citation" else evid
            dc = drugs_dict.mentions(claim) if kind in ("drug_swap",) else d_claim
            rc = reactions_dict.mentions(claim) if kind in ("reaction_swap",) else r_claim
            X.append(featurise(claim, ev, dc, rc, True))
            y.append(label)
            kinds.append(kind)
    return np.array(X), np.array(y), kinds


def train_verifier(verbose: bool = True) -> dict:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, roc_auc_score

    from vigilix.kb.dictionaries import load_dictionaries
    from vigilix.rag.store import PassageStore

    store = PassageStore.load()
    drugs, reactions = load_dictionaries(SETTINGS.paths.processed / "dictionaries.json")
    X, y, kinds = build_training(store.passages, drugs, reactions)
    rng = np.random.default_rng(SETTINGS.random_seed)
    perm = rng.permutation(len(y))
    cut = int(0.8 * len(y))
    tr, te = perm[:cut], perm[cut:]
    mean, scale = X[tr].mean(0), X[tr].std(0) + 1e-6
    clf = LogisticRegression(max_iter=2000, C=1.0)
    clf.fit((X[tr] - mean) / scale, y[tr])
    prob = clf.predict_proba((X[te] - mean) / scale)[:, 1]
    v = Verifier(clf.coef_[0], float(clf.intercept_[0]), mean, scale)
    # apply the hard rules exactly as in production
    feats_te = X[te]
    hard_fail = (feats_te[:, 3] < 1) | (feats_te[:, 5] < 1)
    pred = np.where(hard_fail, 0, (prob >= v.partial).astype(int))
    kinds_te = [kinds[i] for i in te]
    per_kind = {}
    for k in sorted(set(kinds_te)):
        m = np.array([kk == k for kk in kinds_te])
        per_kind[k] = {"n": int(m.sum()), "accuracy": round(float(accuracy_score(y[te][m], pred[m])), 3)}
    info = {
        "train_examples": int(len(tr)),
        "test_examples": int(len(te)),
        "auroc": round(float(roc_auc_score(y[te], prob)), 4),
        "accuracy_with_rules": round(float(accuracy_score(y[te], pred)), 4),
        "per_perturbation": per_kind,
        "coefficients": dict(zip(FEATURES, [round(float(c), 3) for c in clf.coef_[0]])),
    }
    out = v.to_json() | {"evaluation": info}
    (SETTINGS.paths.artifacts / "verifier.json").write_text(json.dumps(out, indent=2))
    if verbose:
        print(json.dumps(info, indent=2))
    return info


if __name__ == "__main__":
    train_verifier()
