import { ReactNode, useMemo, useState } from "react";
import { NARANJO, naranjo, whoUmc } from "../engine/causality";
import { ErrorNote, fmt, navigate, Spinner, title, useEngine } from "../components/ui";

const EXAMPLES = [
  {
    name: "Statin and macrolide",
    text: "I am a hospital pharmacist reporting a case. A 67-year-old woman (Mrs Jane Doe, DOB 03/04/1957) started simvastatin 80 mg and clarithromycin was added for pneumonia. Five days later she developed severe muscle pain and dark urine; creatine kinase was 24,000 U/L consistent with rhabdomyolysis. She was admitted to hospital. Both drugs were stopped and her symptoms resolved after discontinuation over two weeks.",
  },
  {
    name: "Antiepileptic skin reaction",
    text: "Our patient, a 34 year old man, was started on lamotrigine for epilepsy while also taking valproate. Two weeks after starting he developed fever, a widespread blistering rash and mouth ulcers diagnosed as Stevens-Johnson syndrome. He was admitted to intensive care. Lamotrigine was withdrawn and the rash improved over the following ten days.",
  },
  {
    name: "Rechallenge",
    text: "A 58 year old woman reported by her GP developed angioedema of the lips and tongue within hours of starting lisinopril. Lisinopril was stopped and the swelling resolved. Lisinopril was restarted by mistake a month later and the angioedema recurred after the first dose.",
  },
];

export default function CaseIntake() {
  const engine = useEngine();
  const [text, setText] = useState(EXAMPLES[0].text);
  const [res, setRes] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [selIdx, setSelIdx] = useState(0);
  const [overrides, setOverrides] = useState<Record<string, Record<string, string>>>({});
  const run = async () => {
    setBusy(true);
    setErr(null);
    try {
      const r = await engine.caseIntake(text);
      setRes(r);
      setSelIdx(0);
      setOverrides({});
    } catch (e: any) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };
  const a = res?.assessments?.[selIdx];
  const key = a ? `${a.drug}|${a.reaction}` : "";
  const answers = a ? { ...a.naranjo_answers, ...(overrides[key] || {}) } : {};
  const live = a ? naranjo(answers) : null;
  const who = a ? whoUmc(answers.after_drug === "yes" ? "yes" : answers.after_drug === "no" ? "no" : "unknown", answers.alternative_causes === "yes" ? "yes" : answers.alternative_causes === "no" ? "no" : "unknown", answers.improved_on_stop, answers.reappeared_on_rechallenge, a.expectedness === "listed" ? "yes" : "unknown") : null;
  const download = () => {
    const blob = new Blob([JSON.stringify({ ...res, reviewer_answers: overrides }, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "vigilix-case-draft.json";
    link.click();
    URL.revokeObjectURL(url);
  };
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Case intake and causality</h1>
          <p>Paste a case narrative. Identifiers are removed first, then suspect drugs and adverse events are extracted, seriousness and outcome detected, the four minimum criteria checked and the Naranjo scale pre filled with answers you can change.</p>
        </div>
      </div>
      <div className="panel panel-pad stack">
        <textarea className="textarea" rows={6} value={text} onChange={(e) => setText(e.target.value)} aria-label="Case narrative" />
        <div className="row">
          <button className="btn" onClick={run} disabled={busy || text.trim().length < 20}>
            Analyse narrative
          </button>
          {busy && <Spinner label="Extracting" />}
          <span className="spacer" />
          {EXAMPLES.map((e) => (
            <button key={e.name} className="example" onClick={() => setText(e.text)}>
              {e.name}
            </button>
          ))}
        </div>
      </div>
      {err && <ErrorNote error={err} />}
      {res && (
        <div className="stack" style={{ marginTop: 18, gap: 16 }}>
          <div className="grid g4">
            <Fact label="Seriousness" value={res.seriousness.serious ? "Serious" : "Not serious"} detail={Object.keys(res.seriousness.criteria).map((k) => k.replace(/_/g, " ")).join(", ") || "no criteria found"} bad={res.seriousness.serious} />
            <Fact label="Outcome" value={title(res.outcome.replace(/_/g, " "))} detail={`Dechallenge ${res.dechallenge}, rechallenge ${res.rechallenge}`} />
            <Fact label="Time to onset" value={res.time_to_onset[0] ? `${fmt(res.time_to_onset[0].days, 1)} days` : "Not stated"} detail={res.time_to_onset[0]?.text || "no explicit interval found"} />
            <Fact label="Valid ICSR" value={res.valid_icsr ? "Yes" : "Incomplete"} detail={Object.entries(res.icsr_minimum_criteria).map(([k, v]) => `${k.replace(/_/g, " ")}: ${v ? "yes" : "no"}`).join("; ")} bad={!res.valid_icsr} />
          </div>
          <div className="panel panel-pad">
            <div className="row">
              <h2 style={{ margin: 0 }}>Redacted narrative with extracted mentions</h2>
              <span className="spacer" />
              <span className="row tiny muted" style={{ gap: 10 }}>
                <mark className="span-drug">drug</mark>
                <mark className="span-effect">adverse effect</mark>
              </span>
            </div>
            <p style={{ fontFamily: "var(--font-read)", fontSize: 16, lineHeight: 1.7, marginBottom: 0 }}>{marked(res)}</p>
            {Object.keys(res.redactions).length > 0 && <p className="tiny faint">Removed: {Object.entries(res.redactions).map(([k, v]) => `${v} ${k.replace(/_/g, " ")}`).join(", ")}.</p>}
          </div>
          {res.assessments.length === 0 ? (
            <div className="notice info">No drug and adverse event pair was found. Check that the narrative names the suspect drug and the reaction.</div>
          ) : (
            <div className="split">
              <section className="panel panel-pad">
                <h2>Drug and event pairs</h2>
                <table className="data">
                  <thead>
                    <tr>
                      <th>Suspect drug</th>
                      <th>Event</th>
                      <th>Expectedness</th>
                      <th>FAERS</th>
                      <th>Naranjo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {res.assessments.map((x: any, i: number) => {
                      const k = `${x.drug}|${x.reaction}`;
                      const n = naranjo({ ...x.naranjo_answers, ...(overrides[k] || {}) });
                      return (
                        <tr key={k} className={`clickable ${i === selIdx ? "selected" : ""}`} onClick={() => setSelIdx(i)}>
                          <td>{x.drug}</td>
                          <td>{x.reaction}</td>
                          <td className="small">{x.expectedness === "listed" ? "Listed" : <strong>Not listed</strong>}</td>
                          <td className="small">{x.faers ? <span className="chip signal">EB05 {fmt(x.faers.eb05, 1)}</span> : <span className="faint">none</span>}</td>
                          <td className="small">
                            {n.category} ({n.score})
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                <div className="row" style={{ marginTop: 12 }}>
                  <button className="btn ghost small" onClick={download}>
                    Download case draft (JSON)
                  </button>
                  {a && (
                    <button className="btn ghost small" onClick={() => navigate(`/copilot?q=${encodeURIComponent(`Is ${a.reaction} a known adverse reaction of ${a.drug}?`)}`)}>
                      Ask the copilot about {a.drug}
                    </button>
                  )}
                </div>
              </section>
              {a && live && who && (
                <section className="panel panel-pad">
                  <div className="row">
                    <h2 style={{ margin: 0 }}>
                      {a.drug} and {a.reaction}
                    </h2>
                    <span className="spacer" />
                    <span className="chip signal">
                      Naranjo {live.score}: {live.category}
                    </span>
                    <span className="chip">WHO UMC: {who.category}</span>
                  </div>
                  <p className="small muted">{who.reason}.</p>
                  <table className="data">
                    <tbody>
                      {NARANJO.map(([k, q]) => (
                        <tr key={k}>
                          <td className="small">
                            {q}
                            {a.justification[k] && <div className="tiny faint">Found: “{a.justification[k]}”</div>}
                          </td>
                          <td>
                            <select className="select" value={answers[k] || "unknown"} onChange={(e) => setOverrides({ ...overrides, [key]: { ...(overrides[key] || {}), [k]: e.target.value } })} aria-label={q}>
                              <option value="yes">Yes</option>
                              <option value="no">No</option>
                              <option value="unknown">Do not know</option>
                            </select>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </section>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Fact({ label, value, detail, bad }: { label: string; value: string; detail: string; bad?: boolean }) {
  return (
    <div className="panel panel-pad">
      <div className="small muted">{label}</div>
      <div style={{ fontWeight: 700, fontSize: 18, color: bad ? "var(--refuted)" : undefined }}>{value}</div>
      <div className="tiny faint">{detail}</div>
    </div>
  );
}

function marked(res: any): ReactNode[] {
  const text: string = res.redacted_narrative;
  const spans: { start: number; end: number; type: string }[] = [];
  for (const s of res.extraction?.sentences || []) {
    if (s.start < 0) continue;
    for (const sp of s.spans) spans.push({ start: s.start + sp.start, end: s.start + sp.end, type: sp.type });
  }
  spans.sort((a, b) => a.start - b.start);
  const out: ReactNode[] = [];
  let pos = 0;
  spans.forEach((s, i) => {
    if (s.start < pos) return;
    out.push(text.slice(pos, s.start));
    out.push(
      <mark key={i} className={s.type === "DRUG" ? "span-drug" : "span-effect"}>
        {text.slice(s.start, s.end)}
      </mark>,
    );
    pos = s.end;
  });
  out.push(text.slice(pos));
  return out;
}
