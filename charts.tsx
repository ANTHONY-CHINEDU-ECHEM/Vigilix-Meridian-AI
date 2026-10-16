import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY, SimulationNodeDatum } from "d3-force";
import { fmt, int, useTooltip } from "./ui";

// ------------------------------------------------------------------ scales
const log10 = (v: number) => Math.log10(Math.max(v, 1e-9));
function logTicks(min: number, max: number): number[] {
  const out: number[] = [];
  for (let e = Math.floor(log10(min)); e <= Math.ceil(log10(max)); e++) out.push(10 ** e);
  return out;
}
const tickLabel = (v: number) => (v >= 1000 ? `${v / 1000}k` : v >= 1 ? String(v) : v.toString());

export interface ScatterPoint {
  id: string;
  x: number;
  y: number;
  highlight?: boolean;
  label?: string;
  tip: ReactNode;
}

/** Log scale scatter of report count against a reporting ratio, with a crosshair free per point tooltip. */
export function SignalScatter({ points, xLabel, yLabel, onPick, selected }: { points: ScatterPoint[]; xLabel: string; yLabel: string; onPick?: (id: string) => void; selected?: string | null }) {
  const W = 640,
    H = 380,
    m = { l: 56, r: 16, t: 14, b: 44 };
  const tip = useTooltip();
  const pts = points.filter((p) => p.x > 0 && p.y > 0);
  const [xmin, xmax] = pts.length ? [Math.min(...pts.map((p) => p.x)), Math.max(...pts.map((p) => p.x))] : [1, 10];
  const [ymin, ymax] = pts.length ? [Math.min(...pts.map((p) => p.y)), Math.max(...pts.map((p) => p.y))] : [0.1, 10];
  const lx0 = Math.floor(log10(xmin)),
    lx1 = Math.ceil(log10(xmax) + 0.05);
  const ly0 = Math.floor(log10(Math.min(ymin, 0.5))),
    ly1 = Math.ceil(log10(Math.max(ymax, 2)) + 0.05);
  const sx = (v: number) => m.l + ((log10(v) - lx0) / (lx1 - lx0 || 1)) * (W - m.l - m.r);
  const sy = (v: number) => H - m.b - ((log10(v) - ly0) / (ly1 - ly0 || 1)) * (H - m.t - m.b);
  const ordered = [...pts].sort((a, b) => Number(!!a.highlight) - Number(!!b.highlight));
  return (
    <div style={{ position: "relative" }}>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${yLabel} against ${xLabel}`}>
        <g className="grid">
          {logTicks(10 ** ly0, 10 ** ly1).map((t) => (
            <line key={`gy${t}`} x1={m.l} x2={W - m.r} y1={sy(t)} y2={sy(t)} />
          ))}
          {logTicks(10 ** lx0, 10 ** lx1).map((t) => (
            <line key={`gx${t}`} y1={m.t} y2={H - m.b} x1={sx(t)} x2={sx(t)} />
          ))}
        </g>
        <line x1={m.l} x2={W - m.r} y1={sy(1)} y2={sy(1)} stroke="var(--ink-2)" strokeDasharray="4 4" />
        <text x={W - m.r} y={sy(1) - 5} textAnchor="end">
          ratio of 1
        </text>
        {logTicks(10 ** ly0, 10 ** ly1).map((t) => (
          <text key={`ty${t}`} x={m.l - 8} y={sy(t) + 4} textAnchor="end">
            {tickLabel(t)}
          </text>
        ))}
        {logTicks(10 ** lx0, 10 ** lx1).map((t) => (
          <text key={`tx${t}`} x={sx(t)} y={H - m.b + 16} textAnchor="middle">
            {tickLabel(t)}
          </text>
        ))}
        <text x={(W + m.l) / 2} y={H - 6} textAnchor="middle">
          {xLabel}
        </text>
        <text transform={`translate(14 ${(H - m.b) / 2}) rotate(-90)`} textAnchor="middle">
          {yLabel}
        </text>
        {ordered.map((p) => (
          <circle
            key={p.id}
            cx={sx(p.x)}
            cy={sy(p.y)}
            r={p.id === selected ? 7 : p.highlight ? 5 : 4}
            fill={p.highlight ? "var(--series-2)" : "var(--muted-mark)"}
            stroke={p.id === selected ? "var(--ink)" : "var(--surface)"}
            strokeWidth={p.id === selected ? 2 : 1.5}
            style={{ cursor: onPick ? "pointer" : "default" }}
            onMouseMove={(e) => tip.show(e, p.tip)}
            onMouseLeave={tip.hide}
            onClick={() => onPick?.(p.id)}
          >
            <title>{p.label}</title>
          </circle>
        ))}
      </svg>
      {tip.node}
    </div>
  );
}

// ------------------------------------------------------------------ 2x2 card
export function TwoByTwo({ a, b, c, d, drug, pt }: { a: number; b: number; c: number; d: number; drug: string; pt: string }) {
  return (
    <div className="twobytwo" aria-label="Two by two reporting table">
      <div className="hd" />
      <div className="hd">With {pt}</div>
      <div className="hd">Without</div>
      <div className="hd">{drug}</div>
      <div className="cell-a num" title="a: reports with the drug and the event">
        {int(a)}
      </div>
      <div className="cell num">{int(b)}</div>
      <div className="hd">All other drugs</div>
      <div className="cell num">{int(c)}</div>
      <div className="cell num">{int(d)}</div>
    </div>
  );
}

export function IntervalRow({ name, est, lo, hi, nullValue = 1, threshold, log = true }: { name: string; est: number; lo?: number | null; hi?: number | null; nullValue?: number; threshold?: string; log?: boolean }) {
  const vals = [est, lo ?? est, hi ?? est, nullValue].filter((v) => v !== null && v !== undefined && Number.isFinite(v)) as number[];
  const f = (v: number) => (log ? Math.log10(Math.max(v, 1e-3)) : v);
  const mn = Math.min(...vals.map(f)) - 0.1,
    mx = Math.max(...vals.map(f)) + 0.1;
  const pos = (v: number) => `${(100 * (f(v) - mn)) / (mx - mn || 1)}%`;
  return (
    <div className="measure">
      <span>{name}</span>
      <span className="num" style={{ fontWeight: 600 }}>
        {fmt(est)}
        <span className="faint tiny">{lo !== undefined && lo !== null ? ` (${fmt(lo)} to ${fmt(hi ?? est)})` : ""}</span>
      </span>
      <div className="ci-track" title={threshold}>
        <div className="ci-null" style={{ left: pos(nullValue) }} />
        {lo !== undefined && lo !== null && <div className="ci-line" style={{ left: pos(lo), width: `calc(${pos(hi ?? est)} - ${pos(lo)})` }} />}
        <div className="ci-dot" style={{ left: pos(est) }} />
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ graph
const KIND_COLOR: Record<string, string> = {
  drug: "var(--series-1)",
  reaction: "var(--series-2)",
  class: "var(--series-3)",
  disease: "var(--series-4)",
  target: "var(--muted-mark)",
  drug_group: "var(--series-1)",
};
const REL_STYLE: Record<string, { color: string; dash?: string; width: number }> = {
  faers_signal: { color: "var(--signal)", width: 3 },
  case_reported: { color: "var(--series-2)", width: 1.6 },
  labelled_reaction: { color: "var(--rule-strong)", width: 1.2 },
  literature_induced: { color: "var(--series-2)", dash: "3 3", width: 1.4 },
  interacts: { color: "var(--series-1)", width: 1.8 },
  in_class: { color: "var(--series-3)", dash: "2 3", width: 1.2 },
  treats: { color: "var(--series-4)", width: 1.2 },
  targets: { color: "var(--muted-mark)", dash: "1 3", width: 1 },
};

type GNode = SimulationNodeDatum & { id: string; kind: string; name: string; center?: boolean };

export function ForceGraph({ graph, center, onNode, height = 520 }: { graph: { nodes: any[]; edges: any[] }; center: string; onNode?: (n: any) => void; height?: number }) {
  const W = 900;
  const [nodes, setNodes] = useState<GNode[]>([]);
  const tip = useTooltip();
  const links = useMemo(() => graph.edges.map((e) => ({ source: e.src, target: e.dst, rel: e.rel, label: e.label, sources: e.sources })), [graph]);
  const svgRef = useRef<SVGSVGElement>(null);
  useEffect(() => {
    const ns: GNode[] = graph.nodes.map((n) => ({ id: n.id, kind: n.kind, name: n.name, center: n.id === center, x: W / 2 + (Math.random() - 0.5) * 50, y: height / 2 + (Math.random() - 0.5) * 50 }));
    const c = ns.find((n) => n.center);
    if (c) {
      c.fx = W / 2;
      c.fy = height / 2;
    }
    const ls = links.map((l) => ({ ...l }));
    const sim = forceSimulation(ns)
      .force("link", forceLink(ls as any).id((d: any) => d.id).distance((l: any) => (l.rel === "faers_signal" ? 170 : 215)).strength(0.5))
      .force("charge", forceManyBody().strength(-520))
      .force("collide", forceCollide(44))
      .force("x", forceX(W / 2).strength(0.015))
      .force("y", forceY(height / 2).strength(0.03))
      .stop();
    for (let i = 0; i < 260; i++) sim.tick();
    ns.forEach((n) => {
      n.x = Math.max(40, Math.min(W - 40, n.x!));
      n.y = Math.max(24, Math.min(height - 24, n.y!));
    });
    setNodes(ns);
  }, [graph, center, links, height]);
  const byId = useMemo(() => Object.fromEntries(nodes.map((n) => [n.id, n])), [nodes]);
  return (
    <div className="graph-wrap">
      <svg ref={svgRef} className="chart" viewBox={`0 0 ${W} ${height}`} role="img" aria-label={`Knowledge graph neighbourhood of ${center.split(":")[1]}`}>
        {links.map((l, i) => {
          const s = byId[l.source as string],
            t = byId[l.target as string];
          if (!s || !t) return null;
          const st = REL_STYLE[l.rel] || { color: "var(--rule-strong)", width: 1 };
          return (
            <line
              key={i}
              x1={s.x}
              y1={s.y}
              x2={t.x}
              y2={t.y}
              stroke={st.color}
              strokeWidth={st.width}
              strokeDasharray={st.dash}
              onMouseMove={(e) => tip.show(e, <span>{l.label}: {(l.sources || []).join(", ")}</span>)}
              onMouseLeave={tip.hide}
            />
          );
        })}
        {nodes.map((n) => (
          <g key={n.id} transform={`translate(${n.x},${n.y})`} style={{ cursor: onNode ? "pointer" : "default" }} onClick={() => onNode?.(n)} onMouseMove={(e) => tip.show(e, <span>{n.kind}: {n.name}</span>)} onMouseLeave={tip.hide}>
            <circle r={n.center ? 13 : 8} fill={KIND_COLOR[n.kind] || "var(--muted-mark)"} stroke="var(--surface)" strokeWidth={2} />
            <text y={n.center ? 28 : 20} textAnchor="middle" style={{ fontSize: n.center ? 13 : 10.5, fill: n.center ? "var(--ink)" : "var(--ink-2)", fontWeight: n.center ? 700 : 400 }}>
              {n.name.length > 26 ? n.name.slice(0, 25) + "…" : n.name}
            </text>
          </g>
        ))}
      </svg>
      <div className="graph-legend">
        {[
          ["FAERS signal", "faers_signal"],
          ["Case reports", "case_reported"],
          ["Literature", "literature_induced"],
          ["Listed in labels", "labelled_reaction"],
          ["Interaction", "interacts"],
          ["Class", "in_class"],
          ["Indication", "treats"],
        ].map(([lab, rel]) => (
          <span key={rel} className="row" style={{ gap: 6 }}>
            <svg width="22" height="6" aria-hidden="true">
              <line x1="0" x2="22" y1="3" y2="3" stroke={REL_STYLE[rel].color} strokeWidth={REL_STYLE[rel].width + 0.5} strokeDasharray={REL_STYLE[rel].dash} />
            </svg>
            {lab}
          </span>
        ))}
        <span className="spacer" />
        {[
          ["Drug", "drug"],
          ["Reaction", "reaction"],
          ["Class", "class"],
          ["Indication", "disease"],
        ].map(([lab, k]) => (
          <span key={k} className="row" style={{ gap: 5 }}>
            <span className="dot" style={{ background: KIND_COLOR[k] }} />
            {lab}
          </span>
        ))}
      </div>
      {tip.node}
    </div>
  );
}
