// One contract, two engines. The interface calls these functions; they go to
// the FastAPI service when it is reachable and to the in browser engine
// (src/engine) otherwise, or when the page is opened with ?engine=browser.

export type Json = any;

export interface Engine {
  mode: "server" | "browser";
  health(): Promise<Json>;
  overview(): Promise<Json>;
  ask(question: string, engine?: string): Promise<Json>;
  search(query: string, mode?: string): Promise<Json>;
  suggest(q: string, kind?: "drug" | "reaction"): Promise<Json[]>;
  drug(name: string): Promise<Json>;
  reaction(name: string): Promise<Json>;
  datasets(): Promise<Json[]>;
  signals(params: Record<string, string | number | boolean | undefined>): Promise<Json>;
  compute(a: number, b: number, c: number, d: number, dataset?: string): Promise<Json>;
  labels(region?: string, q?: string): Promise<Json[]>;
  label(docId: string): Promise<Json>;
  interactions(drugs: string[]): Promise<Json>;
  caseIntake(narrative: string): Promise<Json>;
  evaluation(): Promise<Json>;
  audit(): Promise<Json>;
  document(docId: string): Promise<Json>;
  figureUrl(name: string): string;
}

async function http(path: string, init?: RequestInit): Promise<Json> {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`${r.status} ${text.slice(0, 200)}`);
  }
  return r.json();
}

const qs = (p: Record<string, any>) =>
  new URLSearchParams(Object.entries(p).filter(([, v]) => v !== undefined && v !== "" && v !== false).map(([k, v]) => [k, String(v)])).toString();

export const serverEngine: Engine = {
  mode: "server",
  health: () => http("/api/health"),
  overview: () => http("/api/overview"),
  ask: (question, engine) => http("/api/ask", { method: "POST", body: JSON.stringify({ question, engine }) }),
  search: (query, mode = "full") => http("/api/search", { method: "POST", body: JSON.stringify({ query, mode, k: 10 }) }),
  suggest: (q, kind = "drug") => http(`/api/suggest?${qs({ q, kind })}`),
  drug: (name) => http(`/api/drugs/${encodeURIComponent(name)}`),
  reaction: (name) => http(`/api/reactions/${encodeURIComponent(name)}`),
  datasets: () => http("/api/signals/datasets"),
  signals: (params) => http(`/api/signals?${qs(params)}`),
  compute: (a, b, c, d, dataset) => http("/api/signals/compute", { method: "POST", body: JSON.stringify({ a, b, c, d, dataset }) }),
  labels: (region, q) => http(`/api/labels?${qs({ region, q })}`),
  label: (docId) => http(`/api/labels/${encodeURIComponent(docId)}`),
  interactions: (drugs) => http("/api/interactions", { method: "POST", body: JSON.stringify({ drugs }) }),
  caseIntake: (narrative) => http("/api/case/intake", { method: "POST", body: JSON.stringify({ narrative }) }),
  evaluation: () => http("/api/evaluation"),
  audit: () => http("/api/audit"),
  document: (docId) => http(`/api/documents/${encodeURIComponent(docId)}`),
  figureUrl: (name) => `/api/figures/${name}`,
};

let chosen: Promise<Engine> | null = null;

export function getEngine(): Promise<Engine> {
  if (chosen) return chosen;
  chosen = (async () => {
    const forced = new URLSearchParams(location.search).get("engine");
    if (forced !== "browser") {
      try {
        const ctrl = new AbortController();
        const t = setTimeout(() => ctrl.abort(), 2500);
        const r = await fetch("/api/health", { signal: ctrl.signal });
        clearTimeout(t);
        if (r.ok && (r.headers.get("content-type") || "").includes("json")) return serverEngine;
      } catch {
        /* fall through to the browser engine */
      }
    }
    const mod = await import("./engine");
    return mod.createBrowserEngine();
  })();
  return chosen;
}
