import { useState } from "react";
import { ForceGraph } from "../components/charts";
import { BarList, EntityInput, ErrorNote, fmt, int, Kpis, navigate, Spinner, Tabs, title, useAsync, useEngine } from "../components/ui";

const POPULAR = ["warfarin", "simvastatin", "clozapine", "lamotrigine", "dexmedetomidine", "nirmatrelvir ritonavir", "amiodarone", "methotrexate"];

export default function DrugProfile({ name }: { name: string }) {
  const engine = useEngine();
  const [tab, setTab] = useState("safety");
  const { data, error, loading } = useAsync(() => (name ? engine.drug(name) : Promise.resolve(null)), [engine, name]);
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>{data ? title(data.drug) : "Drug safety profile"}</h1>
          <p>
            {data
              ? [data.entry?.atc?.[0] && `ATC ${data.entry.atc[0]}`, data.entry?.atc_classes?.[1]?.split(" ").slice(1).join(" "), data.entry?.brands?.length ? `brands: ${data.entry.brands.slice(0, 4).join(", ")}` : null].filter(Boolean).join(", ") || "Everything the knowledge base holds about this drug."
              : "Labelled reactions, FAERS signals, case reports, literature, interactions and classes for one drug, with the provenance of every link."}
          </p>
        </div>
        <div style={{ width: 340 }}>
          <EntityInput placeholder="Find a drug or brand" onPick={(n) => navigate(`/drug/${encodeURIComponent(n)}`)} autoFocus={!name} />
        </div>
      </div>
      {!name && (
        <div className="row">
          <span className="small muted">Try</span>
          {POPULAR.map((p) => (
            <button key={p} className="example" onClick={() => navigate(`/drug/${encodeURIComponent(p)}`)}>
              {p}
            </button>
          ))}
        </div>
      )}
      {loading && name && <Spinner label="Building profile" />}
      {error && <ErrorNote error={error} />}
      {data && <Profile data={data} tab={tab} setTab={setTab} />}
    </div>
  );
}

function Profile({ data, tab, setTab }: { data: any; tab: string; setTab: (t: string) => void }) {
  const p = data.profile;
  if (!p.found) return <div className="notice info">This drug is in the dictionary but has no graph relations yet. Try the copilot for literature.</div>;
  const c = p.counts || {};
  return (
    <div className="stack" style={{ gap: 18 }}>
      <Kpis
        items={[
          { label: "Reactions listed in labels", value: int(c["Listed in labels"] || 0) },
          { label: "FAERS disproportionality links", value: int(c["FAERS disproportionality"] || 0) },
          { label: "Reactions in case reports", value: int(c["Case reports"] || 0) },
          { label: "Literature reactions", value: int(c["Literature (chemical induced disease)"] || 0) },
          { label: "Documented interactions", value: int(c["Documented interaction"] || 0) },
          { label: "Annotated label sections", value: int(data.labels.length) },
        ]}
      />
      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { id: "safety", label: "Safety evidence" },
          { id: "interactions", label: "Interactions" },
          { id: "graph", label: "Graph" },
          { id: "about", label: "Classification" },
        ]}
      />
      {tab === "safety" && (
        <div className="grid g2">
          <section className="panel panel-pad">
            <h2>Labelled reactions by system organ class</h2>
            {Object.keys(p.labelled_by_soc).length ? (
              <BarList rows={Object.entries(p.labelled_by_soc).slice(0, 14).map(([k, v]) => ({ label: k, value: v as number }))} />
            ) : (
              <p className="small muted">No label derived reactions are recorded for this drug in SIDER or the annotated labels.</p>
            )}
            {data.labels.length > 0 && (
              <div className="small" style={{ marginTop: 14 }}>
                Annotated label sections:{" "}
                {Object.entries(
                  data.labels.reduce((acc: Record<string, any[]>, l: any) => {
                    const key = `${l.region} ${l.section.toLowerCase()}`;
                    (acc[key] = acc[key] || []).push(l);
                    return acc;
                  }, {}),
                ).map(([key, ls]: [string, any], gi: number, groups: any[]) => (
                  <span key={key}>
                    {key}
                    {ls.length > 1 ? ` (${ls.length} products: ` : " ("}
                    {ls.map((l: any, i: number) => (
                      <span key={l.doc_id}>
                        <a href={`#/labels/${encodeURIComponent(l.doc_id)}`}>{l.brand || (ls.length > 1 ? i + 1 : "open")}</a>
                        {i < ls.length - 1 ? ", " : ""}
                      </span>
                    ))}
                    {")"}
                    {gi < groups.length - 1 ? "; " : ""}
                  </span>
                ))}
              </div>
            )}
          </section>
          <section className="panel panel-pad">
            <div className="row">
              <h2 style={{ margin: 0 }}>FAERS signals</h2>
              <span className="spacer" />
              {data.faers.map((f: any) => (
                <button key={f.dataset} className="btn ghost small" onClick={() => navigate(`/signals?dataset=${f.dataset}&drug=${encodeURIComponent(data.drug)}`)}>
                  Explore {f.dataset.replace(/_/g, " ")}
                </button>
              ))}
            </div>
            {p.faers_signals.length === 0 ? (
              <p className="small muted">This drug is not in the four FAERS extracts used here.</p>
            ) : (
              <table className="data" style={{ marginTop: 10 }}>
                <thead>
                  <tr>
                    <th>Reaction</th>
                    <th className="r">Cases</th>
                    <th className="r">EB05</th>
                    <th>Label</th>
                  </tr>
                </thead>
                <tbody>
                  {p.faers_signals.slice(0, 14).map((s: any) => (
                    <tr key={s.reaction}>
                      <td>{s.reaction}</td>
                      <td className="r">{int(s.cases)}</td>
                      <td className="r">{s.eb05 >= 2 ? <span className="chip signal">{fmt(s.eb05, 1)}</span> : fmt(s.eb05, 1)}</td>
                      <td className="small">{s.labelled ? "Listed" : "Not listed"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
          <section className="panel panel-pad">
            <h2>Reactions described in case reports</h2>
            {p.case_reported.length === 0 ? (
              <p className="small muted">No annotated case reports for this drug.</p>
            ) : (
              <BarList rows={p.case_reported.slice(0, 12).map((x: any) => ({ label: x.reaction, value: x.reports }))} color="var(--series-2)" onClick={(r) => navigate(`/copilot?q=${encodeURIComponent(`Case reports of ${r} with ${data.drug}`)}`)} />
            )}
          </section>
          <section className="panel panel-pad">
            <h2>Chemical induced disease in the literature</h2>
            {p.literature.length === 0 ? (
              <p className="small muted">No BioCreative CDR annotations for this drug.</p>
            ) : (
              <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
                {p.literature.slice(0, 12).map((x: any) => (
                  <li key={x.reaction}>
                    {x.reaction}{" "}
                    {x.pmids.slice(0, 3).map((id: string) => (
                      <a key={id} href={`https://pubmed.ncbi.nlm.nih.gov/${id}/`} target="_blank" rel="noreferrer" style={{ marginRight: 6 }}>
                        PMID {id}
                      </a>
                    ))}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}
      {tab === "interactions" && (
        <section className="panel panel-pad">
          <h2>Documented interactions (DDI corpus)</h2>
          {p.interactions.length === 0 ? (
            <p className="small muted">No interactions annotated for this drug.</p>
          ) : (
            <table className="data">
              <thead>
                <tr>
                  <th>With</th>
                  <th>Interaction types</th>
                  <th className="r">Annotations</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {p.interactions.map((x: any) => (
                  <tr key={x.drug}>
                    <td>{x.drug}</td>
                    <td className="small">{x.types.join(", ") || "unspecified"}</td>
                    <td className="r">{x.evidence}</td>
                    <td>
                      <button className="btn ghost small" onClick={() => navigate(`/interactions?drugs=${encodeURIComponent(`${data.drug},${x.drug}`)}`)}>
                        Check pair
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}
      {tab === "graph" && <ForceGraph graph={data.subgraph} center={`drug:${data.drug}`} onNode={(n) => n.kind === "drug" && navigate(`/drug/${encodeURIComponent(n.name)}`)} />}
      {tab === "about" && (
        <div className="grid g3">
          <section className="panel panel-pad">
            <h2>Classes</h2>
            <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
              {(data.entry?.atc_classes || []).map((c: string) => <li key={c}>{c}</li>)}
              {p.classes.map((c: string) => <li key={c}>{c}</li>)}
            </ul>
          </section>
          <section className="panel panel-pad">
            <h2>Indications</h2>
            {p.indications.length ? <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>{p.indications.map((c: string) => <li key={c}>{c}</li>)}</ul> : <p className="small muted">None recorded.</p>}
          </section>
          <section className="panel panel-pad">
            <h2>Molecular targets</h2>
            <p className="small">{p.targets.join(", ") || "None recorded."}</p>
          </section>
        </div>
      )}
    </div>
  );
}
