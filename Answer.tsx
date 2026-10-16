import { useState } from "react";
import { LevelBadge, navigate, title } from "./ui";

const STATUS_TEXT: Record<string, string> = {
  supported: "Supported by the cited evidence",
  partial: "Partly supported: check the cited evidence",
  unsupported: "Not supported by the cited evidence",
  not_applicable: "Safety notice",
};

export function AnswerView({ result, onCite, active }: { result: any; onCite: (n: number) => void; active: number | null }) {
  const notices: string[] = result.notices || [];
  const isBlocked = notices.includes("crisis") || notices.includes("out_of_scope");
  return (
    <div>
      {notices.includes("crisis") && <div className="notice crisis" style={{ marginBottom: 12 }}>Support is available right now.</div>}
      <p className="answer" style={{ margin: 0 }}>
        {result.answer.map((s: any, i: number) => {
          const st = s.verification?.status || "not_applicable";
          return (
            <span key={i}>
              <span className={`sent ${st}`} title={`${STATUS_TEXT[st] || st}${s.verification?.issues?.length ? ": " + s.verification.issues.join("; ") : ""}${s.verification?.probability !== undefined ? ` (p = ${s.verification.probability})` : ""}`}>
                {s.text}
              </span>
              {s.citations.map((c: number) => (
                <button key={c} className={`cite ${active === c ? "active" : ""}`} onClick={() => onCite(c)} aria-label={`Show evidence ${c}`}>
                  {c}
                </button>
              ))}{" "}
            </span>
          );
        })}
      </p>
      {!isBlocked && (
        <div className="legend-line">
          <span>
            <i className="swatch" style={{ background: "var(--verified)" }} /> Supported
          </span>
          <span>
            <i className="swatch" style={{ background: "var(--signal)" }} /> Partly supported
          </span>
          <span>
            <i className="swatch" style={{ background: "var(--refuted)" }} /> Unsupported
          </span>
          <span className="faint">Hover a sentence for its verification detail.</span>
        </div>
      )}
    </div>
  );
}

export function EvidenceCard({ item, active, onDrug }: { item: any; active: boolean; onDrug?: (d: string) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <article className={`evidence ${active ? "active" : ""}`} id={`ev-${item.n}`}>
      <div className="evidence-head">
        <span className="evidence-n">{item.n}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="evidence-title">{item.title}</div>
          <div className="row tiny faint" style={{ marginTop: 3, gap: 6 }}>
            <LevelBadge level={item.evidence_level} label={item.evidence_label} />
            {item.section && item.source_type !== "graph" && <span>{item.section}</span>}
            {item.region && <span>{item.region}</span>}
            {item.url && (
              <a href={item.url} target="_blank" rel="noreferrer">
                PubMed
              </a>
            )}
          </div>
        </div>
      </div>
      <div className={`evidence-text ${open ? "open" : ""}`}>{item.text}</div>
      <div className="row tiny" style={{ marginTop: 6 }}>
        {item.text.length > 420 && (
          <button className="btn ghost small" onClick={() => setOpen(!open)}>
            {open ? "Show less" : "Show all"}
          </button>
        )}
        {(item.drugs || []).slice(0, 4).map((d: string) => (
          <button key={d} className="chip drug" onClick={() => (onDrug ? onDrug(d) : navigate(`/drug/${encodeURIComponent(d)}`))}>
            {d}
          </button>
        ))}
        {(item.references || []).length > 0 && (
          <details className="disclose" style={{ width: "100%" }}>
            <summary>References</summary>
            <ul className="small" style={{ margin: "6px 0 0", paddingLeft: 18 }}>
              {item.references.map((r: string) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </details>
        )}
      </div>
    </article>
  );
}

export function QueryChips({ query }: { query: any }) {
  if (!query) return null;
  return (
    <div className="row tiny" style={{ gap: 6 }}>
      <span className="faint">Understood as</span>
      {(query.intents || []).slice(0, 3).map((i: string) => (
        <span key={i} className="chip">
          {title(i.replace("_", " "))}
        </span>
      ))}
      {(query.drugs || []).map((d: string) => (
        <span key={d} className="chip drug">
          {d}
        </span>
      ))}
      {(query.reactions || []).map((r: string) => (
        <span key={r} className="chip reaction">
          {r}
        </span>
      ))}
      {(query.populations || []).map((p: string) => (
        <span key={p} className="chip">
          {p.replace("_", " ")}
        </span>
      ))}
    </div>
  );
}
