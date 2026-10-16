"""Safety layer: identifier redaction, scope, crisis language, dosing and injection.

Everything a user types passes through ``redact`` before it is logged,
embedded or sent to a language model, so the audit log and the model never
see direct identifiers. Retrieved passages pass through ``neutralise`` so
instruction like text inside a document cannot steer the model.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_TITLE_NAME = re.compile(r"\b(Mr|Mrs|Ms|Miss|Mx|Dr|Prof|Professor|Sir|Dame)\.?\s+([A-Z][a-z'\-]+(?:\s+[A-Z][a-z'\-]+)?)")
_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    (
        "dob",
        re.compile(r"\b(?:DOB|D\.O\.B\.|date of birth|born on)[:\s]*(?:\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\.?\s+\d{4})", re.I),
        "[DOB]",
    ),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[EMAIL]"),
    ("nhs_number", re.compile(r"\b\d{3}[ -]?\d{3}[ -]?\d{4}\b"), "[NHS_NUMBER]"),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[ID_NUMBER]"),
    ("phone", re.compile(r"(?:\+44\s?7\d{3}|\b07\d{3}|\+1[\s-]?\(?\d{3}\)?)[\s-]?\d{3}[\s-]?\d{3,4}\b"), "[PHONE]"),
    ("uk_postcode", re.compile(r"\b(?:[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2})\b"), "[POSTCODE]"),
    ("mrn", re.compile(r"\b(?:MRN|hospital (?:no|number)|patient id|case id|unit number)[:#\s]*[A-Z0-9-]{4,}\b", re.I), "[RECORD_ID]"),
    ("date", re.compile(r"\b(?:\d{1,2}[/.-]\d{1,2}[/.-](?:\d{4}|\d{2})|\d{4}-\d{2}-\d{2})\b"), "[DATE]"),
    (
        "date",
        re.compile(r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}\b", re.I),
        "[DATE]",
    ),
]
_AGE_OVER_89 = re.compile(r"\b(aged?|age)\s+(9\d|1[01]\d)\b", re.I)

_CRISIS = re.compile(
    r"\b(i\s*(?:want|am going|plan|intend)\s+to\s+(?:kill myself|end (?:my|it all)|die|overdose|take an overdose)|"
    r"(?:how many|how much)\s+(?:pills|tablets|paracetamol|acetaminophen|\w+)\s+(?:would|will|does it take to)\s+(?:kill|end)|"
    r"suicid\w*\s+(?:plan|note|tonight)|i(?:'m| am)\s+(?:suicidal|going to hurt myself)|want to hurt myself|self[- ]harm(?:ing)? (?:tonight|now))",
    re.I,
)
_OUT_OF_SCOPE = re.compile(
    r"\b(election|vote for|who should i vote|football|premier league|recipe|stock price|bitcoin|crypto|weather|horoscope|write (?:me )?(?:a )?(?:poem|song|essay)|"
    r"python code|javascript|homework|celebrity|movie|lottery|betting odds)\b",
    re.I,
)
_IN_SCOPE_HINT = re.compile(
    r"\b(drug|medicine|medication|dose|tablet|side effect|adverse|reaction|signal|faers|label|interaction|toxicit|safety|pharmacovigilance|prescrib|vaccine|"
    r"report|causality|naranjo|prr|ror|ebgm|meddra|smpc|warning|contraindicat|overdose|poison|syndrome|injury|bleeding|rash)\w*",
    re.I,
)
_DOSING = re.compile(
    r"\b(what (?:dose|dosage)(?: of [\w ]{1,40})? (?:should|do|can) (?:i|we)|how (?:much|many)(?: [\w ]{1,30})? (?:should|do|can) (?:i|we) (?:give|take|prescribe|use)|"
    r"(?:dose|dosage) for (?:my|this) (?:patient|child|baby|son|daughter)|(?:should|can) (?:i|we) (?:double|increase|halve|reduce) (?:my|the|his|her) dose|"
    r"titrate .{0,30} for (?:my|this) patient|what (?:dose|dosage) (?:to|for) (?:give|prescribe))\b",
    re.I,
)
_INJECTION = re.compile(
    r"(ignore (?:all |any )?(?:previous|prior|above) (?:instructions|prompts?)|disregard (?:the )?(?:system|previous)|you are now|system prompt|"
    r"act as (?:an? )?\w+ (?:that|who)|reveal (?:your|the) (?:prompt|instructions)|<\s*/?\s*(?:system|assistant|user)\s*>|\bassistant:\s|\bsystem:\s)",
    re.I,
)

CRISIS_MESSAGE = (
    "It sounds like you might be going through something very difficult. You do not have to face it alone. "
    "In the United Kingdom you can call Samaritans free on 116 123 at any time, contact NHS 111, or call 999 if you are in immediate danger. "
    "In the United States you can call or text 988. If you have taken an overdose, please seek emergency care now, even if you feel well."
)
SCOPE_MESSAGE = (
    "Vigilix Meridian answers questions about medicine safety: adverse reactions, safety signals, drug labels, interactions and pharmacovigilance methods. "
    "This question appears to be outside that scope."
)
DOSING_MESSAGE = (
    "Vigilix Meridian does not recommend doses for individual patients. Dosing depends on the product, indication, renal and hepatic function, age, weight and "
    "co medication, and should follow the current product information and the advice of the prescriber or a pharmacist. The evidence below may still help."
)


@dataclass
class GuardResult:
    text: str
    redactions: dict[str, int] = field(default_factory=dict)
    crisis: bool = False
    out_of_scope: bool = False
    dosing_request: bool = False
    injection: bool = False

    @property
    def blocked(self) -> bool:
        return self.crisis or self.out_of_scope

    def to_dict(self) -> dict:
        return {
            "redacted_text": self.text,
            "redactions": self.redactions,
            "crisis": self.crisis,
            "out_of_scope": self.out_of_scope,
            "dosing_request": self.dosing_request,
            "injection_neutralised": self.injection,
        }


def redact(text: str) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}

    def sub(name: str, pat: re.Pattern, repl: str, s: str) -> str:
        new, n = pat.subn(repl, s)
        if n:
            counts[name] = counts.get(name, 0) + n
        return new

    out = text
    for name, pat, repl in _PATTERNS:
        out = sub(name, pat, repl, out)
    out, n = _TITLE_NAME.subn(lambda m: f"{m.group(1)} [NAME]", out)
    if n:
        counts["name"] = n
    out, n = _AGE_OVER_89.subn(lambda m: f"{m.group(1)} over 89", out)
    if n:
        counts["age_over_89"] = n
    return out, counts


def check(text: str, has_entities: bool = False) -> GuardResult:
    red, counts = redact(text)
    red, injected = neutralise(red)
    crisis = bool(_CRISIS.search(text))
    oos = bool(_OUT_OF_SCOPE.search(text)) and not (has_entities or _IN_SCOPE_HINT.search(text))
    return GuardResult(red, counts, crisis=crisis, out_of_scope=oos and not crisis, dosing_request=bool(_DOSING.search(text)), injection=injected)


def neutralise(passage_text: str) -> tuple[str, bool]:
    """Remove instruction like text from retrieved content before it reaches the model."""
    new, n = _INJECTION.subn("[instruction like text removed]", passage_text)
    return new, n > 0
