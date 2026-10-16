import { useEffect, useState } from "react";
import { IntervalRow, TwoByTwo } from "../components/charts";
import { fmt, Spinner, title, useAsync, useEngine } from "../components/ui";

const PRESETS = [
  { name: "Rare event, strong signal", a: 12, b: 4988, c: 240, d: 1994760 },
  { name: "Common event, mild excess", a: 900, b: 99100, c: 41000, d: 9859000 },
  { name: "Single report", a: 1, b: 2999, c: 15, d: 996985 },
];

export default function Calculator() {
  const engine = useEngine();
  const params = new URLSearchParams(location.hash.split("?")[1] || "");
  const [cells, setCells] = useState({ a: Number(params.get("a")) || 25, b: 4975, c: 1200, d: 993800 });
  const [dataset, setDataset] = useState("sedatives");
  const ds = useAsync(() => engine.datasets(), [engine]);
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setBusy(true);
    const t = setTimeout(() => engine.compute(cells.a, cells.b, cells.c, cells.d, dataset).then(setRes).finally(() => setBusy(false)), 150);
    return () => clearTimeout(t);
  }, [cells, dataset, engine]);
  const field = (k: "a" | "b" | "c" | "d", label: string) => (
    <label className="small muted stack" style={{ gap: 4 }}>
      {label}
      <input className="input num" type="number" min={0} value={cells[k]} onChange={(e) => setCells({ ...cells, [k]: Math.max(0, Number(e.target.value) || 0) })} />
    </label>
  );
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Disproportionality calculator</h1>
          <p>Enter the four cells of a reporting table and see every screening measure with its interval. EBGM shrinkage uses the gamma mixture prior fitted to one of the FAERS datasets, so small counts are pulled towards the database background.</p>
        </div>
      </div>
      <div className="split">
        <section className="panel panel-pad stack">
          <h2>Reporting table</h2>
          <div className="grid g2">
            {field("a", "a: reports with the drug and the event")}
            {field("b", "b: reports with the drug, other events")}
            {field("c", "c: other drugs with the event")}
            {field("d", "d: other drugs, other events")}
          </div>
          <label className="small muted">
            Prior for EBGM{" "}
            <select className="select" value={dataset} onChange={(e) => setDataset(e.target.value)}>
              {ds.data?.map((d: any) => (
                <option key={d.dataset} value={d.dataset}>
                  {title(d.dataset.replace(/_/g, " "))}
                </option>
              ))}
            </select>
          </label>
          <div className="row">
            {PRESETS.map((p) => (
              <button key={p.name} className="example" onClick={() => setCells({ a: p.a, b: p.b, c: p.c, d: p.d })}>
                {p.name}
              </button>
            ))}
          </div>
          <TwoByTwo a={cells.a} b={cells.b} c={cells.c} d={cells.d} drug="Drug of interest" pt="the event" />
        </section>
        <section className="panel panel-pad">
          <div className="row">
            <h2 style={{ margin: 0 }}>Measures</h2>
            {busy && <span className="spinner" aria-hidden="true" />}
          </div>
          {!res && <Spinner />}
          {res && (
            <>
              <div className="small muted" style={{ margin: "8px 0" }}>
                Expected count under independence: <strong className="num">{fmt(res.expected, 2)}</strong>, chi square with Yates correction <strong className="num">{fmt(res.chi2, 1)}</strong>.
              </div>
              <IntervalRow name="PRR" est={res.prr} lo={res.prr_lo} hi={res.prr_hi} />
              <IntervalRow name="ROR" est={res.ror} lo={res.ror_lo} hi={res.ror_hi} />
              <IntervalRow name="EBGM" est={res.ebgm} lo={res.eb05} hi={res.eb95} />
              <IntervalRow name="IC (log2)" est={res.ic} lo={res.ic025} hi={res.ic975} nullValue={0} log={false} />
              <table className="data" style={{ marginTop: 14 }}>
                <thead>
                  <tr>
                    <th>Screening rule</th>
                    <th>Result</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    ["Evans: PRR at least 2, chi square at least 4, at least 3 cases", res.evans],
                    ["ROR lower 95% limit above 1 with at least 3 cases", res.ror_signal],
                    ["IC025 above 0 (Uppsala Monitoring Centre)", res.ic_signal],
                    ["EB05 at least 2 (FDA convention)", res.eb_signal],
                  ].map(([k, v]) => (
                    <tr key={k as string}>
                      <td>{k}</td>
                      <td>{v ? <span className="chip signal">Signal</span> : <span className="chip">No signal</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="small muted" style={{ marginBottom: 0 }}>
                {res.signal_votes >= 3
                  ? "Most rules agree that reporting is disproportionate. Review the cases before drawing conclusions."
                  : res.signal_votes >= 1
                    ? "The rules disagree. This usually happens with small counts, where the Bayesian measures shrink the ratio and the frequentist ones do not."
                    : "No rule flags this pair."}
              </p>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
