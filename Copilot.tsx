import { useEffect, useRef, useState } from "react";
import { AnswerView, EvidenceCard, QueryChips } from "../components/Answer";
import { ErrorNote, navigate, Spinner, useEngine } from "../components/ui";
import { EXAMPLES } from "./Overview";

interface Turn {
  question: string;
  result?: any;
  error?: string;
}

export default function Copilot({ initial }: { initial: string }) {
  const engine = useEngine();
  const [q, setQ] = useState(initial);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [active, setActive] = useState<number | null>(null);
  const asked = useRef<string | null>(null);

  const ask = async (question: string) => {
    if (!question.trim() || busy) return;
    setBusy(true);
    setActive(null);
    setTurns((t) => [{ question }, ...t]);
    try {
      const result = await engine.ask(question);
      setTurns((t) => [{ question, result }, ...t.slice(1)]);
    } catch (e: any) {
      setTurns((t) => [{ question, error: String(e.message || e) }, ...t.slice(1)]);
    } finally {
      setBusy(false);
      setQ("");
    }
  };

  useEffect(() => {
    if (initial && asked.current !== initial) {
      asked.current = initial;
      ask(initial);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial]);

  const current = turns[0];
  const res = current?.result;
  const cite = (n: number) => {
    setActive(n);
    document.getElementById(`ev-${n}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Evidence copilot</h1>
          <p>Answers are written only from retrieved passages and the knowledge graph. Every sentence cites its evidence and is checked for wording, numbers, drugs, reactions and negation before you see it.</p>
        </div>
      </div>
      <form
        className="ask-bar"
        onSubmit={(e) => {
          e.preventDefault();
          ask(q);
        }}
      >
        <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about an adverse reaction, a signal, a label or an interaction" aria-label="Question" autoFocus />
        <button className="btn" type="submit" disabled={busy}>
          Ask
        </button>
      </form>
      {!current && (
        <div className="examples">
          {EXAMPLES.map((e) => (
            <button key={e} className="example" onClick={() => ask(e)}>
              {e}
            </button>
          ))}
        </div>
      )}

      {current && (
        <div className="split" style={{ marginTop: 22 }}>
          <section className="stack" style={{ gap: 14 }}>
            <div className="panel panel-pad">
              <div className="small faint" style={{ marginBottom: 6 }}>Question</div>
              <div style={{ fontWeight: 600, fontSize: 16, marginBottom: 12 }}>{current.question}</div>
              {!res && !current.error && <Spinner label="Retrieving, writing and verifying" />}
              {current.error && <ErrorNote error={current.error} />}
              {res && (
                <>
                  <QueryChips query={res.query} />
                  <div style={{ marginTop: 14 }}>
                    <AnswerView result={res} onCite={cite} active={active} />
                  </div>
                </>
              )}
            </div>
            {res && res.confidence?.level && res.confidence.level !== "not_applicable" && (
              <div className="panel panel-pad">
                <div className="row">
                  <h2 style={{ margin: 0 }}>Confidence: {res.confidence.level}</h2>
                  <span className="spacer" />
                  <span className="tiny faint">
                    {res.engine === "llm" ? "Written by the local model" : "Extractive writer"}, {res.timings?.total_ms ?? "?"} ms
                  </span>
                </div>
                <div className="meter" style={{ margin: "10px 0" }} aria-hidden="true">
                  <div style={{ width: `${Math.round(100 * Math.max(0, Math.min(1, res.confidence.score)))}%` }} />
                </div>
                <ul className="small muted" style={{ margin: 0, paddingLeft: 18 }}>
                  {res.confidence.reasons.map((r: string) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
              </div>
            )}
            {res && res.graph?.pairs?.length > 0 && <GraphFacts graph={res.graph} />}
            {turns.length > 1 && (
              <div className="panel panel-pad">
                <h2>Earlier questions</h2>
                <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
                  {turns.slice(1, 8).map((t, i) => (
                    <li key={i}>
                      <button className="btn ghost small" style={{ border: 0, padding: 0, textAlign: "left" }} onClick={() => ask(t.question)}>
                        {t.question}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>
          <aside className="stack" style={{ gap: 10 }} aria-label="Evidence">
            <div className="row">
              <h2 className="section-title" style={{ margin: 0 }}>
                Evidence {res ? `(${res.evidence.length})` : ""}
              </h2>
            </div>
            {res?.evidence?.length === 0 && <div className="small muted">No evidence was retrieved for this question.</div>}
            {res?.evidence?.map((it: any) => (
              <EvidenceCard key={it.n} item={it} active={active === it.n} onDrug={(d) => navigate(`/drug/${encodeURIComponent(d)}`)} />
            ))}
          </aside>
        </div>
      )}
    </div>
  );
}

const REL: Record<string, string> = {
  labelled_reaction: "Listed in labels",
  faers_signal: "FAERS signal",
  case_reported: "Case reports",
  literature_induced: "Literature",
};

function GraphFacts({ graph }: { graph: any }) {
  return (
    <div className="panel panel-pad">
      <h2>Knowledge graph check</h2>
      <table className="data">
        <thead>
          <tr>
            <th>Drug and reaction</th>
            {Object.values(REL).map((r) => (
              <th key={r}>{r}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {graph.pairs.map((p: any) => (
            <tr key={p.drug + p.reaction}>
              <td>
                {p.drug} and {p.reaction}
              </td>
              {Object.keys(REL).map((k) => (
                <td key={k}>
                  {p.relations[k] ? (
                    k === "faers_signal" ? (
                      <span className="chip signal">EB05 {p.relations[k].eb05}</span>
                    ) : (
                      <span className="chip ok">Yes</span>
                    )
                  ) : (
                    <span className="faint">No</span>
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {graph.interactions?.length > 0 && (
        <div className="small" style={{ marginTop: 10 }}>
          {graph.interactions.map((it: any) => (
            <div key={it.drugs.join()}>
              {it.drugs.join(" with ")}: {it.documented.length ? "documented interaction" : "no documented interaction"}
              {it.shared_risk_groups.length > 0 && `, shared risk groups: ${it.shared_risk_groups.map((g: any) => g.group).join(", ")}`}
              {" "}
              <a href={`#/interactions?drugs=${encodeURIComponent(it.drugs.join(","))}`}>Open in the interaction checker</a>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
