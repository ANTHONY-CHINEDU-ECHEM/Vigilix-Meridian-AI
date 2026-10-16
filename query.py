"""Query understanding: intents, linked drugs and reactions, population flags."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from vigilix.kb.dictionaries import Dictionary, _key
from vigilix.rag.text import analyse, apply_spelling, raw_tokens

INTENTS = ("method", "signal", "interaction", "label", "adverse_effect", "population", "management", "trial", "case", "mechanism", "regulation")

_PATTERNS = {
    "method": r"\b(prr|ror|ebgm|eb05|mgps|bcpnn|information component|proportional reporting|reporting odds|disproportionalit\w*|masking|naranjo|causality|who umc|bradford hill|self controlled|signal detection|data mining|shrinkage|duplicates?|weber effect|notoriety|time to onset|observed versus expected|reference set|meddra|smq)\b",
    "signal": r"\b(faers|signals?|reports?|reported|reporting|spontaneous|yellow card|vigibase|eudravigilance|disproportionat\w*|stand out|data mining|pharmacovigilance)\b",
    "interaction": r"\b(interact\w*|together|combin\w*|co ?administ\w*|concomitant|plus|with an?|and an?|taken with|alongside|cyp\w*|inhibitor|inducer|p glycoprotein)\b",
    "label": r"\b(label\w*|boxed warning|black box|smpc|summary of product characteristics|prescribing information|warnings?|precautions?|listed|section 4\.?8|undesirable effects|contraindicat\w*)\b",
    "adverse_effect": r"\b(cause\w*|induced?|side effects?|adverse|reactions?|toxicit\w*|risk\w*|associated|linked|known|expected|common|safety|harm\w*|problems?|issues?)\b",
    "population": r"\b(pregnan\w*|breast ?feeding|lactation|elderly|older (adults|people|patients)|children|paediatric|pediatric|infants?|neonat\w*|renal impairment|hepatic impairment|kidney disease|under \d+|aged)\b",
    "management": r"\b(manage\w*|monitor\w*|prevent\w*|avoid\w*|treat\w*|what to do|should|stop\w*|switch\w*|reduce\w*|mitigat\w*|screen\w*)\b",
    "trial": r"\b(trials?|randomi[sz]ed|rct|placebo|versus|vs|tolerabilit\w*|discontinu\w*|study|studies)\b",
    "case": r"\b(case reports?|case series|reports? of|patient (developed|presented)|my patient)\b",
    "mechanism": r"\b(mechanism|why|how does|pathophysiolog\w*|because)\b",
    "regulation": r"\b(ich|gvp|mhra|fda|ema|prac|regulator\w*|psur|pbrer|risk management plan|rmp|icsr|e2a|e2b|e2c|seriousness|serious criteria|expedited)\b",
}
_COMPILED = {k: re.compile(v, re.I) for k, v in _PATTERNS.items()}

_POP = {
    "pregnancy": r"\b(pregnan\w*|teratogen\w*|fetal|foetal|congenital)\b",
    "lactation": r"\b(breast ?feeding|lactation)\b",
    "older_adults": r"\b(elderly|older (adults|people|patients)|aged (6[5-9]|[7-9]\d)|geriatric|frail)\b",
    "children": r"\b(children|child|paediatric|pediatric|infants?|neonat\w*|adolescents?|tonsillectomy)\b",
    "renal": r"\b(renal impairment|kidney disease|ckd|egfr|dialysis)\b",
    "hepatic": r"\b(hepatic impairment|cirrhosis|liver disease)\b",
}
_POP_COMPILED = {k: re.compile(v, re.I) for k, v in _POP.items()}

from vigilix.rag.guard import _DOSING  # noqa: E402  single source of truth


@dataclass
class QueryInfo:
    text: str
    tokens: list[str]
    intents: list[str]
    drugs: list[str]
    reactions: list[str]
    populations: list[str]
    dosing_request: bool = False
    drug_mentions: list[str] = field(default_factory=list)

    @property
    def primary_intent(self) -> str:
        return self.intents[0] if self.intents else "adverse_effect"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["primary_intent"] = self.primary_intent
        return d


def _lookup_ngrams(text: str, dictionary: Dictionary, max_n: int = 6) -> list[str]:
    """Exact dictionary lookup over every n gram (catches terms that are not linkable in prose)."""
    toks = [apply_spelling(t) for t in raw_tokens(text)]
    found: list[str] = []
    covered: set[int] = set()
    for n in range(min(max_n, len(toks)), 0, -1):
        for i in range(len(toks) - n + 1):
            if any(j in covered for j in range(i, i + n)):
                continue
            canon = dictionary._index.get(tuple(toks[i : i + n]))
            if canon and (n > 1 or len(toks[i]) >= 4):
                found.append(canon)
                covered.update(range(i, i + n))
    return found


GENERIC_QUERY_TERMS = {
    "drug", "drugs", "patient", "reports", "report", "label", "reaction", "reactions", "adverse reaction", "adverse reactions", "adverse event",
    "adverse events", "side effect", "side effects", "adverse drug reaction", "adverse effect", "risk", "known", "expected",
}
_QUESTION_WORDS = {"does", "can", "is", "are", "what", "which", "why", "how", "when", "should", "will", "could", "my"}


def understand(text: str, drugs: Dictionary, reactions: Dictionary) -> QueryInfo:
    tokens = analyse(text)
    scores = {}
    for name, pat in _COMPILED.items():
        hits = len(pat.findall(text))
        if hits:
            scores[name] = hits
    drug_list = drugs.mentions(text)
    for d in _lookup_ngrams(text, drugs):
        if d not in drug_list and d not in _QUESTION_WORDS:
            drug_list.append(d)
    reaction_list = [r for r in reactions.mentions(text) if r not in GENERIC_QUERY_TERMS]
    for r in _lookup_ngrams(text, reactions):
        if r not in reaction_list and r not in drug_list and r not in GENERIC_QUERY_TERMS:
            reaction_list.append(r)
    # a reaction phrase can contain a drug name ("heparin induced thrombocytopenia"); keep both
    if len(drug_list) >= 2:
        scores["interaction"] = scores.get("interaction", 0) + 2
    if drug_list and reaction_list:
        scores["adverse_effect"] = scores.get("adverse_effect", 0) + 1
    if scores.get("method") and not drug_list:
        scores["method"] += 2
    order = sorted(scores, key=lambda k: (-scores[k], INTENTS.index(k)))
    pops = [k for k, p in _POP_COMPILED.items() if p.search(text)]
    if pops and "population" not in order:
        order.append("population")
    return QueryInfo(
        text=text,
        tokens=tokens,
        intents=order or ["adverse_effect"],
        drugs=drug_list[:6],
        reactions=reaction_list[:8],
        populations=pops,
        dosing_request=bool(_DOSING.search(text)),
    )
