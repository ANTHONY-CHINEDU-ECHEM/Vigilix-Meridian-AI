import { ReactNode, useMemo, useState } from "react";
import { ErrorNote, fmt, int, navigate, pct, Spinner, title, useAsync, useDebounced, useEngine } from "../components/ui";

const REGIONS = ["US", "UK", "EU", "US paediatric"];

export default function Labels({ docId }: { docId: string }) {
  const engine = useEngine();
  const [region, setRegion] = useState("");
  const [q, setQ] = useState("");
  const dq = useDebounced(q, 200);
  const list = useAsync(() => engine.labels(region || undefined, dq || undefined), [engine, region, dq]);
  const current = docId || list.data?.[0]?.doc_id || "";
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Label intelligence</h1>
          <p>Adverse events mined from 1,219 safety sections of US prescribing information and UK and EU summaries of product characteristics, compared with the terms human annotators marked and with FAERS signals for the same substance.</p>
        </div>
      </div>
      <div className="split" style={{ gridTemplateColumns: "minmax(0, 0.8fr) minmax(0, 2fr)" }}>
        <aside className="panel" style={{ overflow: "hidden" }}>
          <div className="panel-pad stack" style={{ gap: 8, borderBottom: "1px solid var(--rule)" }}>
            <input className="input" placeholder="Search substance or brand" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search labels" />
            <div className="row" style={{ gap: 6 }}>
              <button className={`chip ${region === "" ? "drug" : ""}`} onClick={() => setRegion("")}>
                All
              </button>
              {REGIONS.map((r) => (
                <button key={r} className={`chip ${region === r ? "drug" : ""}`} onClick={() => setRegion(r)}>
                  {r}
                </button>
              ))}
            </div>
          </div>
          <div style={{ maxHeight: 640, overflow: "auto" }}>
            {list.loading && <div className="panel-pad"><Spinner /></div>}
            {list.data?.map((l: any) => (
              <button
                key={l.doc_id}
                onClick={() => navigate(`/labels/${encodeURIComponent(l.doc_id)}`)}
                className="nav-item"
                aria-current={l.doc_id === current ? "page" : undefined}
                style={{ width: "100%", borderRadius: 0, borderBottom: "1px solid var(--rule)", display: "block", padding: "8px 14px" }}
              >
                <div style={{ fontWeight: 600, color: "var(--ink)" }}>{title(l.substance || l.brand || l.doc_id)}</div>
                <div className="tiny faint">
                  {l.region}, {l.section.toLowerCase()}, {l.events} annotated events
                </div>
              </button>
            ))}
          </div>
        </aside>
        <section>{current ? <LabelView docId={current} /> : <div className="panel panel-pad muted">No label sections match.</div>}</section>
      </div>
    </div>
  );
}

function LabelView({ docId }: { docId: string }) {
  const engine = useEngine();
  const { data, error, loading } = useAsync(() => engine.label(docId), [engine, docId]);
  const marked = useMemo(() => (data ? highlight(data.text, data.spans) : null), [data]);
  if (loading) return <Spinner label="Mining the section" />;
  if (error) return <ErrorNote error={error} />;
  if (!data) return null;
  return (
    <div className="stack">
      <div className="panel panel-pad">
        <div className="row">
          <div>
            <h2 style={{ margin: 0, fontSize: 18 }}>
              {title(data.substance || data.brand || data.label_id)} {data.brand && data.substance ? <span className="muted">({data.brand})</span> : null}
            </h2>
            <div className="small muted">
              {data.region} label, {data.section}
            </div>
          </div>
          <span className="spacer" />
          <div className="row small">
            <span className="chip ok">Precision {pct(data.precision)}</span>
            <span className="chip ok">Recall {pct(data.recall)}</span>
            {data.substance && (
              <button className="btn ghost small" onClick={() => navigate(`/drug/${encodeURIComponent(data.substance)}`)}>
                Drug profile
              </button>
            )}
          </div>
        </div>
        <div className="legend-line">
          <span>
            <mark className="term">term</mark> mined and annotated
          </span>
          <span>
            <mark className="term extra">term</mark> mined, not annotated
          </span>
          <span>
            <mark className="term neg">term</mark> mined in a negated context, ignored
          </span>
        </div>
      </div>
      <div className="panel label-text">{marked}</div>
      <div className="grid g3">
        <div className="panel panel-pad">
          <h3>Annotated but missed ({data.missed.length})</h3>
          <p className="small muted" style={{ margin: 0 }}>{data.missed.join(", ") || "None"}</p>
        </div>
        <div className="panel panel-pad">
          <h3>Mined but not annotated ({data.extra.length})</h3>
          <p className="small muted" style={{ margin: 0 }}>{data.extra.join(", ") || "None"}</p>
        </div>
        <div className="panel panel-pad">
          <h3>FAERS concordance</h3>
          {data.faers_concordance.length === 0 ? (
            <p className="small muted" style={{ margin: 0 }}>This substance is not in the FAERS extracts used here.</p>
          ) : (
            <table className="data">
              <tbody>
                {data.faers_concordance.slice(0, 12).map((c: any) => (
                  <tr key={c.term}>
                    <td>{c.term}</td>
                    <td className="r">{int(c.cases)}</td>
                    <td className="r">{c.signal ? <span className="chip signal">{fmt(c.eb05, 1)}</span> : fmt(c.eb05, 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

function highlight(text: string, spans: any[]): ReactNode[] {
  const sorted = [...spans].sort((a, b) => a.start - b.start);
  const out: ReactNode[] = [];
  let pos = 0;
  sorted.forEach((s, i) => {
    if (s.start < pos) return;
    out.push(text.slice(pos, s.start));
    out.push(
      <mark key={i} className={`term ${s.negated ? "neg" : s.gold ? "" : "extra"}`} title={s.term}>
        {text.slice(s.start, s.end)}
      </mark>,
    );
    pos = s.end;
  });
  out.push(text.slice(pos));
  return out;
}
