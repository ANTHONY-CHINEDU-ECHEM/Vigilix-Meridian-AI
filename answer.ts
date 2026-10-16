// Ports of vigilix/rag/composer.py, verifier.py and pipeline.py (extractive writer).
import { Dictionary } from "./dict";
import { KnowledgeGraph } from "./graph";
import * as G from "./guard";
import { QueryInfo } from "./query";
import { BrowserRetriever } from "./retriever";
import { analyse, applySpelling, numbers, rawTokens, rewrite, sentences } from "./text";

const LEVEL_PRIOR: Record<number, number> = { 1: 1.0, 2: 0.8, 3: 0.65, 4: 0.45 };
const TABLE = /(\|.*){3,}|\b\d+(\.\d+)?\s+\d+(\.\d+)?\s+\d+(\.\d+)?\s+\d+(\.\d+)?\b/;
const SECTION_LABEL = /^(?:BACKGROUND|OBJECTIVES?|METHODS?|RESULTS?|CONCLUSIONS?|DISCUSSION|CASE (?:SUMMARY|SUMMARIES|REPORT|PRESENTATION)|PURPOSE|AIMS?|INTRODUCTION|SETTING|DESIGN|PATIENTS?|INTERVENTIONS?|EXCERPT)\s*:\s*/;

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export function graphEvidenceText(summary: any): string | null {
  const parts: string[] = [];
  for (const p of summary.pairs || []) {
    const rel = p.relations;
    const d = p.drug,
      r = p.reaction;
    if (!Object.keys(rel).length) {
      parts.push(`The knowledge graph holds no labelled reaction, FAERS signal, case report or literature link between ${d} and ${r}.`);
      continue;
    }
    const bits: string[] = [];
    if (rel.labelled_reaction) bits.push(`${r} is a labelled reaction of ${d} (${rel.labelled_reaction.sources.slice(0, 4).join(", ")})`);
    if (rel.faers_signal) {
      const f = rel.faers_signal;
      bits.push(`FAERS shows disproportionate reporting of ${r} with ${d} in the ${(f.dataset || "").replace(/_/g, " ")} dataset (${f.cases} drug and event pairs, EBGM ${f.ebgm}, EB05 ${f.eb05}, ROR ${f.ror})`);
    }
    if (rel.case_reported) {
      const n = (rel.case_reported.pmids || []).length || rel.case_reported.evidence;
      bits.push(`${n} annotated case report${n !== 1 ? "s" : ""} in the ADE corpus describe ${r} with ${d}`);
    }
    if (rel.literature_induced) {
      const n = (rel.literature_induced.pmids || []).length || 1;
      bits.push(`${n} abstract${n !== 1 ? "s" : ""} in the BioCreative V CDR corpus annotate ${r} as induced by ${d}`);
    }
    parts.push(cap(bits.join("; ")) + ".");
  }
  for (const it of summary.interactions || []) {
    const [a, b] = it.drugs;
    const bits: string[] = [];
    if (it.documented.length) {
      const types = [...new Set(it.documented.flatMap((x: any) => x.types).filter(Boolean))].sort();
      const srcs = [...new Set(it.documented.flatMap((x: any) => x.sources))].sort();
      bits.push(`an interaction between ${a} and ${b} is annotated in ${srcs.join(", ")}` + (types.length ? ` (types: ${types.join(", ")})` : ""));
    }
    for (const g of it.shared_risk_groups.slice(0, 3)) bits.push(`both drugs list reactions in the ${g.group.toLowerCase()} risk group (${a}: ${g[a].slice(0, 2).join(", ")}; ${b}: ${g[b].slice(0, 2).join(", ")})`);
    if (it.shared_classes.length) bits.push(`both belong to ${it.shared_classes.slice(0, 2).join(", ")}`);
    parts.push(bits.length ? `For ${a} with ${b}, ${bits.join("; ")}.` : `The knowledge graph has no documented interaction or shared pharmacodynamic risk group for ${a} with ${b}.`);
  }
  return parts.length ? parts.join(" ") : null;
}

function sectionPrior(it: any): number {
  const sec = (it.section || "").toLowerCase();
  if (it.source_type === "trial_abstract") return sec.includes("result") || sec.includes("conclusion") ? 1 : 0.5;
  if (it.source_type === "drug_label") return sec.includes("warning") || sec.includes("boxed") || sec.includes("undesirable") ? 1 : 0.8;
  return 0.8;
}

export function compose(qTokens: string[], q: QueryInfo, items: any[], maxSentences = 5) {
  const qset = new Set(qTokens);
  const chosen: any[] = [];
  const g = items.find((it) => it.source_type === "graph");
  if (g) chosen.push({ text: sentences(g.text)[0], citations: [g.n], kind: "graph" });
  const scored: [number, string, any, Set<string>][] = [];
  for (const it of items) {
    if (it.source_type === "graph") continue;
    for (let s of sentences(it.text)) {
      s = s.replace(SECTION_LABEL, "").trim();
      const words = s.split(/\s+/).length;
      if (words < 7 || words > 70 || TABLE.test(s) || s.includes("[see")) continue;
      const toks = new Set(analyse(s));
      if (!toks.size) continue;
      const cov = [...qset].filter((t) => toks.has(t)).length / Math.max(qset.size, 1);
      const sl = s.toLowerCase();
      let ent = 0;
      if (q.drugs.length) ent += 0.5 * Number(q.drugs.some((d) => sl.includes(d)));
      if (q.reactions.length) ent += 0.5 * Number(q.reactions.some((r) => sl.includes(r)));
      let score = 0.42 * cov + 0.22 * ent + 0.14 * (LEVEL_PRIOR[it.evidence_level] ?? 0.4) + 0.12 * (1 / Math.sqrt(it.n)) + 0.1 * sectionPrior(it);
      if (numbers(s).length && (qTokens.join(" ").includes("frequen") || qset.has("common") || qset.has("how"))) score += 0.03;
      scored.push([score, s, it, toks]);
    }
  }
  scored.sort((a, b) => b[0] - a[0]);
  const used: Set<string>[] = [];
  const perItem = new Map<number, number>();
  for (const [score, s, it, toks] of scored) {
    if (chosen.length >= maxSentences) break;
    if (used.some((u) => [...toks].filter((t) => u.has(t)).length / Math.max(new Set([...toks, ...u]).size, 1) > 0.5)) continue;
    if ((perItem.get(it.n) || 0) >= 2) continue;
    perItem.set(it.n, (perItem.get(it.n) || 0) + 1);
    used.push(toks);
    chosen.push({ text: s, citations: [it.n], kind: "extract", score: Math.round(score * 1000) / 1000 });
  }
  const head = chosen.filter((c) => c.kind === "graph");
  const level = new Map(items.map((it) => [it.n, it.evidence_level]));
  const rest = chosen.filter((c) => c.kind !== "graph").sort((a, b) => (level.get(a.citations[0]) ?? 4) - (level.get(b.citations[0]) ?? 4) || a.citations[0] - b.citations[0]);
  return [...head, ...rest];
}

// ------------------------------------------------------------------ verifier
const NEG = /\b(no|not|never|without|none|neither|nor|absence|absent|did not|does not|was not|were not|cannot|unlikely|failed to)\b/gi;
const STOP_EXTRA = new Set(["report", "reported", "patient", "includ", "may", "associat"]);
const tok = (t: string) => analyse(t).filter((x) => !STOP_EXTRA.has(x));
const spelled = (t: string) => rewrite(rawTokens(t).map(applySpelling)).join(" ");
const negCount = (s: string) => (s.match(NEG) || []).length;

export function verifierFeatures(claim: string, cited: string[], drugs: string[], rx: string[], valid: boolean): number[] {
  const ct = tok(claim);
  const cset = new Set(ct);
  const evid = cited.join(" ");
  const et = new Set(tok(evid));
  const ebi = new Set<string>();
  let bestRec = 0,
    bestJac = 0,
    bestSentence = "";
  for (const s of evid ? sentences(evid) : []) {
    const st = tok(s);
    const ss = new Set(st);
    st.slice(1).forEach((t, i) => ebi.add(st[i] + " " + t));
    if (cset.size) {
      const inter = [...cset].filter((t) => ss.has(t)).length;
      const rec = inter / cset.size;
      const jac = inter / Math.max(new Set([...cset, ...ss]).size, 1);
      if (rec > bestRec) bestSentence = s;
      bestRec = Math.max(bestRec, rec);
      bestJac = Math.max(bestJac, jac);
    }
  }
  const cbi = new Set(ct.slice(1).map((t, i) => ct[i] + " " + t));
  const nums = numbers(claim);
  const evNums = new Set(numbers(evid));
  const numFrac = nums.length ? nums.filter((n) => evNums.has(n)).length / nums.length : 1;
  const evL = " " + spelled(evid) + " ";
  const drugC = drugs.length ? drugs.filter((d) => evL.includes(` ${spelled(d)} `)).length / drugs.length : 1;
  const rxC = rx.length ? rx.filter((r) => evL.includes(` ${spelled(r)} `)).length / rx.length : 1;
  const negClaim = negCount(claim);
  const negBest = bestSentence ? negCount(bestSentence) : negCount(evid);
  const negAgree = negClaim > 0 === negBest > 0 && (bestRec < 0.95 || negClaim === negBest) ? 1 : 0;
  return [
    [...cset].filter((t) => et.has(t)).length / Math.max(cset.size, 1),
    bestRec,
    cbi.size ? [...cbi].filter((b) => ebi.has(b)).length / cbi.size : 1,
    numFrac === 1 ? 1 : 0,
    numFrac,
    drugC,
    rxC,
    negAgree,
    valid ? 1 : 0,
    Math.log1p(ct.length),
    bestJac,
  ];
}

export class Verifier {
  constructor(private m: { features: string[]; coef: number[]; intercept: number; mean: number[]; scale: number[]; thresholds: number[] }) {}
  verify(claim: string, cited: string[], drugs: Dictionary, reactions: Dictionary, valid = true) {
    const f = verifierFeatures(claim, cited, drugs.mentions(claim), reactions.mentions(claim), valid);
    let p = 0;
    if (valid && cited.length) {
      const z = f.reduce((acc, v, i) => acc + ((v - this.m.mean[i]) / this.m.scale[i]) * this.m.coef[i], this.m.intercept);
      p = 1 / (1 + Math.exp(-z));
    }
    const issues: string[] = [];
    if (f[3] < 1) issues.push("number not found in cited evidence");
    if (f[5] < 1) issues.push("drug not mentioned in cited evidence");
    if (f[6] < 1) issues.push("reaction not mentioned in cited evidence");
    if (f[7] < 1) issues.push("negation not supported");
    if (!valid || !cited.length) issues.push("missing or invalid citation");
    const [sup, part] = this.m.thresholds;
    const status = issues.some((i) => /^(number|drug|missing)/.test(i)) ? "unsupported" : p >= sup ? "supported" : p >= part ? "partial" : "unsupported";
    return { status, probability: Math.round(p * 1000) / 1000, issues, features: Object.fromEntries(this.m.features.map((n, i) => [n, Math.round(f[i] * 1000) / 1000])) };
  }
}

// ------------------------------------------------------------------ pipeline
export class BrowserPipeline {
  constructor(public retriever: BrowserRetriever, public verifier: Verifier, public graph: KnowledgeGraph) {}

  answer(question: string, k = 8) {
    const t0 = performance.now();
    const pre = this.retriever.understand(question);
    const g = G.check(question, pre.drugs.length > 0 || pre.reactions.length > 0);
    const q = this.retriever.understand(g.redacted_text);
    const res = this.retriever.search(q, k);
    const items: any[] = res.map((c, i) => {
      const r: any = this.retriever.resultDict(c, i + 1);
      r.text = G.neutralise(r.text)[0];
      r.n = i + 1;
      return r;
    });
    const summary: any = q.drugs.length && (q.reactions.length || q.drugs.length > 1) ? this.graph.evidenceSummary(q.drugs, q.reactions) : { pairs: [], interactions: [], flags: {} };
    const gtext = graphEvidenceText(summary);
    if (gtext) items.push({ n: items.length + 1, rank: items.length + 1, pid: "graph", doc_id: "graph", source_type: "graph", evidence_level: 3, evidence_label: "Knowledge graph", title: "Knowledge graph evidence", section: "Graph", text: gtext, url: "", drugs: q.drugs, reactions: q.reactions, score: 0 });
    const timings: any = { retrieval_ms: Math.round(performance.now() - t0) };
    const base = { question, guard: g, query: q, evidence: items, graph: summary, engine: "extractive", engine_reason: "browser engine: extractive composer" };
    if (g.crisis) return { ...base, engine: "guard", answer: [{ text: G.CRISIS_MESSAGE, citations: [], verification: { status: "not_applicable" } }], confidence: { level: "not_applicable" }, timings, notices: ["crisis"] };
    if (g.out_of_scope) return { ...base, engine: "guard", evidence: [], answer: [{ text: G.SCOPE_MESSAGE, citations: [], verification: { status: "not_applicable" } }], confidence: { level: "not_applicable" }, timings, notices: ["out_of_scope"] };
    const byN = new Map(items.map((it) => [it.n, it]));
    let sents: any[] = compose(q.tokens, q, items).map((s) => {
      const cited = s.citations.filter((c: number) => byN.has(c)).map((c: number) => byN.get(c).text);
      return { ...s, verification: this.verifier.verify(s.text, cited, this.retriever.drugs, this.retriever.reactions, s.citations.length > 0) };
    });
    const notices: string[] = [];
    if (g.dosing_request) {
      notices.push("dosing");
      sents = [{ text: G.DOSING_MESSAGE, citations: [], kind: "notice", verification: { status: "not_applicable" } }, ...sents];
    }
    timings.total_ms = Math.round(performance.now() - t0);
    return { ...base, answer: sents, confidence: confidence(items, sents.filter((s) => s.kind !== "notice"), q), timings, notices };
  }
}

function confidence(items: any[], sents: any[], q: QueryInfo) {
  if (!sents.length) return { level: "low", score: 0, reasons: ["no answer sentences"] };
  const sup = sents.filter((s) => s.verification.status === "supported").length / sents.length;
  const unsup = sents.filter((s) => s.verification.status === "unsupported").length;
  const top = Math.min(4, ...items.filter((it) => it.source_type !== "graph").map((it) => it.evidence_level));
  const strong = ({ 1: 1, 2: 0.8, 3: 0.6, 4: 0.4 } as Record<number, number>)[top] ?? 0.4;
  let entityHit = 1;
  if (q.drugs.length) {
    const top5 = items.slice(0, 5);
    entityHit = top5.filter((it) => (it.drugs || []).some((d: string) => q.drugs.includes(d)) || q.drugs.some((d) => it.title.toLowerCase().includes(d))).length / Math.max(Math.min(5, items.length), 1);
  }
  const score = 0.5 * sup + 0.3 * strong + 0.2 * entityHit - 0.15 * unsup;
  const reasons = [`${Math.round(sup * 100)} percent of sentences fully supported`, `strongest evidence: level ${top}`];
  if (q.drugs.length) reasons.push(`${Math.round(entityHit * 100)} percent of top evidence mentions the queried drug`);
  return { level: score >= 0.75 ? "high" : score >= 0.5 ? "moderate" : "low", score: Math.round(score * 1000) / 1000, reasons };
}
