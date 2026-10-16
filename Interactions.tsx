import { useEffect, useState } from "react";
import { EntityInput, ErrorNote, navigate, Spinner, title, useEngine } from "../components/ui";

const PRESETS: Record<string, string[]> = {
  "Statin with a macrolide": ["simvastatin", "clarithromycin", "amlodipine"],
  "Anticoagulation and antifungal": ["warfarin", "fluconazole", "aspirin", "omeprazole"],
  "Serotonergic combination": ["sertraline", "tramadol", "linezolid"],
  "Older adult regimen": ["diazepam", "oxycodone", "diphenhydramine", "furosemide", "lisinopril", "ibuprofen"],
};
const LEVEL_CLASS: Record<string, string> = { major: "lvl-major", moderate: "lvl-moderate", minor: "lvl-minor", "none found": "lvl-none" };
const LEVEL_SHORT: Record<string, string> = { major: "Major", moderate: "Mod", minor: "Min", "none found": "None" };

export default function Interactions({ initial }: { initial: string }) {
  const engine = useEngine();
  const [drugs, setDrugs] = useState<string[]>(initial ? initial.split(",").map((s) => s.trim()).filter(Boolean) : PRESETS["Statin with a macrolide"]);
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sel, setSel] = useState<any>(null);
  useEffect(() => {
    if (drugs.length < 2) {
      setRes(null);
      return;
    }
    setBusy(true);
    setErr(null);
    engine
      .interactions(drugs)
      .then((r) => {
        setRes(r);
        setSel(r.pairs[0] || null);
      })
      .catch((e) => setErr(String(e.message || e)))
      .finally(() => setBusy(false));
  }, [drugs, engine]);
  const pair = (a: string, b: string) => res?.pairs.find((p: any) => (p.drugs[0] === a && p.drugs[1] === b) || (p.drugs[0] === b && p.drugs[1] === a));
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Interaction checker</h1>
          <p>Every pair in a medication list is checked three ways: interactions documented in DrugBank and MEDLINE texts, pharmacokinetic mechanisms (CYP450, P glycoprotein, OATP1B1, renal clearance) and pharmacodynamic overlap in serious reaction groups.</p>
        </div>
      </div>
      <div className="panel panel-pad stack">
        <div className="row">
          <EntityInput placeholder="Add a drug or brand" onPick={(n) => !drugs.includes(n) && setDrugs([...drugs, n])} />
          <button className="btn ghost" onClick={() => setDrugs([])}>
            Clear
          </button>
        </div>
        <div className="row">
          {drugs.map((d) => (
            <span key={d} className="chip drug">
              {d}
              <button aria-label={`Remove ${d}`} onClick={() => setDrugs(drugs.filter((x) => x !== d))}>
                ×
              </button>
            </span>
          ))}
        </div>
        <div className="row">
          <span className="small muted">Examples</span>
          {Object.entries(PRESETS).map(([k, v]) => (
            <button key={k} className="example" onClick={() => setDrugs(v)}>
              {k}
            </button>
          ))}
        </div>
      </div>
      {busy && <div style={{ marginTop: 16 }}><Spinner label="Checking pairs" /></div>}
      {err && <ErrorNote error={err} />}
      {res && (
        <div className="split" style={{ marginTop: 18 }}>
          <section className="stack">
            <div className="panel panel-pad">
              <h2>Pair matrix</h2>
              <div style={{ overflowX: "auto" }}>
                <table className="matrix">
                  <thead>
                    <tr>
                      <th />
                      {res.drugs.map((d: string) => (
                        <th key={d} className="rot">
                          {d}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {res.drugs.map((a: string, i: number) => (
                      <tr key={a}>
                        <th style={{ textAlign: "right" }}>{a}</th>
                        {res.drugs.map((b: string, j: number) => {
                          if (i === j) return <td key={b} className="lvl-self" />;
                          const p = pair(a, b);
                          return (
                            <td key={b} className={LEVEL_CLASS[p?.level || "none found"]} onClick={() => setSel(p)} title={`${a} with ${b}: ${p?.level}`} style={{ outline: sel === p ? "2px solid var(--ink)" : undefined }}>
                              {LEVEL_SHORT[p?.level || "none found"]}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="row small muted" style={{ marginTop: 10 }}>
                {Object.entries(res.summary).map(([k, v]) => (
                  <span key={k} className="row" style={{ gap: 6 }}>
                    <span className={LEVEL_CLASS[k]} style={{ width: 12, height: 12, borderRadius: 3, display: "inline-block" }} />
                    {title(k)}: {String(v)}
                  </span>
                ))}
              </div>
            </div>
            <div className="panel panel-pad">
              <h2>Cumulative burden across the whole list</h2>
              {res.cumulative_burden.length === 0 ? (
                <p className="small muted">No serious reaction group is shared by two or more of these drugs in the label references.</p>
              ) : (
                <table className="data">
                  <tbody>
                    {res.cumulative_burden.map((g: any) => (
                      <tr key={g.group}>
                        <td style={{ fontWeight: 600 }}>
                          {g.group} {g.high_risk && <span className="chip bad">high risk</span>}
                        </td>
                        <td className="small">{g.drugs.join(", ")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {res.unknown.length > 0 && <p className="small muted">Not in the graph: {res.unknown.join(", ")}.</p>}
              <p className="tiny faint" style={{ marginBottom: 0 }}>{res.disclaimer}</p>
            </div>
          </section>
          <aside>{sel ? <PairDetail p={sel} /> : <div className="panel panel-pad muted small">Select a cell to see the evidence for that pair.</div>}</aside>
        </div>
      )}
    </div>
  );
}

function PairDetail({ p }: { p: any }) {
  return (
    <div className="panel panel-pad stack">
      <div className="row">
        <h2 style={{ margin: 0, fontSize: 18 }}>
          {p.drugs[0]} with {p.drugs[1]}
        </h2>
        <span className="spacer" />
        <span className={`chip ${p.level === "major" ? "bad" : p.level === "moderate" ? "signal" : ""}`}>{title(p.level)}</span>
      </div>
      {p.reasons.length > 0 && <div className="small muted">Triage score {p.score}: {p.reasons.join("; ")}.</div>}
      <div>
        <h3>Documented interaction</h3>
        {p.documented.length === 0 ? (
          <p className="small muted">Not annotated in the DDI corpus.</p>
        ) : (
          p.documented.map((d: any, i: number) => (
            <blockquote key={i} className="small" style={{ margin: "0 0 8px", paddingLeft: 10, borderLeft: "3px solid var(--series-1)", fontFamily: "var(--font-read)" }}>
              {d.sentence}
              <div className="tiny faint" style={{ fontFamily: "var(--font-ui)" }}>
                {d.source}, type: {d.type}
              </div>
            </blockquote>
          ))
        )}
      </div>
      <div>
        <h3>Pharmacokinetic mechanism</h3>
        {p.pharmacokinetic.length === 0 ? <p className="small muted">No mechanism in the curated table.</p> : <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>{p.pharmacokinetic.map((m: any, i: number) => <li key={i}>{m.effect} ({m.mechanism})</li>)}</ul>}
      </div>
      <div>
        <h3>Shared reaction groups</h3>
        {p.pharmacodynamic.length === 0 ? (
          <p className="small muted">No shared serious reaction group.</p>
        ) : (
          <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
            {p.pharmacodynamic.map((g: any) => (
              <li key={g.group}>
                <strong>{g.group}</strong>: {p.drugs[0]} lists {g[p.drugs[0]].join(", ")}; {p.drugs[1]} lists {g[p.drugs[1]].join(", ")}
              </li>
            ))}
          </ul>
        )}
      </div>
      <button className="btn small" onClick={() => navigate(`/copilot?q=${encodeURIComponent(`What is the interaction between ${p.drugs[0]} and ${p.drugs[1]}?`)}`)}>
        Ask the copilot about this pair
      </button>
    </div>
  );
}
