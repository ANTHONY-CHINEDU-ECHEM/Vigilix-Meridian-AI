import { useState } from "react";
import { BarList, ErrorNote, fmt, int, Kpis, navigate, pct, Spinner, title, useAsync, useEngine } from "../components/ui";

export const EXAMPLES = [
  "Does clarithromycin raise the risk of rhabdomyolysis with simvastatin?",
  "Is dysgeusia an expected reaction to Paxlovid?",
  "Which drugs cause torsade de pointes and what increases the risk?",
  "My patient on Cipralex has a long QT. Is that known?",
  "What does an EB05 of 2 mean in FDA data mining?",
  "Bleeding risk of apixaban with an NSAID",
];

const SOURCE_NAMES: Record<string, string> = {
  trial_abstract: "Randomised trial abstracts",
  kg_fact: "Curated graph facts",
  drug_label: "Drug label sections",
  case_report: "Case reports",
  cid_abstract: "Chemical induced disease abstracts",
  interaction_monograph: "Interaction monographs",
  interaction_abstract: "Interaction abstracts",
  signal_summary: "FAERS signal summaries",
  guidance_card: "Guidance digests",
};

export default function Overview() {
  const engine = useEngine();
  const { data, error, loading } = useAsync(() => engine.overview(), [engine]);
  const [q, setQ] = useState("");
  const go = (text: string) => navigate(`/copilot?q=${encodeURIComponent(text)}`);
  return (
    <div className="page">
      <section className="hero-ask" aria-labelledby="hero-title">
        <h2 id="hero-title">Ask a drug safety question and get an answer checked line by line against its sources.</h2>
        <form
          className="ask-bar"
          onSubmit={(e) => {
            e.preventDefault();
            if (q.trim()) go(q.trim());
          }}
        >
          <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="For example: does fingolimod cause bradycardia after the first dose?" aria-label="Question" />
          <button className="btn" type="submit">
            Ask
          </button>
        </form>
        <div className="examples">
          {EXAMPLES.slice(0, 4).map((e) => (
            <button key={e} className="example" onClick={() => go(e)}>
              {e}
            </button>
          ))}
        </div>
      </section>

      {loading && <div style={{ marginTop: 20 }}><Spinner label="Loading overview" /></div>}
      {error && <ErrorNote error={error} />}
      {data && (
        <div className="stack" style={{ gap: 22, marginTop: 22 }}>
          <Kpis
            items={[
              { label: "Passages indexed", value: int(data.kb.passages) },
              { label: "Source documents", value: int(data.kb.documents) },
              { label: "Drugs in the dictionary", value: int(data.kb.drugs) },
              { label: "Reaction terms", value: int(data.kb.reactions) },
              { label: "Knowledge graph edges", value: int(data.kb.kg_edges) },
              { label: "FAERS pairs screened", value: int(data.kb.faers_pairs) },
            ]}
          />
          <div className="split">
            <section className="panel panel-pad">
              <div className="row" style={{ marginBottom: 10 }}>
                <h2 style={{ margin: 0 }}>Unlabelled FAERS signals worth a look</h2>
                <span className="spacer" />
                <button className="btn ghost small" onClick={() => navigate("/signals")}>
                  Open signal explorer
                </button>
              </div>
              <p className="small muted" style={{ marginTop: 0 }}>
                EB05 of at least 2, at least ten reports, not listed in label derived references for drugs the references cover, and outside suspicious report clusters. A disproportionate reporting pattern is a reason to review cases, not proof of harm.
              </p>
              <div className="table-wrap" style={{ maxHeight: 420 }}>
                <table className="data">
                  <thead>
                    <tr>
                      <th>Drug</th>
                      <th>Preferred term</th>
                      <th className="r">Cases</th>
                      <th className="r">EB05</th>
                      <th className="r">ROR</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.top_unlabelled_signals.map((r: any) => (
                      <tr key={r.drug + r.pt} className="clickable" onClick={() => navigate(`/signals?dataset=${r.dataset}&drug=${encodeURIComponent(r.drug)}`)}>
                        <td>{r.drug}</td>
                        <td>{r.pt}</td>
                        <td className="r">{int(r.a)}</td>
                        <td className="r">
                          <span className="chip signal">{fmt(r.eb05, 1)}</span>
                        </td>
                        <td className="r">{fmt(r.ror, 1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
            <div className="stack" style={{ gap: 16 }}>
              <section className="panel panel-pad">
                <h2>How well it works</h2>
                <dl className="small" style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: "8px 16px", margin: 0 }}>
                  {data.evaluation.retrieval_dev && (
                    <>
                      <dt className="muted">Relevant evidence in the top five (development set)</dt>
                      <dd className="num" style={{ margin: 0, fontWeight: 600 }}>{pct(data.evaluation.retrieval_dev.recall_at_5)}</dd>
                    </>
                  )}
                  {data.evaluation.retrieval_blind && (
                    <>
                      <dt className="muted">Relevant evidence in the top five (blind set)</dt>
                      <dd className="num" style={{ margin: 0, fontWeight: 600 }}>{pct(data.evaluation.retrieval_blind.recall_at_5)}</dd>
                    </>
                  )}
                  <dt className="muted">Answer sentences supported by their citations</dt>
                  <dd className="num" style={{ margin: 0, fontWeight: 600 }}>{pct(data.evaluation.answers?.faithfulness_supported, 1)}</dd>
                  <dt className="muted">Claim verifier AUROC on held out perturbations</dt>
                  <dd className="num" style={{ margin: 0, fontWeight: 600 }}>{fmt(data.evaluation.verifier_auroc, 3)}</dd>
                  <dt className="muted">Adverse effect span F1 on held out case reports</dt>
                  <dd className="num" style={{ margin: 0, fontWeight: 600 }}>{fmt(data.evaluation.ade?.effect_spans_crf, 2)}</dd>
                  <dt className="muted">Safety probes passed</dt>
                  <dd className="num" style={{ margin: 0, fontWeight: 600 }}>
                    {(data.evaluation.safety_probes || []).filter((p: any) => p.passed).length} of {(data.evaluation.safety_probes || []).length}
                  </dd>
                </dl>
                <button className="btn ghost small" style={{ marginTop: 14 }} onClick={() => navigate("/evaluation")}>
                  See the full evaluation
                </button>
              </section>
              <section className="panel panel-pad">
                <h2>What the knowledge base holds</h2>
                <BarList rows={Object.entries(data.passages_by_source).map(([k, v]) => ({ label: SOURCE_NAMES[k] || k, value: v as number })).sort((a, b) => b.value - a.value)} />
              </section>
            </div>
          </div>
          <section>
            <h2 className="section-title">FAERS datasets screened</h2>
            <div className="grid g4">
              {data.datasets.map((d: any) => (
                <button key={d.dataset} className="panel panel-pad" style={{ textAlign: "left", cursor: "pointer" }} onClick={() => navigate(`/signals?dataset=${d.dataset}`)}>
                  <div style={{ fontWeight: 700 }}>{title(d.dataset.replace(/_/g, " "))}</div>
                  <div className="small muted">{d.period}</div>
                  <div className="small" style={{ marginTop: 8 }}>
                    {d.drugs.length} drugs, {int(d.terms)} preferred terms, <strong>{int(d.signals)}</strong> pairs at EB05 of 2 or more
                  </div>
                  <div className="tiny faint" style={{ marginTop: 6 }}>{d.drugs.slice(0, 6).join(", ")}{d.drugs.length > 6 ? ", and more" : ""}</div>
                </button>
              ))}
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
