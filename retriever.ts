// Browser retrieval: BM25 over a packed inverted index, entity and source
// routing, the lexical LightGBM reranker and the diversity cap. Mirrors
// vigilix/rag/retriever.py without the dense generator.
import { Dictionary } from "./dict";
import { KnowledgeGraph } from "./graph";
import { INTENTS, POP, QueryInfo, understand } from "./query";
import { analyse } from "./text";

export const SOURCE_TYPES = ["guidance_card", "drug_label", "trial_abstract", "signal_summary", "kg_fact", "interaction_monograph", "cid_abstract", "interaction_abstract", "case_report"];

export interface Passage {
  pid: string;
  doc_id: string;
  source_type: string;
  evidence_level: number;
  evidence_label: string;
  title: string;
  section: string;
  text: string;
  url: string;
  drugs: string[];
  reactions: string[];
  roles?: string[];
  region?: string;
  references?: string[];
}

export class PackedBM25 {
  vocab: Map<string, number>;
  offsets: Uint32Array;
  scales: Float32Array;
  docs: Uint16Array;
  weights: Uint8Array;
  n: number;
  constructor(terms: string[], buf: ArrayBuffer, n: number) {
    this.vocab = new Map(terms.map((t, i) => [t, i]));
    const V = terms.length;
    this.offsets = new Uint32Array(buf, 0, V + 1);
    this.scales = new Float32Array(buf, 4 * (V + 1), V);
    const P = this.offsets[V];
    const docStart = 4 * (V + 1) + 4 * V;
    this.docs = new Uint16Array(buf, docStart, P);
    this.weights = new Uint8Array(buf, docStart + 2 * P, P);
    this.n = n;
  }
  scores(tokens: string[]): Float32Array {
    const s = new Float32Array(this.n);
    const tf = new Map<number, number>();
    for (const t of tokens) {
      const i = this.vocab.get(t);
      if (i !== undefined) tf.set(i, (tf.get(i) || 0) + 1);
    }
    for (const [i, q] of tf) {
      const sc = (this.scales[i] / 255) * q;
      for (let p = this.offsets[i]; p < this.offsets[i + 1]; p++) s[this.docs[p]] += this.weights[p] * sc;
    }
    return s;
  }
}

function topK(scores: Float32Array, k: number, subset?: number[]): [number, number][] {
  const idx = subset ?? Array.from({ length: scores.length }, (_, i) => i);
  const arr: [number, number][] = [];
  for (const i of idx) if (scores[i] > 0) arr.push([i, scores[i]]);
  arr.sort((a, b) => b[1] - a[1]);
  return arr.slice(0, k);
}

// ------------------------------------------------------------------ LightGBM
interface TreeNode {
  split_feature?: number;
  threshold?: number;
  decision_type?: string;
  default_left?: boolean;
  left_child?: TreeNode;
  right_child?: TreeNode;
  leaf_value?: number;
}
export class GBDT {
  trees: TreeNode[];
  names: string[];
  constructor(model: any) {
    this.trees = model.tree_info.map((t: any) => t.tree_structure);
    this.names = model.feature_names;
  }
  predict(x: number[]): number {
    let s = 0;
    for (const t of this.trees) {
      let n = t;
      while (n.leaf_value === undefined) {
        const v = x[n.split_feature!];
        n = (Number.isNaN(v) ? n.default_left : v <= n.threshold!) ? n.left_child! : n.right_child!;
      }
      s += n.leaf_value;
    }
    return s;
  }
}

export interface Cand {
  idx: number;
  bm25: number;
  rankBm25?: number;
  rankEntity?: number;
  rankCard?: number;
  rankLabel?: number;
  score: number;
}

export class BrowserRetriever {
  byDrug = new Map<string, number[]>();
  byReaction = new Map<string, number[]>();
  cardIdx: number[] = [];
  labelSet = new Set<number>();
  docToIdx = new Map<string, number[]>();
  private tokCache = new Map<number, string[]>();
  constructor(public passages: Passage[], public bm25: PackedBM25, public model: GBDT, public graph: KnowledgeGraph, public drugs: Dictionary, public reactions: Dictionary) {
    passages.forEach((p, i) => {
      for (const d of p.drugs) (this.byDrug.get(d) || this.byDrug.set(d, []).get(d)!).push(i);
      for (const r of p.reactions) (this.byReaction.get(r) || this.byReaction.set(r, []).get(r)!).push(i);
      if (p.source_type === "guidance_card") this.cardIdx.push(i);
      if (p.source_type === "drug_label") this.labelSet.add(i);
      (this.docToIdx.get(p.doc_id) || this.docToIdx.set(p.doc_id, []).get(p.doc_id)!).push(i);
    });
  }
  understand(text: string): QueryInfo {
    return understand(text, this.drugs, this.reactions);
  }
  entitySubset(drugs: string[], reactions: string[]): number[] {
    const ds = new Set<number>();
    for (const d of drugs) for (const i of this.byDrug.get(d) || []) ds.add(i);
    if (reactions.length) {
      const rs = new Set<number>();
      for (const r of reactions) for (const i of this.byReaction.get(r) || []) rs.add(i);
      const both = ds.size ? [...ds].filter((i) => rs.has(i)) : [...rs];
      if (both.length >= 5) return both.sort((a, b) => a - b);
    }
    return [...ds].sort((a, b) => a - b);
  }
  private ptoks(i: number): string[] {
    let t = this.tokCache.get(i);
    if (!t) {
      t = analyse(this.passages[i].text);
      if (this.tokCache.size > 20000) this.tokCache.clear();
      this.tokCache.set(i, t);
    }
    return t;
  }
  search(q: QueryInfo, k = 8): Cand[] {
    const scores = this.bm25.scores(q.tokens);
    const cands = new Map<number, Cand>();
    const get = (i: number) => cands.get(i) || cands.set(i, { idx: i, bm25: scores[i], score: 0 }).get(i)!;
    topK(scores, 80).forEach(([i], r) => (get(i).rankBm25 = r));
    if (q.drugs.length || q.reactions.length) {
      const sub = this.entitySubset(q.drugs, q.reactions);
      if (sub.length) topK(scores, 40, sub).forEach(([i], r) => (get(i).rankEntity = r));
    }
    topK(scores, 6, this.cardIdx).forEach(([i], r) => (get(i).rankCard = r));
    if (q.drugs.length) {
      const lab = this.entitySubset(q.drugs, []).filter((i) => this.labelSet.has(i));
      if (lab.length) topK(scores, 6, lab).forEach(([i], r) => (get(i).rankLabel = r));
    }
    if (!cands.size) return [];
    const flags = q.drugs.length && (q.reactions.length || q.drugs.length > 1) ? this.graph.evidenceSummary(q.drugs, q.reactions).flags : ({} as any);
    const maxBm = Math.max(...[...cands.values()].map((c) => c.bm25)) || 1;
    const qset = new Set(q.tokens);
    const qbi = new Set(q.tokens.slice(1).map((t, i) => q.tokens[i] + " " + t));
    const intents = new Set(q.intents);
    const pops = q.populations.map((p) => POP[p]);
    for (const c of cands.values()) {
      const p = this.passages[c.idx];
      const textL = p.text.toLowerCase();
      const titleL = p.title.toLowerCase();
      const pl = this.ptoks(c.idx);
      const titleT = new Set(analyse(p.title));
      const ptoks = new Set([...pl, ...titleT]);
      const pbi = new Set(pl.slice(1).map((t, i) => pl[i] + " " + t));
      const pdr = new Set(p.drugs);
      const prx = new Set(p.reactions);
      const dm = q.drugs.length ? q.drugs.filter((d) => pdr.has(d) || titleL.includes(d)).length / q.drugs.length : 0;
      const dt = q.drugs.length ? Number(q.drugs.some((d) => titleL.includes(d))) : 0;
      const rm = q.reactions.length ? q.reactions.filter((r) => prx.has(r) || textL.includes(r)).length / q.reactions.length : 0;
      const f: Record<string, number> = {
        bm25: c.bm25,
        bm25_norm: c.bm25 / maxBm,
        rr_bm25: c.rankBm25 !== undefined ? 1 / (c.rankBm25 + 1) : 0,
        rr_entity: c.rankEntity !== undefined ? 1 / (c.rankEntity + 1) : 0,
        rr_card: c.rankCard !== undefined ? 1 / (c.rankCard + 1) : 0,
        rr_label: c.rankLabel !== undefined ? 1 / (c.rankLabel + 1) : 0,
        q_coverage: [...qset].filter((t) => ptoks.has(t)).length / Math.max(qset.size, 1),
        title_coverage: [...qset].filter((t) => titleT.has(t)).length / Math.max(qset.size, 1),
        bigram_overlap: [...qbi].filter((b) => pbi.has(b)).length / Math.max(qbi.size, 1),
        drug_match: dm,
        drug_in_title: dt,
        reaction_match: rm,
        pair_match: Number(dm > 0 && rm > 0),
        evidence_level: p.evidence_level,
        log_len: Math.log1p(p.text.split(/\s+/).length),
        results_section: Number(p.source_type === "trial_abstract" && (p.roles || []).some((r) => r === "results" || r === "conclusions")),
        n_query_drugs: q.drugs.length,
        n_query_reactions: q.reactions.length,
        kg_labelled: Number(!!flags.labelled),
        kg_faers: Number(!!flags.faers),
        kg_case: Number(!!flags.case),
        kg_literature: Number(!!flags.literature),
        kg_interaction: Number(!!flags.interaction),
        population_match: pops.length ? Number(pops.some((pt) => pt.test(p.text))) : 0,
        query_len: q.tokens.length,
      };
      for (const s of SOURCE_TYPES) f[`src_${s}`] = Number(p.source_type === s);
      for (const i of INTENTS) f[`intent_${i}`] = Number(intents.has(i));
      c.score = this.model.predict(this.model.names.map((n) => f[n] ?? 0));
    }
    const ranked = [...cands.values()].sort((a, b) => b.score - a.score);
    const out: Cand[] = [];
    const perDoc = new Map<string, number>();
    for (const c of ranked) {
      const d = this.passages[c.idx].doc_id;
      if ((perDoc.get(d) || 0) >= 2) continue;
      perDoc.set(d, (perDoc.get(d) || 0) + 1);
      out.push(c);
      if (out.length >= k) break;
    }
    return out;
  }
  resultDict(c: Cand, rank: number) {
    const p = this.passages[c.idx];
    return { rank, pid: p.pid, doc_id: p.doc_id, source_type: p.source_type, evidence_level: p.evidence_level, evidence_label: p.evidence_label, title: p.title, section: p.section, text: p.text, url: p.url, drugs: p.drugs, reactions: p.reactions, region: p.region, references: p.references, score: Math.round(c.score * 1e4) / 1e4, scores: { bm25: Math.round(c.bm25 * 1e3) / 1e3 } };
  }
}
