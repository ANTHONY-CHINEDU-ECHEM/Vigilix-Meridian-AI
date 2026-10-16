import { useState } from "react";
import { ForceGraph } from "../components/charts";
import { EntityInput, ErrorNote, navigate, Spinner, title, useAsync, useEngine } from "../components/ui";

export default function GraphExplorer({ name }: { name: string }) {
  const engine = useEngine();
  const drug = name || "simvastatin";
  const { data, error, loading } = useAsync(() => engine.drug(drug), [engine, drug]);
  const [picked, setPicked] = useState<any>(null);
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Knowledge graph</h1>
          <p>
            The pharmacovigilance graph links 21 thousand drugs, reactions, classes, indications and targets through 194 thousand edges, each with its source. Click a drug to move the centre; click a reaction to see which drugs share it.
          </p>
        </div>
        <div style={{ width: 340 }}>
          <EntityInput placeholder="Centre on a drug" onPick={(n) => navigate(`/graph/${encodeURIComponent(n)}`)} />
        </div>
      </div>
      {loading && <Spinner label="Laying out the neighbourhood" />}
      {error && <ErrorNote error={error} />}
      {data && (
        <div className="split">
          <ForceGraph
            graph={data.subgraph}
            center={`drug:${data.drug}`}
            height={600}
            onNode={(n) => {
              if (n.kind === "drug" && n.name !== data.drug) navigate(`/graph/${encodeURIComponent(n.name)}`);
              else if (n.kind === "reaction") setPicked(n);
            }}
          />
          <aside className="stack">
            <div className="panel panel-pad">
              <h2>{title(data.drug)}</h2>
              <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
                {Object.entries(data.profile.counts || {}).map(([k, v]) => (
                  <li key={k}>
                    {k}: <strong className="num">{String(v)}</strong>
                  </li>
                ))}
              </ul>
              <div className="row" style={{ marginTop: 12 }}>
                <button className="btn small" onClick={() => navigate(`/drug/${encodeURIComponent(data.drug)}`)}>
                  Full profile
                </button>
              </div>
            </div>
            {picked && <ReactionPanel name={picked.name} drug={data.drug} />}
          </aside>
        </div>
      )}
    </div>
  );
}

function ReactionPanel({ name, drug }: { name: string; drug: string }) {
  const engine = useEngine();
  const { data, loading } = useAsync(() => engine.reaction(name), [engine, name]);
  return (
    <div className="panel panel-pad">
      <h2>{title(name)}</h2>
      {loading && <Spinner />}
      {data?.profile?.found && (
        <>
          <div className="small muted" style={{ marginBottom: 8 }}>
            {data.profile.soc}. Linked to {data.profile.total_drugs} drugs; those with the most kinds of evidence:
          </div>
          <table className="data">
            <tbody>
              {data.profile.drugs.slice(0, 12).map((d: any) => (
                <tr key={d.drug} className="clickable" onClick={() => navigate(`/graph/${encodeURIComponent(d.drug)}`)}>
                  <td style={{ fontWeight: d.drug === drug ? 700 : 400 }}>{d.drug}</td>
                  <td className="small muted">{d.relations.map((r: string) => r.replace(/_/g, " ")).join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <button className="btn ghost small" style={{ marginTop: 10 }} onClick={() => navigate(`/copilot?q=${encodeURIComponent(`Is ${name} a known adverse reaction of ${drug}?`)}`)}>
            Ask the copilot
          </button>
        </>
      )}
    </div>
  );
}
