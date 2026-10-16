import { useEffect, useMemo, useState } from "react";
import { IntervalRow, SignalScatter, TwoByTwo } from "../components/charts";
import { ErrorNote, fmt, int, navigate, Spinner, title, useAsync, useDebounced, useEngine } from "../components/ui";

export default function Signals({ initialDataset, initialDrug }: { initialDataset: string; initialDrug: string }) {
  const engine = useEngine();
  const ds = useAsync(() => engine.datasets(), [engine]);
  const [dataset, setDataset] = useState(initialDataset);
  const [drug, setDrug] = useState(initialDrug);
  const [onlySignals, setOnlySignals] = useState(false);
  const [unlabelled, setUnlabelled] = useState(false);
  const [hideClusters, setHideClusters] = useState(true);
  const [minCases, setMinCases] = useState(3);
  const [soc, setSoc] = useState("");
  const [term, setTerm] = useState("");
  const dterm = useDebounced(term, 250);
  const [sel, setSel] = useState<any | null>(null);

  useEffect(() => {
    if (!ds.data?.length) return;
    const d = ds.data.find((x: any) => x.dataset === dataset) || ds.data.find((x: any) => x.drugs.includes(initialDrug)) || ds.data[0];
    if (d.dataset !== dataset) setDataset(d.dataset);
    if (!d.drugs.includes(drug)) setDrug(d.drugs.includes(initialDrug) ? initialDrug : d.drugs[0]);
  }, [ds.data, dataset]); // eslint-disable-line react-hooks/exhaustive-deps

  const meta = ds.data?.find((x: any) => x.dataset === dataset);
  const rows = useAsync(
    () => (dataset && drug ? engine.signals({ dataset, drug, min_cases: minCases, only_signals: onlySignals, unlabelled, hide_clusters: hideClusters, soc, q: dterm, limit: 2000 }) : Promise.resolve(null)),
    [engine, dataset, drug, minCases, onlySignals, unlabelled, hideClusters, soc, dterm],
  );
  useEffect(() => setSel(null), [dataset, drug]);

  const points = useMemo(
    () =>
      (rows.data?.rows || []).map((r: any) => ({
        id: r.pt,
        x: r.a,
        y: r.ror,
        highlight: r.eb_signal,
        label: r.pt,
        tip: (
          <div>
            <strong>{r.pt}</strong>
            <div>
              {int(r.a)} cases, ROR {fmt(r.ror, 1)}, EB05 {fmt(r.eb05, 2)}
            </div>
            <div>{r.labelled ? "Listed in labels" : r.label_known ? "Not listed in label references" : "No label reference for this drug"}</div>
          </div>
        ),
      })),
    [rows.data],
  );

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Signal explorer</h1>
          <p>Disproportionality for every drug and MedDRA preferred term in four public FAERS extracts, scored with PRR, ROR, the BCPNN information component and the empirical Bayes geometric mean, and compared with what labels already list.</p>
        </div>
      </div>
      {ds.error && <ErrorNote error={ds.error} />}
      <div className="panel panel-pad" style={{ marginBottom: 16 }}>
        <div className="row" style={{ gap: 14 }}>
          <label className="small muted">
            Dataset{" "}
            <select className="select" value={dataset} onChange={(e) => setDataset(e.target.value)}>
              {ds.data?.map((d: any) => (
                <option key={d.dataset} value={d.dataset}>
                  {title(d.dataset.replace(/_/g, " "))}
                </option>
              ))}
            </select>
          </label>
          <label className="small muted">
            Drug{" "}
            <select className="select" value={drug} onChange={(e) => setDrug(e.target.value)}>
              {meta?.drugs.map((d: string) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
          <label className="small muted">
            Minimum cases{" "}
            <input className="input" type="number" min={0} style={{ width: 80 }} value={minCases} onChange={(e) => setMinCases(Number(e.target.value) || 0)} />
          </label>
          <label className="small muted">
            System organ class{" "}
            <select className="select" value={soc} onChange={(e) => setSoc(e.target.value)} style={{ maxWidth: 260 }}>
              <option value="">All</option>
              {rows.data?.socs?.map((s: string) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <input className="input" placeholder="Filter preferred terms" value={term} onChange={(e) => setTerm(e.target.value)} aria-label="Filter preferred terms" />
        </div>
        <div className="row" style={{ marginTop: 10, gap: 18 }}>
          <label className="check">
            <input type="checkbox" checked={onlySignals} onChange={(e) => setOnlySignals(e.target.checked)} /> EB05 of 2 or more only
          </label>
          <label className="check">
            <input type="checkbox" checked={unlabelled} onChange={(e) => setUnlabelled(e.target.checked)} /> Not listed in labels
          </label>
          <label className="check">
            <input type="checkbox" checked={hideClusters} onChange={(e) => setHideClusters(e.target.checked)} /> Hide suspected report clusters
          </label>
          <span className="spacer" />
          {meta && <span className="tiny faint">{meta.note}</span>}
        </div>
      </div>
      {rows.loading && <Spinner label="Scoring" />}
      {rows.data && (
        <div className="split">
          <section className="stack">
            <div className="panel panel-pad">
              <div className="row">
                <h2 style={{ margin: 0 }}>
                  {title(drug)}: {int(rows.data.total)} preferred terms
                </h2>
                <span className="spacer" />
                <span className="row tiny muted" style={{ gap: 12 }}>
                  <span className="row" style={{ gap: 5 }}>
                    <span className="dot" style={{ background: "var(--series-2)" }} /> EB05 of 2 or more
                  </span>
                  <span className="row" style={{ gap: 5 }}>
                    <span className="dot" style={{ background: "var(--muted-mark)" }} /> Below threshold
                  </span>
                </span>
              </div>
              <SignalScatter points={points} xLabel="Drug and event reports (log scale)" yLabel="Reporting odds ratio (log scale)" onPick={(id) => setSel(rows.data.rows.find((r: any) => r.pt === id))} selected={sel?.pt} />
            </div>
          </section>
          <aside className="stack" style={{ position: "sticky", top: 16 }}>
            {sel ? <SignalDetail r={sel} /> : <div className="panel panel-pad muted small">Select a point or a row to see its two by two table, every measure with its interval and how it compares with the label.</div>}
          </aside>
        </div>
      )}
      {rows.data && (
        <div style={{ marginTop: 18 }}>
            <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Preferred term</th>
                  <th>System organ class</th>
                  <th className="r">Cases</th>
                  <th className="r">Expected</th>
                  <th className="r">ROR</th>
                  <th className="r">IC025</th>
                  <th className="r">EB05</th>
                  <th>Label</th>
                </tr>
              </thead>
              <tbody>
                {rows.data.rows.slice(0, 400).map((r: any) => (
                  <tr key={r.pt} className={`clickable ${sel?.pt === r.pt ? "selected" : ""}`} onClick={() => setSel(r)}>
                    <td>
                      {r.pt}
                      {r.cluster_flag && <span className="chip" style={{ marginLeft: 6 }} title="Part of a cluster of near identical counts">cluster</span>}
                    </td>
                    <td className="small muted">{r.soc}</td>
                    <td className="r">{int(r.a)}</td>
                    <td className="r">{fmt(r.expected, 1)}</td>
                    <td className="r">{fmt(r.ror, 2)}</td>
                    <td className="r">{fmt(r.ic025, 2)}</td>
                    <td className="r">{r.eb_signal ? <span className="chip signal">{fmt(r.eb05, 2)}</span> : fmt(r.eb05, 2)}</td>
                    <td className="small">{r.labelled ? "Listed" : r.label_known ? <strong>Not listed</strong> : <span className="faint">No reference</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function SignalDetail({ r }: { r: any }) {
  const votes = [
    ["Evans criteria (PRR at least 2, chi square at least 4, three cases)", r.evans],
    ["ROR lower 95% limit above 1", r.ror_signal],
    ["IC025 above 0", r.ic_signal],
    ["EB05 at least 2", r.eb_signal],
  ];
  return (
    <div className="panel panel-pad stack">
      <div>
        <div className="small faint">{r.soc}</div>
        <h2 style={{ margin: "2px 0 0", fontSize: 18 }}>
          {r.pt} with {r.drug}
        </h2>
      </div>
      <TwoByTwo a={r.a} b={r.b} c={r.c} d={r.d} drug={r.drug} pt={r.pt} />
      <div>
        <IntervalRow name="PRR" est={r.prr} lo={r.prr_lo} hi={r.prr_hi} threshold="Evans: at least 2" />
        <IntervalRow name="ROR" est={r.ror} lo={r.ror_lo} hi={r.ror_hi} threshold="Lower limit above 1" />
        <IntervalRow name="EBGM" est={r.ebgm} lo={r.eb05} hi={r.eb95} threshold="EB05 at least 2" />
        <IntervalRow name="IC (log2)" est={r.ic} lo={r.ic025} hi={r.ic975} nullValue={0} log={false} threshold="IC025 above 0" />
      </div>
      <div className="small">
        {votes.map(([label, ok]) => (
          <div key={label as string} className="row" style={{ gap: 8 }}>
            <span className={`chip ${ok ? "signal" : ""}`} style={{ minWidth: 48, justifyContent: "center" }}>
              {ok ? "Signal" : "No"}
            </span>
            {label}
          </div>
        ))}
      </div>
      <div className="small">
        {r.labelled ? (
          <span>Listed in label derived references, so this is an expected reaction.</span>
        ) : r.label_known ? (
          <span>
            <strong>Not listed</strong> in label derived references for this drug. If the signal holds up, review the individual cases for timing, dechallenge and alternative causes.
          </span>
        ) : (
          <span className="muted">The label references do not cover this drug, so expectedness cannot be judged here.</span>
        )}
      </div>
      {r.cluster_flag && <div className="notice">This term sits in a cluster of five or more terms with near identical counts and high disproportionality, a pattern typical of duplicated or mass submitted reports. Check deduplication before acting.</div>}
      <div className="row">
        <button className="btn small" onClick={() => navigate(`/copilot?q=${encodeURIComponent(`Is ${r.pt.toLowerCase()} a known adverse reaction of ${r.drug}?`)}`)}>
          Ask the copilot
        </button>
        <button className="btn ghost small" onClick={() => navigate(`/drug/${encodeURIComponent(r.drug)}`)}>
          Drug profile
        </button>
        <button className="btn ghost small" onClick={() => navigate(`/calculator?a=${r.a}`)}>
          Open in calculator
        </button>
      </div>
    </div>
  );
}
