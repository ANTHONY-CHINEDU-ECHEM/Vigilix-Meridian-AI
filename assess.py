"""Case causality assessment: Naranjo scale, WHO UMC categories and case intake.

``intake`` turns a free text case narrative into a structured individual
case safety report draft: identifiers are redacted, adverse events and
suspect drugs are extracted, seriousness, outcome, time to onset,
dechallenge and rechallenge are detected, the four ICSR minimum criteria are
checked, expectedness is looked up in the knowledge graph and the Naranjo
questionnaire is pre filled with answers the narrative supports. Every pre
filled answer carries the text that justified it so a reviewer can accept or
change it; the final judgement always rests with the assessor.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

NARANJO_QUESTIONS = [
    ("previous_reports", "Are there previous conclusive reports on this reaction?", {"yes": 1, "no": 0, "unknown": 0}),
    ("after_drug", "Did the adverse event appear after the suspected drug was administered?", {"yes": 2, "no": -1, "unknown": 0}),
    ("improved_on_stop", "Did the adverse reaction improve when the drug was discontinued or a specific antagonist was administered?", {"yes": 1, "no": 0, "unknown": 0}),
    ("reappeared_on_rechallenge", "Did the adverse reaction reappear when the drug was readministered?", {"yes": 2, "no": -1, "unknown": 0}),
    ("alternative_causes", "Are there alternative causes (other than the drug) that could on their own have caused the reaction?", {"yes": -1, "no": 2, "unknown": 0}),
    ("placebo_reaction", "Did the reaction reappear when a placebo was given?", {"yes": -1, "no": 1, "unknown": 0}),
    ("toxic_concentration", "Was the drug detected in blood or other fluids in concentrations known to be toxic?", {"yes": 1, "no": 0, "unknown": 0}),
    ("dose_response", "Was the reaction more severe when the dose was increased or less severe when the dose was decreased?", {"yes": 1, "no": 0, "unknown": 0}),
    ("previous_similar", "Did the patient have a similar reaction to the same or similar drugs in any previous exposure?", {"yes": 1, "no": 0, "unknown": 0}),
    ("objective_evidence", "Was the adverse event confirmed by any objective evidence?", {"yes": 1, "no": 0, "unknown": 0}),
]


def naranjo(answers: dict[str, str]) -> dict:
    total = 0
    detail = []
    for key, question, points in NARANJO_QUESTIONS:
        a = (answers.get(key) or "unknown").lower()
        a = a if a in points else "unknown"
        total += points[a]
        detail.append({"key": key, "question": question, "answer": a, "points": points[a]})
    category = "definite" if total >= 9 else "probable" if total >= 5 else "possible" if total >= 1 else "doubtful"
    return {"score": total, "category": category, "items": detail}


def who_umc(time_plausible: str, other_explanation: str, dechallenge: str, rechallenge: str, known_reaction: str, sufficient_information: bool = True) -> dict:
    """Map structured answers onto the WHO UMC causality categories.

    Answers are "yes", "no" or "unknown". The mapping follows the published
    criteria; borderline cases are labelled with the reason so the assessor
    can override them.
    """
    if not sufficient_information:
        return {"category": "unassessable", "reason": "information is insufficient or contradictory and cannot be supplemented"}
    if time_plausible == "no":
        return {"category": "unlikely", "reason": "the time relationship makes a causal relationship improbable"}
    if time_plausible == "yes" and other_explanation == "no" and dechallenge == "yes" and rechallenge == "yes" and known_reaction == "yes":
        return {"category": "certain", "reason": "plausible timing, no alternative explanation, positive dechallenge and rechallenge, recognised reaction"}
    if time_plausible == "yes" and other_explanation == "no" and dechallenge == "yes":
        return {"category": "probable", "reason": "reasonable timing, unlikely alternative explanation and clinically reasonable response to withdrawal"}
    if time_plausible == "yes" and other_explanation in ("yes", "unknown"):
        if dechallenge == "unknown" and other_explanation == "unknown":
            return {"category": "conditional", "reason": "more data are needed for a proper assessment (dechallenge and alternative causes not documented)"}
        return {"category": "possible", "reason": "reasonable timing but disease or other drugs could also explain the event"}
    if time_plausible == "yes" and other_explanation == "no" and dechallenge in ("no", "unknown"):
        return {"category": "possible", "reason": "reasonable timing and no alternative explanation, but withdrawal information is lacking or negative"}
    return {"category": "conditional", "reason": "more data are needed for a proper assessment"}


# ---------------------------------------------------------------------------
# Narrative parsing
# ---------------------------------------------------------------------------
SERIOUS = {
    "death": r"\b(died|death|fatal|deceased|passed away)\b",
    "life_threatening": r"\b(life[- ]threatening|cardiac arrest|resuscitat\w+|intubat\w+|anaphylactic shock)\b",
    "hospitalisation": r"\b(hospitali[sz]\w*|admitted|admission|intensive care|icu|emergency department|prolonged (?:stay|hospital))\b",
    "disability": r"\b(disabilit\w+|incapacit\w+|permanent(?:ly)? (?:damage|impair\w+)|persistent (?:weakness|neuropathy))\b",
    "congenital_anomaly": r"\b(congenital|birth defect|malformation|neural tube)\b",
    "medically_important": r"\b(seizure|stevens[- ]johnson|toxic epidermal necrolysis|agranulocytosis|liver failure|torsade|ventricular fibrillation|suicid\w+)\b",
}
OUTCOME = {
    "recovered": r"\b(recovered|resolved|returned to normal|normali[sz]ed|full recovery)\b",
    "recovering": r"\b(improv\w+|recovering|resolving|subsided|abated)\b",
    "not_recovered": r"\b(persist\w+|ongoing|not recovered|no improvement|worsened)\b",
    "fatal": r"\b(died|death|fatal)\b",
    "sequelae": r"\b(sequelae|residual|permanent)\b",
}
DECHALLENGE_POS = re.compile(r"\b(resolved|improved|subsided|disappeared|recovered|abated|normali[sz]ed)\b[^.]{0,80}\b(after|following|on|upon|within)\b[^.]{0,40}\b(discontinu\w+|withdraw\w+|stopp\w+|cessation|withheld)|\b(discontinu\w+|withdraw\w+|stopp\w+|cessation of)\b[^.]{0,80}\b(resolved|improved|subsided|disappeared|recovered|abated|normali[sz]ed|resolution|improvement)", re.I)
DECHALLENGE_NEG = re.compile(r"\b(persist\w+|did not (?:improve|resolve)|no improvement)\b[^.]{0,60}\b(despite|after|following)\b[^.]{0,40}\b(discontinu\w+|withdraw\w+|stopp\w+)", re.I)
RECHALLENGE_POS = re.compile(r"\b(recurr\w+|reappear\w+|relaps\w+|returned|re[- ]?occur\w+)\b[^.]{0,80}\b(re[- ]?challeng\w+|re[- ]?introduc\w+|re[- ]?start\w+|re[- ]?administ\w+|re[- ]?exposure|resum\w+)|\b(re[- ]?challeng\w+|re[- ]?introduc\w+|re[- ]?start\w+|re[- ]?administ\w+|resum\w+)\b[^.]{0,80}\b(recurr\w+|reappear\w+|relaps\w+|returned|re[- ]?occur\w+)", re.I)
RECHALLENGE_NEG = re.compile(r"\b(re[- ]?challeng\w+|re[- ]?introduc\w+|re[- ]?start\w+|resum\w+)\b[^.]{0,80}\b(without (?:recurrence|reappearance)|no recurrence|tolerated)", re.I)
ONSET = re.compile(r"\b(?:after|within|following|about|approximately|on day)\s+(\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|twelve|several|a few)\s*(minutes?|hours?|days?|weeks?|months?|years?)\b|\b(\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|twelve|several|a few)\s*(minutes?|hours?|days?|weeks?|months?|years?)\s+(?:later|after (?:starting|initiation|the first dose|commencing))\b", re.I)
WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "several": 3, "a few": 3}
REPORTER = re.compile(r"\b(i am a|as a|reported by|reporter|the (?:treating|attending) (?:physician|doctor|nurse|pharmacist)|our patient|we (?:report|describe|present)|physician|pharmacist|nurse|doctor|gp)\b", re.I)
PATIENT = re.compile(r"\b(\d{1,3}[- ]?(?:year|yr|month|week|day)s?[- ]old|aged? \d+|man|woman|male|female|boy|girl|infant|patient|child|he|she)\b", re.I)
OBJECTIVE = re.compile(r"\b(biopsy|ecg|electrocardiogram|qtc|creatine kinase|ck|alt|ast|bilirubin|inr|level of|concentration|serum|plasma|imaging|mri|ct scan|x[- ]ray|blood count|platelet|neutrophil|eosinophil|creatinine|troponin|culture)\b", re.I)
ALTERNATIVE = re.compile(r"\b(alternative (?:cause|explanation)|could also be explained|underlying|pre[- ]existing|history of|concomitant|co[- ]?medication|also (?:taking|receiving)|viral|infection|sepsis)\b", re.I)


def _onset_days(text: str) -> list[dict]:
    out = []
    for m in ONSET.finditer(text):
        n = (m.group(1) or m.group(3)).lower()
        unit_raw = m.group(2) or m.group(4)
        val = float(WORDNUM.get(n, n)) if not n.replace(".", "").isdigit() else float(n)
        unit = unit_raw.lower().rstrip("s")
        days = val * {"minute": 1 / 1440, "hour": 1 / 24, "day": 1, "week": 7, "month": 30.4, "year": 365}[unit]
        out.append({"text": m.group(0), "days": round(days, 3)})
    return out


def _find(pat: str | re.Pattern, text: str) -> str | None:
    m = re.search(pat, text, re.I) if isinstance(pat, str) else pat.search(text)
    return m.group(0) if m else None


def intake(narrative: str, extractor, graph, drugs_dict, reactions_dict) -> dict:
    from vigilix.rag.guard import redact
    from vigilix.rag.text import canonical_drug, canonical_term

    red, redactions = redact(narrative)
    ext = extractor.extract(red) if extractor is not None else {"pairs": [], "sentences": []}
    # entity sets: extractor spans, then dictionary links as a safety net
    ext_drugs = [canonical_drug(p["drug"]) for p in ext["pairs"]]
    def norm_event(phrase: str) -> str:
        """Map an extracted effect phrase onto the reaction dictionary where possible."""
        base = re.sub(r"^(?:severe|mild|moderate|acute|chronic|serious|marked|significant|progressive|fatal|life[- ]threatening)\s+", "", phrase.strip().lower())
        c = canonical_term(base)
        if c in reactions_dict.entries:
            return c
        hit = reactions_dict.lookup(base)
        if hit is not None:
            return hit.canonical
        found = reactions_dict.mentions(base)
        return found[0] if len(found) == 1 else c

    ext_rx = [norm_event(p["effect"]) for p in ext["pairs"]]
    span_drugs = [canonical_drug(sp["text"]) for s in ext["sentences"] for sp in s["spans"] if sp["type"] == "DRUG"]
    span_rx = [norm_event(sp["text"]) for s in ext["sentences"] for sp in s["spans"] if sp["type"] == "EFFECT"]
    dict_drugs = drugs_dict.mentions(red)
    dict_rx = reactions_dict.mentions(red)
    suspects = list(dict.fromkeys(ext_drugs + span_drugs + dict_drugs))
    indications = {canonical_term(m.group(1)) for m in re.finditer(r"\b(?:for|treatment of|treat|indicated for|prescribed for)\s+(?:an?\s+|her\s+|his\s+)?([a-z][a-z ]{2,40}?)(?=[,.;)]|\s+(?:and|with|was|which))", red, re.I)}
    events = [
        r
        for r in dict.fromkeys(ext_rx + span_rx + dict_rx)
        if r not in {"reaction", "infusion"} and r not in indications and r not in suspects and len(r) > 3 and (r in reactions_dict.entries or len(r.split()) > 1)
    ]

    seriousness = {k: _find(v, red) for k, v in SERIOUS.items()}
    serious = any(seriousness.values())
    outcome = next((k for k, v in OUTCOME.items() if re.search(v, red, re.I)), "unknown")
    if seriousness.get("death"):
        outcome = "fatal"
    dech_pos, dech_neg = _find(DECHALLENGE_POS, red), _find(DECHALLENGE_NEG, red)
    rech_pos, rech_neg = _find(RECHALLENGE_POS, red), _find(RECHALLENGE_NEG, red)
    onset = _onset_days(red)
    objective = _find(OBJECTIVE, red)
    alternative = _find(ALTERNATIVE, red)

    assessments = []
    for d in suspects[:4]:
        for r in events[:4]:
            ev = graph.pair_evidence(d, r)
            rel = ev["relations"]
            labelled = "labelled_reaction" in rel
            literature = bool({"case_reported", "literature_induced"} & set(rel))
            faers = rel.get("faers_signal")
            answers = {
                "previous_reports": "yes" if (labelled or literature) else "unknown",
                "after_drug": "yes" if onset or re.search(r"\b(after|following|since starting|on starting|commenced|initiated)\b", red, re.I) else "unknown",
                "improved_on_stop": "yes" if dech_pos else ("no" if dech_neg else "unknown"),
                "reappeared_on_rechallenge": "yes" if rech_pos else ("no" if rech_neg else "unknown"),
                "alternative_causes": "yes" if alternative else "unknown",
                "placebo_reaction": "unknown",
                "toxic_concentration": "yes" if re.search(r"\b(toxic (?:level|concentration)|supratherapeutic|elevated (?:serum|plasma) (?:level|concentration))\b", red, re.I) else "unknown",
                "dose_response": "yes" if re.search(r"\b(dose[- ](?:dependent|related)|after (?:the )?dose (?:was )?(?:increase|reduc)\w*)\b", red, re.I) else "unknown",
                "previous_similar": "yes" if re.search(r"\b(previous(?:ly)?|prior)\b[^.]{0,40}\b(similar|same) (?:reaction|episode)\b", red, re.I) else "unknown",
                "objective_evidence": "yes" if objective else "unknown",
            }
            justification = {
                "previous_reports": ", ".join(REL for REL in ("labelled_reaction", "case_reported", "literature_induced") if REL in rel) or None,
                "after_drug": onset[0]["text"] if onset else None,
                "improved_on_stop": dech_pos or dech_neg,
                "reappeared_on_rechallenge": rech_pos or rech_neg,
                "alternative_causes": alternative,
                "objective_evidence": objective,
            }
            n = naranjo(answers)
            w = who_umc(
                "yes" if answers["after_drug"] == "yes" else "unknown",
                "yes" if alternative else "unknown",
                answers["improved_on_stop"],
                answers["reappeared_on_rechallenge"],
                "yes" if labelled else "unknown",
            )
            assessments.append(
                {
                    "drug": d,
                    "reaction": r,
                    "expectedness": "listed" if labelled else "not listed in sources",
                    "label_sources": rel.get("labelled_reaction", {}).get("sources", []),
                    "faers": faers,
                    "literature": {k: rel[k] for k in ("case_reported", "literature_induced") if k in rel},
                    "naranjo": n,
                    "naranjo_answers": answers,
                    "justification": {k: v for k, v in justification.items() if v},
                    "who_umc": w,
                }
            )
    minimum = {
        "identifiable_reporter": bool(REPORTER.search(narrative)),
        "identifiable_patient": bool(PATIENT.search(narrative)),
        "suspect_drug": bool(suspects),
        "adverse_reaction": bool(events),
    }
    return {
        "redacted_narrative": red,
        "redactions": redactions,
        "suspect_drugs": suspects,
        "events": events,
        "extraction": ext,
        "seriousness": {"serious": serious, "criteria": {k: v for k, v in seriousness.items() if v}},
        "outcome": outcome,
        "time_to_onset": onset,
        "dechallenge": "positive" if dech_pos else "negative" if dech_neg else "not reported",
        "rechallenge": "positive" if rech_pos else "negative" if rech_neg else "not reported",
        "icsr_minimum_criteria": minimum,
        "valid_icsr": all(minimum.values()),
        "assessments": assessments,
    }
