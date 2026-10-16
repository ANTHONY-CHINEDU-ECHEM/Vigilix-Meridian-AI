// The in browser engine: loads the exported bundle (public/data) and
// implements the same contract as the FastAPI service.
import type { Engine } from "../api";
import { BrowserPipeline, Verifier } from "./answer";
import { Dictionary } from "./dict";
import { KnowledgeGraph } from "./graph";
import { BrowserRetriever, GBDT, PackedBM25, Passage } from "./retriever";
import { score } from "./stats";
import { canonicalDrug, canonicalTerm, initText } from "./text";
import { checkRegimen, intake, labelView } from "./tools";

const BASE = new URL("./data/", document.baseURI).toString();

// Some static hosts only serve text and web media types. For those, the
// export can also write each compressed file as base64 text (name.b64.txt),
// which is used when the binary file is not available.
async function fetchRaw(name: string): Promise<ArrayBuffer> {
  const r = await fetch(BASE + name);
  if (r.ok) return r.arrayBuffer();
  if (name.endsWith(".gz")) {
    const t = await fetch(BASE + name + ".b64.txt");
    if (t.ok) {
      const text = (await t.text()).trim();
      const bin = atob(text);
      const out = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
      return out.buffer;
    }
  }
  throw new Error(`could not load ${name} (${r.status})`);
}

async function fetchBytes(name: string): Promise<ArrayBuffer> {
  const buf = await fetchRaw(name);
  if (!name.endsWith(".gz")) return buf;
  const head = new Uint8Array(buf, 0, 2);
  if (head[0] !== 0x1f || head[1] !== 0x8b) return buf; // already decompressed by the server
  const ds = new Blob([buf]).stream().pipeThrough(new DecompressionStream("gzip"));
  return new Response(ds).arrayBuffer();
}
async function fetchJson(name: string): Promise<any> {
  return JSON.parse(new TextDecoder().decode(await fetchBytes(name)));
}

export async function createBrowserEngine(): Promise<Engine> {
  const [lexicon, dicts, pass, terms, blob, reranker, verifierModel, graphData, signals, labels, ddi, pk, overview, evaluation] = await Promise.all([
    fetchJson("lexicon.json"),
    fetchJson("dicts.json.gz"),
    fetchJson("passages.json.gz"),
    fetchJson("bm25_terms.json.gz"),
    fetchBytes("bm25.bin.gz"),
    fetchJson("reranker.json.gz"),
    fetchJson("verifier.json"),
    fetchJson("graph.json.gz"),
    fetchJson("signals.json.gz"),
    fetchJson("labels.json.gz"),
    fetchJson("ddi.json.gz"),
    fetchJson("pk.json"),
    fetchJson("overview.json"),
    fetchJson("evaluation.json").catch(() => ({})),
  ]);
  initText(lexicon);
  const drugs = new Dictionary(dicts.drugs);
  const reactions = new Dictionary(dicts.reactions);
  const passages: Passage[] = pass.rows.map((r: any[]) => {
    const st = pass.source_types[r[2]];
    const [level, label] = pass.levels[st];
    return { pid: r[0], doc_id: r[1], source_type: st, evidence_level: level, evidence_label: label, title: r[3], section: r[4], text: r[5], url: r[6], drugs: r[7], reactions: r[8], roles: r[9], region: r[10] ?? undefined, references: r[11] ?? undefined };
  });
  const graph = new KnowledgeGraph(graphData);
  const retriever = new BrowserRetriever(passages, new PackedBM25(terms, blob, passages.length), new GBDT(reranker), graph, drugs, reactions);
  const pipeline = new BrowserPipeline(retriever, new Verifier(verifierModel), graph);

  const cols: string[] = signals.columns;
  const rows: any[] = signals.rows.map((r: any[]) => {
    const o: any = {};
    cols.forEach((c, i) => (o[c] = typeof r[i] === "number" && ["evans", "ror_signal", "ic_signal", "eb_signal", "labelled", "label_known", "cluster_flag"].includes(c) ? Boolean(r[i]) : r[i]));
    return o;
  });
  const byDrug = new Map<string, any[]>();
  for (const r of rows) (byDrug.get(r.drug) || byDrug.set(r.drug, []).get(r.drug)!).push(r);
  const labelsById = new Map(labels.map((l: any) => [l.doc_id, l]));
  const audit: any[] = [];
  const log = (endpoint: string, res: any, extra: any = {}) =>
    audit.unshift({ id: audit.length + 1, ts: Date.now() / 1000, endpoint, redacted_query: res?.guard?.redacted_text ?? extra.redacted ?? "", redactions: res?.guard?.redactions ?? extra.redactions ?? {}, drugs: res?.query?.drugs ?? extra.drugs ?? [], reactions: res?.query?.reactions ?? extra.reactions ?? [], engine: res?.engine ?? "browser", supported: supportedShare(res), confidence: res?.confidence?.level });

  const resolveDrug = (name: string) => {
    const e = drugs.lookup(name);
    return e ? e.canonical : canonicalDrug(name);
  };

  const engine: Engine = {
    mode: "browser",
    health: async () => ({ status: "ok", engine: "extractive", engine_reason: `browser engine, ${passages.length.toLocaleString("en-GB")} passages`, passages: passages.length }),
    overview: async () => overview,
    ask: async (question) => {
      const res = pipeline.answer(question);
      log("/api/ask", res);
      return res;
    },
    search: async (query) => {
      const q = retriever.understand(query);
      return { query: q, results: retriever.search(q, 10).map((c, i) => retriever.resultDict(c, i + 1)) };
    },
    suggest: async (q, kind = "drug") => (kind === "drug" ? drugs : reactions).suggest(q, 12, (c) => graph.nodes.has(`${kind}:${c}`)),
    drug: async (name) => {
      const c = resolveDrug(name);
      const prof = graph.drugProfile(c);
      const entry = drugs.entries[c] ? { canonical: c, ...drugs.entries[c] } : null;
      const faers = [...groupBy(byDrug.get(c) || [], (r) => r.dataset)].map(([ds, part]) => ({
        dataset: ds,
        pairs: part.reduce((s, r) => s + r.a, 0),
        terms: part.length,
        signals: part.filter((r) => r.eb_signal).length,
        unlabelled_signals: part[0].label_known ? part.filter((r) => r.eb_signal && !r.labelled).length : null,
        label_coverage: part[0].label_known,
      }));
      return {
        drug: c,
        entry,
        profile: prof,
        labels: labels.filter((l: any) => l.substance && canonicalDrug(l.substance) === c).map((l: any) => ({ doc_id: l.doc_id, region: l.region, section: l.section, brand: l.brand, events: l.events.length })),
        faers,
        subgraph: graph.subgraph(c),
      };
    },
    reaction: async (name) => {
      const e = reactions.lookup(name);
      const c = e ? e.canonical : canonicalTerm(name);
      return { reaction: c, entry: e, profile: graph.reactionProfile(c), faers: rows.filter((r) => canonicalTerm(r.pt) === c).sort((a, b) => b.eb05 - a.eb05).slice(0, 30) };
    },
    datasets: async () => signals.datasets,
    signals: async (p) => {
      let out = rows;
      if (p.dataset) out = out.filter((r) => r.dataset === p.dataset);
      if (p.drug) out = out.filter((r) => r.drug === canonicalDrug(String(p.drug)));
      if (p.min_cases) out = out.filter((r) => r.a >= Number(p.min_cases));
      if (p.only_signals) out = out.filter((r) => r.eb_signal);
      if (p.unlabelled) out = out.filter((r) => !r.labelled && r.label_known);
      if (p.hide_clusters) out = out.filter((r) => !r.cluster_flag);
      if (p.soc) out = out.filter((r) => r.soc === p.soc);
      if (p.q) out = out.filter((r) => r.pt.toLowerCase().includes(String(p.q).toLowerCase()));
      const key = String(p.sort || "eb05");
      out = [...out].sort((a, b) => (b[key] ?? -Infinity) - (a[key] ?? -Infinity));
      const socs = [...new Set(rows.map((r) => r.soc).filter(Boolean))].sort();
      return { total: out.length, rows: out.slice(0, Number(p.limit) || 500), socs };
    },
    compute: async (a, b, c, d, dataset) => ({ ...score(a, b, c, d, signals.priors[dataset || "sedatives"]), prior_dataset: dataset || "sedatives" }),
    labels: async (region, q) =>
      labels
        .filter((l: any) => (!region || l.region === region) && (!q || `${l.substance || l.brand || l.label_id} ${l.brand || ""}`.toLowerCase().includes(q.toLowerCase())))
        .map((l: any) => ({ doc_id: l.doc_id, region: l.region, section: l.section, substance: l.substance, brand: l.brand, events: l.events.length, chars: l.text.length }))
        .sort((x: any, y: any) => (x.substance || x.brand || "zzz").toLowerCase().localeCompare((y.substance || y.brand || "zzz").toLowerCase()) || x.section.localeCompare(y.section))
        .slice(0, 400),
    label: async (docId) => {
      const l = labelsById.get(docId);
      if (!l) throw new Error("unknown label section");
      return labelView(l, reactions, (d) => byDrug.get(d) || []);
    },
    interactions: async (list) => {
      const res = checkRegimen(list, graph, pk.mechanisms, ddi);
      log("/api/interactions", null, { redacted: list.join(","), drugs: res.drugs });
      return res;
    },
    caseIntake: async (narrative) => {
      const res = intake(narrative, graph, drugs, reactions);
      log("/api/case/intake", null, { redacted: res.redacted_narrative.slice(0, 500), redactions: res.redactions, drugs: res.suspect_drugs, reactions: res.events });
      return res;
    },
    evaluation: async () => evaluation,
    audit: async () => ({ stats: { entries: audit.length }, entries: audit.slice(0, 100) }),
    document: async (docId) => {
      const idx = retriever.docToIdx.get(docId) || [];
      if (!idx.length) return { doc_id: docId, found: false };
      const ps = idx.map((i) => passages[i]);
      return { doc_id: docId, found: true, title: ps[0].title, source_type: ps[0].source_type, url: ps[0].url, passages: ps.map((p) => ({ pid: p.pid, section: p.section, text: p.text })) };
    },
    figureUrl: (name) => `${BASE}figures/${name}`,
  };
  return engine;
}

function supportedShare(res: any): number | null {
  const s = (res?.answer || []).filter((x: any) => x.verification && x.verification.status !== "not_applicable");
  if (!s.length) return null;
  return s.filter((x: any) => x.verification.status === "supported").length / s.length;
}

function groupBy<T>(xs: T[], f: (x: T) => string): Map<string, T[]> {
  const m = new Map<string, T[]>();
  for (const x of xs) (m.get(f(x)) || m.set(f(x), []).get(f(x))!).push(x);
  return m;
}
