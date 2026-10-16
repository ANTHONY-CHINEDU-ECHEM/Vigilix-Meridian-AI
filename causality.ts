// Naranjo and WHO UMC scoring, identical to vigilix/causality/assess.py.

export const NARANJO: [string, string, Record<string, number>][] = [
  ["previous_reports", "Are there previous conclusive reports on this reaction?", { yes: 1, no: 0, unknown: 0 }],
  ["after_drug", "Did the adverse event appear after the suspected drug was administered?", { yes: 2, no: -1, unknown: 0 }],
  ["improved_on_stop", "Did the reaction improve when the drug was discontinued or a specific antagonist was given?", { yes: 1, no: 0, unknown: 0 }],
  ["reappeared_on_rechallenge", "Did the reaction reappear when the drug was readministered?", { yes: 2, no: -1, unknown: 0 }],
  ["alternative_causes", "Are there alternative causes that could on their own have caused the reaction?", { yes: -1, no: 2, unknown: 0 }],
  ["placebo_reaction", "Did the reaction reappear when a placebo was given?", { yes: -1, no: 1, unknown: 0 }],
  ["toxic_concentration", "Was the drug detected in blood or other fluids in toxic concentrations?", { yes: 1, no: 0, unknown: 0 }],
  ["dose_response", "Was the reaction more severe when the dose was increased or less severe when it was decreased?", { yes: 1, no: 0, unknown: 0 }],
  ["previous_similar", "Did the patient have a similar reaction to the same or similar drugs before?", { yes: 1, no: 0, unknown: 0 }],
  ["objective_evidence", "Was the adverse event confirmed by objective evidence?", { yes: 1, no: 0, unknown: 0 }],
];

export function naranjo(answers: Record<string, string>) {
  let total = 0;
  const items = NARANJO.map(([key, question, pts]) => {
    const a = pts[answers[key]] !== undefined ? answers[key] : "unknown";
    total += pts[a];
    return { key, question, answer: a, points: pts[a] };
  });
  const category = total >= 9 ? "definite" : total >= 5 ? "probable" : total >= 1 ? "possible" : "doubtful";
  return { score: total, category, items };
}

export function whoUmc(time: string, other: string, dech: string, rech: string, known: string, sufficient = true) {
  if (!sufficient) return { category: "unassessable", reason: "information is insufficient or contradictory and cannot be supplemented" };
  if (time === "no") return { category: "unlikely", reason: "the time relationship makes a causal relationship improbable" };
  if (time === "yes" && other === "no" && dech === "yes" && rech === "yes" && known === "yes")
    return { category: "certain", reason: "plausible timing, no alternative explanation, positive dechallenge and rechallenge, recognised reaction" };
  if (time === "yes" && other === "no" && dech === "yes") return { category: "probable", reason: "reasonable timing, unlikely alternative explanation and clinically reasonable response to withdrawal" };
  if (time === "yes" && (other === "yes" || other === "unknown")) {
    if (dech === "unknown" && other === "unknown") return { category: "conditional", reason: "more data are needed for a proper assessment (dechallenge and alternative causes not documented)" };
    return { category: "possible", reason: "reasonable timing but disease or other drugs could also explain the event" };
  }
  if (time === "yes" && other === "no" && (dech === "no" || dech === "unknown")) return { category: "possible", reason: "reasonable timing and no alternative explanation, but withdrawal information is lacking or negative" };
  return { category: "conditional", reason: "more data are needed for a proper assessment" };
}
