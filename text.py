"""Clinical text normalisation for pharmacovigilance retrieval.

The same rules are ported line for line to ``frontend/src/engine/text.ts`` so
that the browser engine and the Python service index and query identically.
The pipeline is deliberately transparent:

1. Unicode folding, lower casing and splitting on anything that is not a
   letter or digit (hyphens become spaces, so "QT-prolongation" and
   "QT prolongation" match).
2. Multi word phrase rewriting with a longest match first scan over the
   lexicon: brand names and British approved names fold onto the canonical
   generic; abbreviations and lay phrases are expanded while the original
   token is kept, so "SJS" also retrieves "Stevens Johnson syndrome" and
   "muscle pain" also retrieves "myalgia".
3. British to American spelling rules (oedema to edema, haemorrhage to
   hemorrhage) applied inside each token.
4. Stop word removal and a conservative suffix stemmer that never strips
   a token below four characters.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

LEXICON_PATH = Path(__file__).resolve().parent.parent / "kb" / "content" / "lexicon.json"
_SPLIT = re.compile(r"[^a-z0-9]+")
MAX_PHRASE = 5


@lru_cache(maxsize=1)
def lexicon() -> dict:
    return json.loads(LEXICON_PATH.read_text())


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower().replace("≥", " >= ").replace("≤", " <= ")


def raw_tokens(text: str) -> list[str]:
    return [t for t in _SPLIT.split(fold(text)) if t]


def apply_spelling(token: str) -> str:
    """Apply British to American spelling rules inside a token.

    A rule may carry a third element naming a substring that blocks it, so
    "lymphoedema" becomes "lymphedema" while "angioedema" is left intact.
    """
    for rule in lexicon()["spelling_rules"]:
        old, new = rule[0], rule[1]
        if old in token and not (len(rule) > 2 and rule[2] in token):
            token = token.replace(old, new)
    return token


@lru_cache(maxsize=1)
def _phrase_tables() -> tuple[dict, dict]:
    """Return (replace, expand) dictionaries keyed by tuples of spelled tokens."""
    lex = lexicon()
    replace: dict[tuple[str, ...], list[str]] = {}
    expand: dict[tuple[str, ...], list[str]] = {}

    def key(phrase: str) -> tuple[str, ...]:
        return tuple(apply_spelling(t) for t in raw_tokens(phrase))

    for table in ("drug_synonyms", "brands"):
        for src, dst in lex[table].items():
            k = key(src)
            if k:
                replace[k] = [apply_spelling(t) for t in raw_tokens(dst)]
    for table in ("abbreviations", "lay_terms"):
        for src, dst in lex[table].items():
            k = key(src)
            tgt = [apply_spelling(t) for t in raw_tokens(dst)]
            if k and list(k) != tgt:
                expand[k] = tgt
    return replace, expand


def rewrite(tokens: list[str]) -> list[str]:
    """Longest match first phrase rewriting over spelled tokens."""
    replace, expand = _phrase_tables()
    out: list[str] = []
    i = 0
    n = len(tokens)
    while i < n:
        matched = False
        for span in range(min(MAX_PHRASE, n - i), 0, -1):
            k = tuple(tokens[i : i + span])
            if k in replace:
                out.extend(replace[k])
                i += span
                matched = True
                break
            if k in expand:
                out.extend(k)
                out.extend(expand[k])
                i += span
                matched = True
                break
        if not matched:
            out.append(tokens[i])
            i += 1
    return out


@lru_cache(maxsize=1)
def stopwords() -> frozenset[str]:
    return frozenset(lexicon()["stopwords"])


_PROTECTED = frozenset({"qt", "ecg", "inr", "alt", "ast", "ck", "hiv", "covid", "sars", "sjs", "ten", "dress", "nms", "aki", "dili"})


def stem(token: str) -> str:
    if token.isdigit() or len(token) <= 4 or token in _PROTECTED:
        return token
    for suffix, repl, min_len in (
        ("ational", "ate", 8),
        ("ization", "ize", 8),
        ("iveness", "ive", 8),
        ("fulness", "ful", 8),
        ("ousness", "ous", 8),
        ("ities", "ity", 6),
        ("ies", "y", 5),
        ("sses", "ss", 5),
        ("ings", "", 7),
        ("ing", "", 6),
        ("edly", "", 7),
        ("ed", "", 6),
        ("es", "e", 6),
        ("s", "", 5),
    ):
        if token.endswith(suffix) and len(token) >= min_len:
            if suffix == "s" and token.endswith(("ss", "us", "is", "ys")):
                return token
            if suffix == "es" and not token.endswith(("ses", "zes", "ches", "shes", "xes")):
                # "doses" -> "dose", "rates" -> "rate"
                return token[:-1]
            return token[: len(token) - len(suffix)] + repl
    return token


def analyse(text: str, keep_stopwords: bool = False) -> list[str]:
    """Full normalisation used by indexing and querying."""
    toks = [apply_spelling(t) for t in raw_tokens(text)]
    toks = rewrite(toks)
    sw = stopwords()
    out = []
    for t in toks:
        if not keep_stopwords and t in sw:
            continue
        out.append(stem(t))
    return out


def canonical_drug(name: str) -> str:
    """Map a free text drug mention to its canonical generic name (lower case)."""
    toks = [apply_spelling(t) for t in raw_tokens(name)]
    replace, _ = _phrase_tables()
    k = tuple(toks)
    if k in replace:
        return " ".join(replace[k])
    return " ".join(toks)


def canonical_term(name: str) -> str:
    """Normalise a reaction term for dictionary matching (spelling, lay terms)."""
    toks = [apply_spelling(t) for t in raw_tokens(name)]
    _, expand = _phrase_tables()
    k = tuple(toks)
    if k in expand and len(k) > 1:
        return " ".join(expand[k])
    lay = lexicon()["lay_terms"]
    joined = " ".join(toks)
    if joined in lay:
        return " ".join(apply_spelling(t) for t in raw_tokens(lay[joined]))
    return joined


_NUM = re.compile(r"(?<![\w.])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:\s?%)?")


def numbers(text: str) -> list[str]:
    """Numbers as written (used by numeric fidelity checks).

    Thousands separators are removed ("5,248,821" is one number) and every
    value is rendered in a canonical form so "12.50" and "12.5" compare equal.
    """
    vals = []
    for m in _NUM.finditer(text):
        v = m.group(0).replace(",", "").replace(" ", "").rstrip("%")
        try:
            f = float(v)
        except ValueError:
            continue
        vals.append(f"{f:g}")
    return vals


def sentences(text: str) -> list[str]:
    """Light sentence splitter tolerant of abbreviations used in medicine."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9(\[])", text)
    merged: list[str] = []
    for p in parts:
        if merged and (len(p) < 25 or re.search(r"\b(?:vs|e\.g|i\.e|approx|no|fig|ref|et al)\.$", merged[-1], re.I)):
            merged[-1] = merged[-1] + " " + p
        else:
            merged.append(p)
    return merged
