import { createContext, ReactNode, useContext, useEffect, useRef, useState } from "react";
import { Engine, getEngine } from "../api";

export const EngineContext = createContext<Engine | null>(null);
export const useEngine = () => useContext(EngineContext)!;

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): { data: T | null; error: string | null; loading: boolean; reload: () => void } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    fn()
      .then((d) => alive && setData(d))
      .catch((e) => alive && setError(String(e.message || e)))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return { data, error, loading, reload: () => setTick((t) => t + 1) };
}

export function useEngineLoader() {
  const [engine, setEngine] = useState<Engine | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    getEngine().then(setEngine).catch((e) => setError(String(e)));
  }, []);
  return { engine, error };
}

export const Spinner = ({ label }: { label?: string }) => (
  <span className="row small muted" role="status">
    <span className="spinner" aria-hidden="true" /> {label ?? "Working"}
  </span>
);

export const ErrorNote = ({ error }: { error: string }) => <div className="notice crisis">Something failed: {error}</div>;

export const Empty = ({ children }: { children: ReactNode }) => <div className="empty">{children}</div>;

export const fmt = (v: number | null | undefined, d = 2) => {
  if (v === null || v === undefined || Number.isNaN(v)) return "n/a";
  if (Math.abs(v) >= 1000) return Math.round(v).toLocaleString("en-GB");
  return v.toFixed(d);
};
export const int = (v: number | null | undefined) => (v === null || v === undefined ? "n/a" : Math.round(v).toLocaleString("en-GB"));
export const pct = (v: number | null | undefined, d = 0) => (v === null || v === undefined ? "n/a" : `${(v * 100).toFixed(d)}%`);
export const title = (s: string) => (s ? s.replace(/\b\w/g, (c) => c.toUpperCase()) : s);

export const LEVEL_NAMES: Record<number, string> = { 1: "Guidance or label", 2: "Randomised trial", 3: "Database or graph", 4: "Case or literature" };

export function LevelBadge({ level, label }: { level: number; label: string }) {
  return (
    <span className={`level l${level}`} title={LEVEL_NAMES[level]}>
      {label}
    </span>
  );
}

export function Kpis({ items }: { items: { label: string; value: ReactNode }[] }) {
  return (
    <div className="kpis">
      {items.map((k) => (
        <div className="kpi" key={k.label}>
          <div className="kpi-value">{k.value}</div>
          <div className="kpi-label">{k.label}</div>
        </div>
      ))}
    </div>
  );
}

export function BarList({ rows, color, format = (v: number) => v.toLocaleString("en-GB"), onClick }: { rows: { label: string; value: number }[]; color?: string; format?: (v: number) => string; onClick?: (label: string) => void }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <div className="bars">
      {rows.map((r) => (
        <div className="bar-row" key={r.label} onClick={onClick ? () => onClick(r.label) : undefined} style={onClick ? { cursor: "pointer" } : undefined}>
          <span title={r.label} style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {r.label}
          </span>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${(100 * r.value) / max}%`, background: color }} />
          </div>
          <span className="num small" style={{ textAlign: "right" }}>
            {format(r.value)}
          </span>
        </div>
      ))}
    </div>
  );
}

export function Tabs({ tabs, value, onChange }: { tabs: { id: string; label: string }[]; value: string; onChange: (id: string) => void }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button key={t.id} role="tab" aria-selected={value === t.id} className="tab" onClick={() => onChange(t.id)}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function useTooltip() {
  const [tip, setTip] = useState<{ x: number; y: number; content: ReactNode } | null>(null);
  const node = tip ? (
    <div className="tooltip" style={{ left: Math.min(tip.x + 14, window.innerWidth - 300), top: tip.y + 14 }}>
      {tip.content}
    </div>
  ) : null;
  return { show: (e: { clientX: number; clientY: number }, content: ReactNode) => setTip({ x: e.clientX, y: e.clientY, content }), hide: () => setTip(null), node };
}

export function navigate(path: string) {
  location.hash = path;
}

export function useDebounced<T>(value: T, ms = 200): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function useOutside(ref: React.RefObject<HTMLElement>, cb: () => void) {
  useEffect(() => {
    const h = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) cb();
    };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [ref, cb]);
}

export function EntityInput({ placeholder, onPick, kind = "drug", initial = "", autoFocus = false }: { placeholder: string; onPick: (name: string) => void; kind?: "drug" | "reaction"; initial?: string; autoFocus?: boolean }) {
  const engine = useEngine();
  const [q, setQ] = useState(initial);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<any[]>([]);
  const [active, setActive] = useState(0);
  const dq = useDebounced(q, 150);
  const ref = useRef<HTMLDivElement>(null);
  useOutside(ref, () => setOpen(false));
  useEffect(() => {
    if (dq.trim().length < 2) {
      setItems([]);
      return;
    }
    engine.suggest(dq, kind).then((r) => {
      setItems(r);
      setActive(0);
    });
  }, [dq, kind, engine]);
  const pick = (name: string) => {
    onPick(name);
    setQ(kind === "drug" ? "" : name);
    setOpen(false);
  };
  return (
    <div className="ac" ref={ref} style={{ flex: 1, minWidth: 220 }}>
      <input
        className="input"
        style={{ width: "100%" }}
        value={q}
        autoFocus={autoFocus}
        placeholder={placeholder}
        aria-label={placeholder}
        role="combobox"
        aria-expanded={open && items.length > 0}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") setActive((a) => Math.min(a + 1, items.length - 1));
          else if (e.key === "ArrowUp") setActive((a) => Math.max(a - 1, 0));
          else if (e.key === "Enter") {
            e.preventDefault();
            if (items[active]) pick(items[active].name);
            else if (q.trim()) pick(q.trim().toLowerCase());
          } else if (e.key === "Escape") setOpen(false);
        }}
      />
      {open && items.length > 0 && (
        <div className="ac-list" role="listbox">
          {items.map((it, i) => (
            <div key={it.name} className="ac-item" role="option" aria-selected={i === active} onMouseDown={() => pick(it.name)}>
              <span>{it.name}</span>
              <span className="faint tiny">{it.match?.find((m: string) => m !== it.name) || it.atc || it.soc || ""}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
