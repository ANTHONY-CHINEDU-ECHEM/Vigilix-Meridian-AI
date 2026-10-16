// Port of vigilix/rag/graph.py over the compact graph exported for the browser.

export const PD_GROUPS: Record<string, string[]> = {
  "QT prolongation": ["qt prolongation", "electrocardiogram qt prolonged", "electrocardiogram qt corrected interval prolonged", "torsade de pointes", "long qt syndrome"],
  Bleeding: ["gastrointestinal hemorrhage", "intracranial hemorrhage", "cerebral hemorrhage", "hemorrhage", "bleeding", "melena", "hematemesis"],
  "Serotonin toxicity": ["serotonin syndrome"],
  "CNS and respiratory depression": ["respiratory depression", "coma", "depressed level of consciousness", "respiratory arrest"],
  Hyperkalaemia: ["hyperkalemia", "blood potassium increased"],
  Hyponatraemia: ["hyponatremia", "syndrome of inappropriate antidiuretic hormone", "inappropriate antidiuretic hormone secretion"],
  Nephrotoxicity: ["acute kidney injury", "renal failure acute", "nephrotoxicity", "acute renal failure"],
  Hepatotoxicity: ["hepatic failure", "hepatitis", "drug induced liver injury", "liver injury", "hepatotoxicity", "hepatic necrosis"],
  Myelosuppression: ["agranulocytosis", "pancytopenia", "bone marrow failure", "aplastic anemia", "bone marrow depression"],
  Hypotension: ["hypotension", "orthostatic hypotension"],
  Bradycardia: ["bradycardia", "atrioventricular block", "atrioventricular block complete", "sinus arrest"],
  Hypoglycaemia: ["hypoglycemia"],
  "Seizure threshold": ["seizure", "convulsion", "grand mal convulsion"],
  "Anticholinergic effects": ["urinary retention", "paralytic ileus", "ileus"],
  Myopathy: ["rhabdomyolysis", "myopathy"],
};

export const REL_LABEL: Record<string, string> = {
  labelled_reaction: "Listed in labels",
  case_reported: "Case reports",
  literature_induced: "Literature (chemical induced disease)",
  faers_signal: "FAERS disproportionality",
  interacts: "Documented interaction",
  in_class: "Class",
  treats: "Indication",
  targets: "Target",
};

export interface Edge {
  src: string;
  dst: string;
  rel: string;
  sources: string[];
  evidence: number;
  weight: number;
  [k: string]: any;
}

export class KnowledgeGraph {
  nodes = new Map<string, any>();
  out = new Map<string, Edge[]>();
  inc = new Map<string, Edge[]>();
  pair = new Map<string, Edge[]>();
  edgeCount = 0;

  constructor(data: { nodes: any[][]; rels: string[]; sources: string[]; edges: any[][] }) {
    const ids: string[] = [];
    for (const [id, kind, name, extra] of data.nodes) {
      ids.push(id);
      const n: any = { id, kind, name };
      if (kind === "reaction") n.soc = extra;
      else if (kind === "drug") n.atc = extra;
      else if (extra) n.code = extra;
      this.nodes.set(id, n);
    }
    for (const [s, d, r, srcs, evidence, weight, attrs] of data.edges) {
      const e: Edge = { src: ids[s], dst: ids[d], rel: data.rels[r], sources: (srcs as number[]).map((i) => data.sources[i]), evidence, weight, ...(attrs || {}) };
      this.push(this.out, e.src, e);
      this.push(this.inc, e.dst, e);
      this.push(this.pair, `${e.src}|${e.dst}`, e);
      if (e.rel === "interacts") this.push(this.pair, `${e.dst}|${e.src}`, e);
      this.edgeCount++;
    }
  }
  private push(m: Map<string, Edge[]>, k: string, e: Edge) {
    const a = m.get(k);
    if (a) a.push(e);
    else m.set(k, [e]);
  }

  reactionsOf(drug: string, rel?: string): Edge[] {
    return (this.out.get(`drug:${drug}`) || []).filter((e) => e.dst.startsWith("reaction:") && (!rel || e.rel === rel));
  }

  pairEvidence(drug: string, reaction: string) {
    const edges = this.pair.get(`drug:${drug}|reaction:${reaction}`) || [];
    const relations: Record<string, any> = {};
    for (const e of edges) {
      const item: any = { sources: e.sources, evidence: e.evidence };
      for (const k of ["ebgm", "eb05", "ror", "cases", "dataset", "labelled", "pmids", "section"]) if (e[k] !== undefined) item[k] = e[k];
      relations[e.rel] = item;
    }
    return { drug, reaction, found: edges.length > 0, relations };
  }

  interaction(a: string, b: string) {
    const na = `drug:${a}`,
      nb = `drug:${b}`;
    const direct = (this.pair.get(`${na}|${nb}`) || []).filter((e) => e.rel === "interacts");
    const ra = new Set(this.reactionsOf(a, "labelled_reaction").map((e) => e.dst.split(":").slice(1).join(":")));
    const rb = new Set(this.reactionsOf(b, "labelled_reaction").map((e) => e.dst.split(":").slice(1).join(":")));
    const shared: any[] = [];
    for (const [group, terms] of Object.entries(PD_GROUPS)) {
      const ha = terms.filter((t) => ra.has(t)).sort();
      const hb = terms.filter((t) => rb.has(t)).sort();
      if (ha.length && hb.length) shared.push({ group, [a]: ha.slice(0, 4), [b]: hb.slice(0, 4) });
    }
    const ca = new Set((this.out.get(na) || []).filter((e) => e.rel === "in_class").map((e) => e.dst));
    const cb = new Set((this.out.get(nb) || []).filter((e) => e.rel === "in_class").map((e) => e.dst));
    const sharedClasses = [...ca].filter((c) => cb.has(c)).sort().map((c) => this.nodes.get(c)?.name);
    return {
      drugs: [a, b],
      documented: direct.map((e) => ({ sources: e.sources, types: e.types || [], evidence: e.evidence, docs: e.docs || [] })),
      shared_risk_groups: shared,
      shared_classes: sharedClasses,
      known: { [a]: this.nodes.has(na), [b]: this.nodes.has(nb) },
    };
  }

  private name(id: string) {
    return this.nodes.get(id)?.name ?? id.split(":").slice(1).join(":");
  }

  drugProfile(drug: string, top = 25) {
    const nid = `drug:${drug}`;
    const node = this.nodes.get(nid);
    if (!node) return { drug, found: false };
    const byRel: Record<string, Edge[]> = {};
    for (const e of this.out.get(nid) || []) (byRel[e.rel] ||= []).push(e);
    for (const e of this.inc.get(nid) || []) if (e.rel === "interacts") (byRel.interacts ||= []).push({ ...e, src: e.dst, dst: e.src });
    const soc: Record<string, number> = {};
    for (const e of byRel.labelled_reaction || []) {
      const s = this.nodes.get(e.dst)?.soc || "Unclassified";
      soc[s] = (soc[s] || 0) + 1;
    }
    const socSorted = Object.fromEntries(Object.entries(soc).sort((x, y) => y[1] - x[1]));
    const counts: Record<string, number> = {};
    for (const [k, v] of Object.entries(byRel)) counts[REL_LABEL[k] || k] = v.length;
    const signals = [...(byRel.faers_signal || [])].sort((x, y) => (y.eb05 || 0) - (x.eb05 || 0));
    return {
      drug,
      found: true,
      atc: node.atc,
      counts,
      labelled_by_soc: socSorted,
      faers_signals: signals.slice(0, top).map((e) => ({ reaction: this.name(e.dst), eb05: e.eb05, ebgm: e.ebgm, cases: e.cases, labelled: e.labelled, dataset: e.dataset })),
      case_reported: (byRel.case_reported || [])
        .map((e) => ({ reaction: this.name(e.dst), reports: (e.pmids || []).length || e.evidence, pmids: (e.pmids || []).slice(0, 5) }))
        .sort((x, y) => y.reports - x.reports)
        .slice(0, top),
      literature: (byRel.literature_induced || [])
        .map((e) => ({ reaction: this.name(e.dst), pmids: (e.pmids || []).slice(0, 5) }))
        .sort((x, y) => y.pmids.length - x.pmids.length)
        .slice(0, top),
      interactions: (byRel.interacts || [])
        .map((e) => ({ drug: this.name(e.dst), types: e.types || [], evidence: e.evidence }))
        .sort((x, y) => y.evidence - x.evidence)
        .slice(0, top),
      classes: (byRel.in_class || []).map((e) => this.name(e.dst)).slice(0, 12),
      indications: (byRel.treats || []).map((e) => this.name(e.dst)).slice(0, 12),
      targets: (byRel.targets || []).map((e) => this.name(e.dst)).slice(0, 16),
    };
  }

  subgraph(drug: string, limit = 40) {
    const nid = `drug:${drug}`;
    if (!this.nodes.has(nid)) return { nodes: [], edges: [] };
    const priority: Record<string, number> = { faers_signal: 0, case_reported: 1, interacts: 2, literature_induced: 3, labelled_reaction: 4, in_class: 5, treats: 6, targets: 7 };
    const caps: Record<string, number> = { faers_signal: 12, case_reported: 8, interacts: 8, literature_induced: 6, labelled_reaction: 10, in_class: 4, treats: 4, targets: 4 };
    const cand = [...(this.out.get(nid) || []), ...(this.inc.get(nid) || []).filter((e) => e.rel === "interacts")];
    cand.sort((a, b) => (priority[a.rel] ?? 9) - (priority[b.rel] ?? 9) || (b.weight || 0) - (a.weight || 0) || b.evidence - a.evidence);
    const quota: Record<string, number> = {};
    const keep: Edge[] = [];
    for (const e of cand) {
      if ((quota[e.rel] || 0) >= (caps[e.rel] ?? 3)) continue;
      quota[e.rel] = (quota[e.rel] || 0) + 1;
      keep.push(e);
      if (keep.length >= limit) break;
    }
    const ids = new Set([nid]);
    for (const e of keep) {
      ids.add(e.src);
      ids.add(e.dst);
    }
    return {
      nodes: [...ids].filter((i) => this.nodes.has(i)).map((i) => this.nodes.get(i)),
      edges: keep.map((e) => ({ src: e.src, dst: e.dst, rel: e.rel, label: REL_LABEL[e.rel] || e.rel, weight: e.weight, sources: e.sources })),
    };
  }

  reactionProfile(reaction: string, top = 30) {
    const nid = `reaction:${reaction}`;
    if (!this.nodes.has(nid)) return { reaction, found: false };
    const by = new Map<string, { relations: Set<string>; eb05: number | null }>();
    for (const e of this.inc.get(nid) || []) {
      const d = this.nodes.get(e.src)?.name;
      if (!by.has(d)) by.set(d, { relations: new Set(), eb05: null });
      const r = by.get(d)!;
      r.relations.add(e.rel);
      if (e.rel === "faers_signal") r.eb05 = e.eb05;
    }
    const rows = [...by.entries()].map(([drug, v]) => ({ drug, relations: [...v.relations].sort(), eb05: v.eb05 }));
    rows.sort((a, b) => b.relations.length - a.relations.length || (b.eb05 || 0) - (a.eb05 || 0));
    return { reaction, found: true, soc: this.nodes.get(nid)?.soc, drugs: rows.slice(0, top), total_drugs: rows.length };
  }

  evidenceSummary(drugs: string[], reactions: string[]) {
    const pairs = [];
    for (const d of drugs.slice(0, 3)) for (const r of reactions.slice(0, 3)) pairs.push(this.pairEvidence(d, r));
    const inter = [];
    const n = Math.min(3, drugs.length);
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) inter.push(this.interaction(drugs[i], drugs[j]));
    const flags = { labelled: false, faers: false, case: false, literature: false, interaction: false };
    for (const p of pairs) {
      flags.labelled ||= "labelled_reaction" in p.relations;
      flags.faers ||= "faers_signal" in p.relations;
      flags.case ||= "case_reported" in p.relations;
      flags.literature ||= "literature_induced" in p.relations;
    }
    for (const it of inter) flags.interaction ||= it.documented.length > 0 || it.shared_risk_groups.length > 0;
    return { pairs, interactions: inter, flags };
  }

  stats() {
    return { nodes: this.nodes.size, edges: this.edgeCount };
  }
}
