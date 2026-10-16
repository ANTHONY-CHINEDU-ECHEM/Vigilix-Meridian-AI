// Label mining, interaction screening and case intake for the browser engine.
// Ports of vigilix/extraction/labels.py, vigilix/interactions/checker.py and
// vigilix/causality/assess.py (with dictionary extraction in place of the CRF).
import { naranjo, whoUmc } from "./causality";
import { Dictionary } from "./dict";
import { KnowledgeGraph, PD_GROUPS } from "./graph";
import { redact } from "./guard";
import { canonicalDrug, canonicalTerm, fold, rawTokens, sentences } from "./text";

// ------------------------------------------------------------------ labels
const NEGATION_WINDOW = /\b(no|not|without|absence of|did not|was not|were not|no cases of|none of|rule out|ruled out)\b[^.;:]{0,60}$/i;
const GENERIC = new Set(["adverse reaction", "adverse reactions", "adverse event", "adverse events", "reaction", "reactions", "toxicity", "death", "infection", "pain", "disorder", "disorders", "syndrome", "disease", "symptoms", "drug interaction", "overdose"]);
const isHeading = (t: string) => t.endsWith(" disorders") || t.endsWith(" conditions") || ["investigations", "surgical and medical procedures", "social circumstances", "causality", "adrs", "adr", "antiretroviral therapy"].includes(t);

export function extractTerms(text: string, reactions: Dictionary) {
  const toks = rawTokens(text);
  const out: { term: string; negated: boolean }[] = [];
  for (const [c, a] of reactions.link(text)) {
    if (GENERIC.has(c) || isHeading(c)) continue;
    const prefix = toks.slice(Math.max(0, a - 12), a).join(" ");
    out.push({ term: c, negated: NEGATION_WINDOW.test(prefix) });
  }
  return out;
}

export function labelView(l: any, reactions: Dictionary, signalsFor: (drug: string) => any[]) {
  const mined = extractTerms(l.text, reactions);
  const gold = new Set<string>([...l.events.map((e: any) => canonicalTerm(e.pt)), ...l.events.map((e: any) => canonicalTerm(e.mention))]);
  const goldPt = [...new Set<string>(l.events.map((e: any) => canonicalTerm(e.pt)))].sort();
  const pred = new Set(mined.filter((m) => !m.negated).map((m) => m.term));
  const low = l.text.toLowerCase();
  const spans: any[] = [];
  let cursor = 0;
  for (const m of mined) {
    const syns = [...(reactions.entries[m.term]?.synonyms || [m.term])].sort((a: string, b: string) => b.length - a.length);
    for (const syn of syns) {
      let i = low.indexOf(syn, cursor);
      if (i < 0) i = low.indexOf(syn);
      if (i >= 0) {
        spans.push({ start: i, end: i + syn.length, term: m.term, negated: m.negated, gold: gold.has(m.term) });
        cursor = i + syn.length;
        break;
      }
    }
  }
  const conc: any[] = [];
  if (l.substance) {
    const rows = signalsFor(canonicalDrug(l.substance));
    for (const t of [...pred].sort()) {
      const hit = rows.find((r) => canonicalTerm(r.pt) === t);
      if (hit) conc.push({ term: t, cases: hit.a, eb05: hit.eb05, signal: hit.eb_signal });
    }
  }
  const tp = [...pred].filter((t) => gold.has(t)).length;
  return {
    doc_id: l.doc_id, region: l.region, section: l.section, substance: l.substance, brand: l.brand, label_id: l.label_id,
    text: l.text, spans, gold_terms: goldPt, mined_terms: [...pred].sort(),
    missed: goldPt.filter((t) => !pred.has(t)), extra: [...pred].filter((t) => !gold.has(t)).sort(),
    precision: pred.size ? Math.round((1000 * tp) / pred.size) / 1000 : null,
    recall: goldPt.length ? Math.round((1000 * goldPt.filter((t) => pred.has(t)).length) / goldPt.length) / 1000 : null,
    faers_concordance: conc,
  };
}

// ------------------------------------------------------------------ interactions
const HIGH_RISK = new Set(["QT prolongation", "Bleeding", "Serotonin toxicity", "CNS and respiratory depression", "Hyperkalaemia", "Myelosuppression", "Nephrotoxicity"]);

export function pkMechanisms(a: string, b: string, pk: Record<string, Record<string, string[]>>) {
  const out: any[] = [];
  for (const [mech, roles] of Object.entries(pk)) {
    for (const [x, y] of [[a, b], [b, a]]) {
      const has = (role: string, d: string) => (roles[role] || []).includes(d);
      const sens = has("sensitive_substrates", y) || has("narrow_index_substrates", y);
      const narrow = has("narrow_index_substrates", y);
      if (has("strong_inhibitors", x) && sens) out.push({ mechanism: mech, perpetrator: x, victim: y, effect: `${x} is a strong ${mech} inhibitor and may markedly increase exposure to ${y}`, strength: narrow ? 4 : 3 });
      else if ((has("moderate_inhibitors", x) || has("inhibitors", x)) && sens) out.push({ mechanism: mech, perpetrator: x, victim: y, effect: `${x} inhibits ${mech} and may increase exposure to ${y}`, strength: narrow ? 3 : 2 });
      if ((has("strong_inducers", x) || has("inducers", x)) && sens) out.push({ mechanism: mech, perpetrator: x, victim: y, effect: `${x} induces ${mech} and may reduce exposure to ${y}, risking loss of effect`, strength: 3 });
      else if (has("moderate_inducers", x) && sens) out.push({ mechanism: mech, perpetrator: x, victim: y, effect: `${x} is a moderate ${mech} inducer and may reduce exposure to ${y}`, strength: 2 });
      if (has("prodrugs", y) && (has("strong_inhibitors", x) || has("moderate_inhibitors", x))) out.push({ mechanism: mech, perpetrator: x, victim: y, effect: `${y} needs ${mech} activation; ${x} may reduce its active metabolite and effect`, strength: 2 });
      if (has("reducers", x) && has("renally_cleared_narrow_index", y)) out.push({ mechanism: mech, perpetrator: x, victim: y, effect: `${x} can reduce renal clearance of ${y}, a renally cleared drug with a narrow therapeutic index`, strength: 2 });
    }
  }
  return out;
}

export function checkRegimen(drugs: string[], graph: KnowledgeGraph, pk: any, ddi: Record<string, any[]>) {
  const canon: string[] = [];
  for (const d of drugs) {
    const c = canonicalDrug(d);
    if (c && !canon.includes(c)) canon.push(c);
  }
  const pairs: any[] = [];
  for (let i = 0; i < canon.length; i++)
    for (let j = i + 1; j < canon.length; j++) {
      const [a, b] = [canon[i], canon[j]];
      const g = graph.interaction(a, b);
      const docs = ddi[[a, b].sort().join("|")] || [];
      const mech = pkMechanisms(a, b, pk);
      let score = 0;
      const reasons: string[] = [];
      if (docs.length || g.documented.length) {
        const types = [...new Set([...docs.map((d) => d.type), ...g.documented.flatMap((d: any) => d.types)])].sort();
        score += types.some((t) => ["mechanism", "effect", "advise"].includes(t)) ? 2 : 1;
        reasons.push(`documented interaction (${(types.length ? types : ["int"]).join(", ")})`);
      }
      if (mech.length) {
        score += Math.max(...mech.map((m) => m.strength));
        reasons.push(`pharmacokinetic mechanism (${[...new Set(mech.map((m) => m.mechanism))].sort().join(", ")})`);
      }
      if (g.shared_risk_groups.length) {
        score += Math.min(3, g.shared_risk_groups.reduce((s: number, x: any) => s + (HIGH_RISK.has(x.group) ? 2 : 1), 0));
        reasons.push(`shared risk groups (${g.shared_risk_groups.map((x: any) => x.group).join(", ")})`);
      }
      const level = score >= 5 ? "major" : score >= 3 ? "moderate" : score >= 1 ? "minor" : "none found";
      pairs.push({ drugs: [a, b], level, score, reasons, documented: docs, pharmacokinetic: mech, pharmacodynamic: g.shared_risk_groups, shared_classes: g.shared_classes, known: g.known });
    }
  const order: Record<string, number> = { major: 0, moderate: 1, minor: 2, "none found": 3 };
  pairs.sort((x, y) => order[x.level] - order[y.level] || y.score - x.score);
  const burden: Record<string, string[]> = {};
  for (const d of canon) {
    const rx = new Set(graph.reactionsOf(d, "labelled_reaction").map((e) => e.dst.split(":").slice(1).join(":")));
    for (const [group, terms] of Object.entries(PD_GROUPS)) if (terms.some((t) => rx.has(t))) (burden[group] ||= []).push(d);
  }
  const cumulative = Object.entries(burden)
    .filter(([, ds]) => ds.length >= 2)
    .map(([group, ds]) => ({ group, drugs: ds, high_risk: HIGH_RISK.has(group) }))
    .sort((x, y) => Number(y.high_risk) - Number(x.high_risk) || y.drugs.length - x.drugs.length);
  return {
    drugs: canon,
    unknown: canon.filter((d) => !graph.nodes.has(`drug:${d}`)),
    pairs,
    cumulative_burden: cumulative,
    summary: Object.fromEntries(Object.keys(order).map((l) => [l, pairs.filter((p) => p.level === l).length])),
    disclaimer: "Heuristic triage from public sources. Always confirm with a full interaction reference and the product information.",
  };
}

// ------------------------------------------------------------------ case intake
const SERIOUS: Record<string, RegExp> = {
  death: /\b(died|death|fatal|deceased|passed away)\b/i,
  life_threatening: /\b(life[- ]threatening|cardiac arrest|resuscitat\w+|intubat\w+|anaphylactic shock)\b/i,
  hospitalisation: /\b(hospitali[sz]\w*|admitted|admission|intensive care|icu|emergency department|prolonged (?:stay|hospital))\b/i,
  disability: /\b(disabilit\w+|incapacit\w+|permanent(?:ly)? (?:damage|impair\w+)|persistent (?:weakness|neuropathy))\b/i,
  congenital_anomaly: /\b(congenital|birth defect|malformation|neural tube)\b/i,
  medically_important: /\b(seizure|stevens[- ]johnson|toxic epidermal necrolysis|agranulocytosis|liver failure|torsade|ventricular fibrillation|suicid\w+)\b/i,
};
const OUTCOME: [string, RegExp][] = [
  ["recovered", /\b(recovered|resolved|returned to normal|normali[sz]ed|full recovery)\b/i],
  ["recovering", /\b(improv\w+|recovering|resolving|subsided|abated)\b/i],
  ["not_recovered", /\b(persist\w+|ongoing|not recovered|no improvement|worsened)\b/i],
  ["fatal", /\b(died|death|fatal)\b/i],
  ["sequelae", /\b(sequelae|residual|permanent)\b/i],
];
const DECH_POS = /\b(resolved|improved|subsided|disappeared|recovered|abated|normali[sz]ed)\b[^.]{0,80}\b(after|following|on|upon|within)\b[^.]{0,40}\b(discontinu\w+|withdraw\w+|stopp\w+|cessation|withheld)|\b(discontinu\w+|withdraw\w+|stopp\w+|cessation of)\b[^.]{0,80}\b(resolved|improved|subsided|disappeared|recovered|abated|normali[sz]ed|resolution|improvement)/i;
const DECH_NEG = /\b(persist\w+|did not (?:improve|resolve)|no improvement)\b[^.]{0,60}\b(despite|after|following)\b[^.]{0,40}\b(discontinu\w+|withdraw\w+|stopp\w+)/i;
const RECH_POS = /\b(recurr\w+|reappear\w+|relaps\w+|returned|re[- ]?occur\w+)\b[^.]{0,80}\b(re[- ]?challeng\w+|re[- ]?introduc\w+|re[- ]?start\w+|re[- ]?administ\w+|re[- ]?exposure|resum\w+)|\b(re[- ]?challeng\w+|re[- ]?introduc\w+|re[- ]?start\w+|re[- ]?administ\w+|resum\w+)\b[^.]{0,80}\b(recurr\w+|reappear\w+|relaps\w+|returned|re[- ]?occur\w+)/i;
const RECH_NEG = /\b(re[- ]?challeng\w+|re[- ]?introduc\w+|re[- ]?start\w+|resum\w+)\b[^.]{0,80}\b(without (?:recurrence|reappearance)|no recurrence|tolerated)/i;
const NUMW = "(\\d+(?:\\.\\d+)?|one|two|three|four|five|six|seven|eight|nine|ten|twelve|several|a few)";
const UNIT = "(minutes?|hours?|days?|weeks?|months?|years?)";
const ONSET = new RegExp(`\\b(?:after|within|following|about|approximately|on day)\\s+${NUMW}\\s*${UNIT}\\b|\\b${NUMW}\\s*${UNIT}\\s+(?:later|after (?:starting|initiation|the first dose|commencing))\\b`, "gi");
const WORDNUM: Record<string, number> = { one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, twelve: 12, several: 3, "a few": 3 };
const REPORTER = /\b(i am a|as a|reported by|reporter|the (?:treating|attending) (?:physician|doctor|nurse|pharmacist)|our patient|we (?:report|describe|present)|physician|pharmacist|nurse|doctor|gp)\b/i;
const PATIENT = /\b(\d{1,3}[- ]?(?:year|yr|month|week|day)s?[- ]old|aged? \d+|man|woman|male|female|boy|girl|infant|patient|child|he|she)\b/i;
const OBJECTIVE = /\b(biopsy|ecg|electrocardiogram|qtc|creatine kinase|ck|alt|ast|bilirubin|inr|level of|concentration|serum|plasma|imaging|mri|ct scan|x[- ]ray|blood count|platelet|neutrophil|eosinophil|creatinine|troponin|culture)\b/i;
const ALTERNATIVE = /\b(alternative (?:cause|explanation)|could also be explained|underlying|pre[- ]existing|history of|concomitant|co[- ]?medication|also (?:taking|receiving)|viral|infection|sepsis)\b/i;
const UNITDAYS: Record<string, number> = { minute: 1 / 1440, hour: 1 / 24, day: 1, week: 7, month: 30.4, year: 365 };

function charSpans(text: string, dict: Dictionary, type: string) {
  // map token positions of the linker onto character offsets
  const folded = fold(text);
  const pos: [number, number][] = [];
  for (const m of folded.matchAll(/[a-z0-9]+/g)) pos.push([m.index!, m.index! + m[0].length]);
  return dict.link(text).map(([c, a, b]) => ({ type, text: text.slice(pos[a][0], pos[b - 1][1]), start: pos[a][0], end: pos[b - 1][1], canonical: c }));
}

export function intake(narrative: string, graph: KnowledgeGraph, drugs: Dictionary, reactions: Dictionary) {
  const [red, redactions] = redact(narrative);
  const sents = sentences(red);
  let offset = 0;
  const extSentences: any[] = [];
  const indications = new Set<string>();
  for (const m of red.matchAll(/\b(?:for|treatment of|treat|indicated for|prescribed for)\s+(?:an?\s+|her\s+|his\s+)?([a-z][a-z ]{2,40}?)(?=[,.;)]|\s+(?:and|with|was|which))/gi)) indications.add(canonicalTerm(m[1]));
  const suspects: string[] = [];
  const events: string[] = [];
  for (const s of sents) {
    const start = red.indexOf(s, offset);
    offset = start >= 0 ? start + s.length : offset;
    const ds = charSpans(s, drugs, "DRUG");
    const rs = charSpans(s, reactions, "EFFECT").filter((x) => !["reaction", "infusion"].includes(x.canonical) && !indications.has(x.canonical) && !ds.some((d) => d.canonical === x.canonical));
    ds.forEach((d) => !suspects.includes(d.canonical) && suspects.push(d.canonical));
    rs.forEach((r) => !events.includes(r.canonical) && events.push(r.canonical));
    extSentences.push({ text: s, start, ade_probability: null, spans: [...ds, ...rs].map(({ canonical, ...x }) => x), pairs: [] });
  }
  const find = (re: RegExp) => red.match(re)?.[0] || null;
  const seriousness = Object.fromEntries(Object.entries(SERIOUS).map(([k, re]) => [k, find(re)]).filter(([, v]) => v));
  let outcome = OUTCOME.find(([, re]) => re.test(red))?.[0] || "unknown";
  if (seriousness.death) outcome = "fatal";
  const dechPos = find(DECH_POS),
    dechNeg = find(DECH_NEG),
    rechPos = find(RECH_POS),
    rechNeg = find(RECH_NEG);
  const onset = [...red.matchAll(ONSET)].map((m) => {
    const n = (m[1] || m[3]).toLowerCase();
    const unit = (m[2] || m[4]).toLowerCase().replace(/s$/, "");
    const v = WORDNUM[n] ?? Number(n);
    return { text: m[0], days: Math.round(v * UNITDAYS[unit] * 1000) / 1000 };
  });
  const objective = find(OBJECTIVE),
    alternative = find(ALTERNATIVE);
  const assessments: any[] = [];
  for (const d of suspects.slice(0, 4))
    for (const r of events.slice(0, 4)) {
      const rel = graph.pairEvidence(d, r).relations;
      const labelled = !!rel.labelled_reaction;
      const lit = !!(rel.case_reported || rel.literature_induced);
      const answers: Record<string, string> = {
        previous_reports: labelled || lit ? "yes" : "unknown",
        after_drug: onset.length || /\b(after|following|since starting|on starting|commenced|initiated)\b/i.test(red) ? "yes" : "unknown",
        improved_on_stop: dechPos ? "yes" : dechNeg ? "no" : "unknown",
        reappeared_on_rechallenge: rechPos ? "yes" : rechNeg ? "no" : "unknown",
        alternative_causes: alternative ? "yes" : "unknown",
        placebo_reaction: "unknown",
        toxic_concentration: /\b(toxic (?:level|concentration)|supratherapeutic|elevated (?:serum|plasma) (?:level|concentration))\b/i.test(red) ? "yes" : "unknown",
        dose_response: /\b(dose[- ](?:dependent|related)|after (?:the )?dose (?:was )?(?:increase|reduc)\w*)\b/i.test(red) ? "yes" : "unknown",
        previous_similar: /\b(previous(?:ly)?|prior)\b[^.]{0,40}\b(similar|same) (?:reaction|episode)\b/i.test(red) ? "yes" : "unknown",
        objective_evidence: objective ? "yes" : "unknown",
      };
      const justification: Record<string, string> = {};
      const prev = ["labelled_reaction", "case_reported", "literature_induced"].filter((k) => rel[k]).join(", ");
      if (prev) justification.previous_reports = prev;
      if (onset[0]) justification.after_drug = onset[0].text;
      if (dechPos || dechNeg) justification.improved_on_stop = (dechPos || dechNeg)!;
      if (rechPos || rechNeg) justification.reappeared_on_rechallenge = (rechPos || rechNeg)!;
      if (alternative) justification.alternative_causes = alternative;
      if (objective) justification.objective_evidence = objective;
      assessments.push({
        drug: d, reaction: r,
        expectedness: labelled ? "listed" : "not listed in sources",
        label_sources: rel.labelled_reaction?.sources || [],
        faers: rel.faers_signal || null,
        literature: Object.fromEntries(["case_reported", "literature_induced"].filter((k) => rel[k]).map((k) => [k, rel[k]])),
        naranjo: naranjo(answers), naranjo_answers: answers, justification,
        who_umc: whoUmc(answers.after_drug === "yes" ? "yes" : "unknown", alternative ? "yes" : "unknown", answers.improved_on_stop, answers.reappeared_on_rechallenge, labelled ? "yes" : "unknown"),
      });
    }
  const minimum = { identifiable_reporter: REPORTER.test(narrative), identifiable_patient: PATIENT.test(narrative), suspect_drug: suspects.length > 0, adverse_reaction: events.length > 0 };
  return {
    redacted_narrative: red, redactions, suspect_drugs: suspects, events,
    extraction: { sentences: extSentences, pairs: [], note: "Browser engine: dictionary extraction. The server engine uses the trained CRF and relation models." },
    seriousness: { serious: Object.keys(seriousness).length > 0, criteria: seriousness },
    outcome, time_to_onset: onset,
    dechallenge: dechPos ? "positive" : dechNeg ? "negative" : "not reported",
    rechallenge: rechPos ? "positive" : rechNeg ? "negative" : "not reported",
    icsr_minimum_criteria: minimum, valid_icsr: Object.values(minimum).every(Boolean), assessments,
  };
}
