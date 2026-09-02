import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { fmt2 } from "@/lib/format";

/** Every chart is wrapped in a figure with a caption and a screen-reader data table. */
export function Figure({ caption, table, children, className }: { caption: string; table?: { headers: string[]; rows: (string | number | null)[][] }; children: ReactNode; className?: string }) {
  return (
    <figure className={cn("m-0", className)}>
      {children}
      <figcaption className="mt-1 text-xs text-muted">{caption}</figcaption>
      {table && (
        <table className="sr-only">
          <caption>{caption}</caption>
          <thead>
            <tr>{table.headers.map((h) => <th key={h} scope="col">{h}</th>)}</tr>
          </thead>
          <tbody>
            {table.rows.map((r, i) => (
              <tr key={i}>{r.map((c, j) => <td key={j}>{c ?? "not available"}</td>)}</tr>
            ))}
          </tbody>
        </table>
      )}
    </figure>
  );
}

/** Horizontal bar showing a 0-100 score, optionally with a peer marker. */
export function ScoreBar({ score, max = 100, peer, tone = "risk", title }: { score: number | null | undefined; max?: number; peer?: number | null; tone?: "risk" | "accent"; title?: string }) {
  const v = score == null ? 0 : Math.max(0, Math.min(max, score));
  const pct = (v / max) * 100;
  const colour = tone === "accent" ? "bg-accent" : v >= 75 ? "bg-risk-critical" : v >= 50 ? "bg-risk-high" : v >= 25 ? "bg-risk-elevated" : "bg-risk-low";
  return (
    <span className="relative inline-block h-3 w-full min-w-[60px] rounded-sm bg-surface align-middle" title={title}>
      <span className={cn("absolute left-0 top-0 h-full rounded-sm", colour)} style={{ width: `${pct}%` }} />
      {peer != null && <span className="absolute top-[-2px] h-[calc(100%+4px)] w-px bg-muted" style={{ left: `${(Math.max(0, Math.min(max, peer)) / max) * 100}%` }} title={`peer median ${fmt2(peer)}`} />}
    </span>
  );
}

/** Bullet bar: entity value against the peer p10-p90 band and median. */
export function BulletBar({ value, median, p10, p90, higherIsWorse = true, format = fmt2 }: { value: number | null; median: number | null; p10: number | null; p90: number | null; higherIsWorse?: boolean; format?: (v: number | null) => string }) {
  const nums = [value, median, p10, p90].filter((v): v is number => v != null);
  if (!nums.length) return <span className="text-muted">—</span>;
  const lo = Math.min(...nums), hi = Math.max(...nums);
  const span = hi - lo || Math.abs(hi) || 1;
  const pos = (v: number) => ((v - lo) / span) * 100;
  const worse = value != null && median != null && (higherIsWorse ? value > median : value < median);
  return (
    <span className="relative inline-flex h-4 w-full min-w-[90px] items-center" title={`value ${format(value)} · peer median ${format(median)} · p10–p90 ${format(p10)}–${format(p90)}`}>
      <span className="absolute left-0 h-1.5 w-full rounded-sm bg-surface" />
      {p10 != null && p90 != null && <span className="absolute h-1.5 rounded-sm bg-risk-none-bg" style={{ left: `${pos(p10)}%`, width: `${Math.max(2, pos(p90) - pos(p10))}%` }} />}
      {median != null && <span className="absolute h-3 w-px bg-muted" style={{ left: `${pos(median)}%` }} />}
      {value != null && <span className={cn("absolute h-2.5 w-2.5 -translate-x-1/2 rotate-45", worse ? "bg-risk-high" : "bg-accent")} style={{ left: `${pos(value)}%` }} />}
    </span>
  );
}

/** Diverging bar for one SHAP-style contribution. */
export function ContributionBar({ value, scale }: { value: number; scale: number }) {
  const pct = Math.min(50, (Math.abs(value) / (scale || 1)) * 50);
  return (
    <span className="relative block h-3 w-full min-w-[80px] bg-surface">
      <span className="absolute left-1/2 top-0 h-full w-px bg-border" />
      <span
        className={cn("absolute top-0 h-full", value >= 0 ? "bg-risk-high" : "bg-accent")}
        style={value >= 0 ? { left: "50%", width: `${pct}%` } : { right: "50%", width: `${pct}%` }}
      />
    </span>
  );
}

/** Tiny inline trend line, decorative: the numbers are always available as text nearby. */
export function Sparkline({ values, width = 76, height = 20 }: { values: (number | null)[]; width?: number; height?: number }) {
  const pts = values.map((v, i) => ({ v, i })).filter((p): p is { v: number; i: number } => p.v != null);
  if (pts.length < 2) return <span className="text-muted">—</span>;
  const lo = Math.min(...pts.map((p) => p.v));
  const hi = Math.max(...pts.map((p) => p.v));
  const span = hi - lo || 1;
  const d = pts.map((p, k) => `${k === 0 ? "M" : "L"} ${(p.i / Math.max(1, values.length - 1)) * width} ${height - ((p.v - lo) / span) * height}`).join(" ");
  const rising = pts[pts.length - 1].v > pts[0].v;
  return (
    <svg width={width} height={height} aria-hidden className="align-middle">
      <path d={d} fill="none" strokeWidth="1.5" className={rising ? "stroke-risk-high" : "stroke-muted"} />
    </svg>
  );
}

export function ThresholdLine({ tStar, band, marks = [] }: { tStar: number; band: number; marks?: { p: number; label: string }[] }) {
  const pct = (v: number) => `${Math.max(0, Math.min(1, v)) * 100}%`;
  return (
    <div className="relative h-9 w-full">
      <div className="absolute top-4 h-1 w-full rounded-sm bg-surface" />
      <div className="hatch-uncertain absolute top-3 h-3 rounded-sm" style={{ left: pct(tStar - band), width: pct(Math.min(1, 2 * band)) }} title={`uncertainty band ${(tStar - band).toFixed(2)}–${(tStar + band).toFixed(2)}`} />
      <div className="absolute top-2 h-5 w-px bg-accent" style={{ left: pct(tStar) }} />
      <div className="absolute top-0 -translate-x-1/2 text-[11px] text-accent" style={{ left: pct(tStar) }}>
        t* {tStar.toFixed(2)}
      </div>
      {marks.map((m) => (
        <div key={m.label} className="absolute top-5 -translate-x-1/2 text-[11px] text-muted" style={{ left: pct(m.p) }} title={m.label}>
          ▲
        </div>
      ))}
      <div className="absolute bottom-0 left-0 text-[11px] text-muted">0</div>
      <div className="absolute bottom-0 right-0 text-[11px] text-muted">1</div>
    </div>
  );
}
