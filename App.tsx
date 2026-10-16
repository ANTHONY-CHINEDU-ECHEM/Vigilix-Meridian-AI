import { lazy, Suspense, useEffect, useState } from "react";
import { EngineContext, Spinner, useAsync, useEngineLoader } from "./components/ui";
import Overview from "./pages/Overview";

const Copilot = lazy(() => import("./pages/Copilot"));
const Signals = lazy(() => import("./pages/Signals"));
const Calculator = lazy(() => import("./pages/Calculator"));
const DrugProfile = lazy(() => import("./pages/DrugProfile"));
const GraphExplorer = lazy(() => import("./pages/GraphExplorer"));
const Labels = lazy(() => import("./pages/Labels"));
const Interactions = lazy(() => import("./pages/Interactions"));
const CaseIntake = lazy(() => import("./pages/CaseIntake"));
const Evaluation = lazy(() => import("./pages/Evaluation"));
const Audit = lazy(() => import("./pages/Audit"));

const I = {
  home: "M3 10.5 12 3l9 7.5V21h-6v-6H9v6H3z",
  ask: "M4 5h16v11H8l-4 4zM8 9h8M8 12h5",
  signal: "M3 20h18M6 16l3-6 4 3 5-9",
  calc: "M5 3h14v18H5zM8 7h8M8 11h2M12 11h2M16 11h0M8 15h2M12 15h2M8 18h8",
  drug: "M7 17 17 7a3.5 3.5 0 0 0-5-5L2 12a3.5 3.5 0 0 0 5 5zM7 7l5 5",
  graph: "M6 6m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0M18 6m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0M12 18m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0M7.5 7.5l3.5 9M16.5 7.5l-3.5 9M8 6h8",
  label: "M6 3h9l4 4v14H6zM9 9h7M9 13h7M9 17h4",
  mix: "M9 3v6l-5 9a2 2 0 0 0 2 3h12a2 2 0 0 0 2-3l-5-9V3M8 3h8",
  case: "M4 7h16v13H4zM9 7V4h6v3M12 11v5M9.5 13.5h5",
  check: "M4 12l5 5L20 6",
  log: "M5 4h14v16H5zM8 8h8M8 12h8M8 16h5",
};

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}

const NAV = [
  { group: "Ask", items: [
    { path: "/", label: "Overview", icon: I.home },
    { path: "/copilot", label: "Evidence copilot", icon: I.ask },
  ] },
  { group: "Detect", items: [
    { path: "/signals", label: "Signal explorer", icon: I.signal },
    { path: "/calculator", label: "Disproportionality calculator", icon: I.calc },
    { path: "/labels", label: "Label intelligence", icon: I.label },
  ] },
  { group: "Assess", items: [
    { path: "/drug", label: "Drug safety profile", icon: I.drug },
    { path: "/graph", label: "Knowledge graph", icon: I.graph },
    { path: "/interactions", label: "Interaction checker", icon: I.mix },
    { path: "/case", label: "Case intake and causality", icon: I.case },
  ] },
  { group: "Govern", items: [
    { path: "/evaluation", label: "Evaluation and governance", icon: I.check },
    { path: "/audit", label: "Audit log", icon: I.log },
  ] },
];

function parseHash(): { path: string; arg: string; params: URLSearchParams } {
  const raw = location.hash.replace(/^#/, "") || "/";
  const [p, q] = raw.split("?");
  const parts = p.split("/").filter(Boolean);
  return { path: "/" + (parts[0] || ""), arg: decodeURIComponent(parts.slice(1).join("/")), params: new URLSearchParams(q || "") };
}

function Mark() {
  return (
    <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
      <rect x="1" y="1" width="30" height="30" rx="7" fill="#14202b" stroke="var(--rule-strong)" strokeWidth="1" />
      <path d="M8 22 L12.5 13 L16 19 L19.5 9 L24 22" fill="none" stroke="var(--signal)" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="19.5" cy="9" r="2.4" fill="var(--signal)" />
    </svg>
  );
}

export default function App() {
  const { engine, error } = useEngineLoader();
  const [route, setRoute] = useState(parseHash());
  const [open, setOpen] = useState(false);
  const [theme, setTheme] = useState<string | null>(() => {
    try {
      return localStorage.getItem("vigilix-theme");
    } catch {
      return null;
    }
  });
  useEffect(() => {
    const h = () => {
      setRoute(parseHash());
      setOpen(false);
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", h);
    return () => window.removeEventListener("hashchange", h);
  }, []);
  useEffect(() => {
    if (theme) document.documentElement.dataset.theme = theme;
    else delete document.documentElement.dataset.theme;
    try {
      theme ? localStorage.setItem("vigilix-theme", theme) : localStorage.removeItem("vigilix-theme");
    } catch {
      /* storage unavailable */
    }
  }, [theme]);

  if (error) return <div className="page"><div className="notice crisis">The engine could not start: {error}</div></div>;
  if (!engine)
    return (
      <div className="page" style={{ display: "grid", placeItems: "center", minHeight: "80vh" }}>
        <div className="stack" style={{ alignItems: "center" }}>
          <Mark />
          <Spinner label="Loading the pharmacovigilance knowledge base" />
        </div>
      </div>
    );

  const page = (() => {
    switch (route.path) {
      case "/copilot": return <Copilot initial={route.params.get("q") || ""} />;
      case "/signals": return <Signals initialDataset={route.params.get("dataset") || ""} initialDrug={route.params.get("drug") || ""} />;
      case "/calculator": return <Calculator />;
      case "/drug": return <DrugProfile name={route.arg} />;
      case "/graph": return <GraphExplorer name={route.arg} />;
      case "/labels": return <Labels docId={route.arg} />;
      case "/interactions": return <Interactions initial={route.params.get("drugs") || ""} />;
      case "/case": return <CaseIntake />;
      case "/evaluation": return <Evaluation />;
      case "/audit": return <Audit />;
      default: return <Overview />;
    }
  })();

  return (
    <EngineContext.Provider value={engine}>
      <div className="mobile-bar">
        <button className="btn ghost small" onClick={() => setOpen(!open)} aria-expanded={open} aria-controls="rail">
          Menu
        </button>
        <Mark />
        <strong>Vigilix Meridian</strong>
      </div>
      <div className="shell">
        <nav className={`rail ${open ? "open" : ""}`} id="rail" aria-label="Workspaces">
          <a href="#/" className="brand" style={{ textDecoration: "none", color: "inherit" }}>
            <Mark />
            <div>
              <div className="brand-name">Vigilix Meridian</div>
              <div className="brand-sub">Pharmacovigilance intelligence</div>
            </div>
          </a>
          {NAV.map((g) => (
            <div className="nav-group" key={g.group}>
              <div className="nav-group-title">{g.group}</div>
              {g.items.map((it) => (
                <button key={it.path} className="nav-item" aria-current={route.path === it.path ? "page" : undefined} onClick={() => (location.hash = it.path)}>
                  <Icon d={it.icon} />
                  {it.label}
                </button>
              ))}
            </div>
          ))}
          <div className="rail-foot">
            <EngineBadge />
            <div className="row">
              <button className="theme-toggle" onClick={() => setTheme(theme === "dark" ? "light" : theme === "light" ? null : "dark")}>
                Theme: {theme ?? "system"}
              </button>
            </div>
            <div>Research tool. Not a medical device and not for individual treatment decisions.</div>
          </div>
        </nav>
        <main className="main" id="main">
          <Suspense fallback={<div className="page"><Spinner /></div>}>{page}</Suspense>
        </main>
      </div>
    </EngineContext.Provider>
  );
}

function EngineBadge() {
  const { data } = useAsync(async () => {
    const { getEngine } = await import("./api");
    const e = await getEngine();
    return { mode: e.mode, health: await e.health() };
  }, []);
  if (!data) return null;
  const server = data.mode === "server";
  return (
    <div className="engine-pill" title={data.health?.engine_reason}>
      <span className={`dot ${server ? "" : "browser"}`} />
      {server ? `Server engine, ${data.health?.engine === "llm" ? "local model" : "extractive writer"}` : "Browser engine (offline demo)"}
    </div>
  );
}
