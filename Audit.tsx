import { ErrorNote, Spinner, useAsync, useEngine } from "../components/ui";

export default function Audit() {
  const engine = useEngine();
  const { data, error, loading, reload } = useAsync(() => engine.audit(), [engine]);
  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>Audit log</h1>
          <p>Every question, interaction check and case analysis is recorded with its redacted text, a hash of the original, the entities found, the engine used and the verification outcome. The log is append only: database triggers reject updates and deletes.</p>
        </div>
        <button className="btn ghost" onClick={reload}>
          Refresh
        </button>
      </div>
      {loading && <Spinner />}
      {error && <ErrorNote error={error} />}
      {data && (
        <>
          <p className="small muted">
            {data.stats.entries} entries{engine.mode === "browser" ? " in this browser session (the browser engine keeps its log in memory only)" : ""}.
          </p>
          {data.entries.length === 0 ? (
            <div className="panel empty">No activity yet. Ask the copilot a question to create the first entry.</div>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Endpoint</th>
                    <th>Redacted input</th>
                    <th>Removed</th>
                    <th>Entities</th>
                    <th>Engine</th>
                    <th className="r">Supported</th>
                    <th>Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  {data.entries.map((e: any) => (
                    <tr key={e.id}>
                      <td className="small num">{new Date(e.ts * 1000).toLocaleString("en-GB")}</td>
                      <td className="small">{e.endpoint}</td>
                      <td className="small" style={{ maxWidth: 380 }}>{e.redacted_query}</td>
                      <td className="small">{e.redactions && Object.keys(e.redactions).length ? Object.entries(e.redactions).map(([k, v]) => `${v} ${k}`).join(", ") : "none"}</td>
                      <td className="small">{[...(e.drugs || []), ...(e.reactions || [])].join(", ")}</td>
                      <td className="small">{e.engine || ""}</td>
                      <td className="r small">{e.supported === null || e.supported === undefined ? "" : `${Math.round(e.supported * 100)}%`}</td>
                      <td className="small">{e.confidence || ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
