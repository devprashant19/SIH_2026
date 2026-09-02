import { Link } from "react-router-dom";
import { cn } from "@/lib/cn";
import { fmt1 } from "@/lib/format";
import { RiskBadge } from "@/components/domain/badges";
import { Sparkline } from "./primitives";
import type { Capability, HeatmapRow, SriDimension } from "@/api/types";

export const DIMENSION_LABELS: Record<SriDimension, string> = {
  execution_gap: "Execution gap",
  negative_space: "Negative space",
  escalation_discipline: "Escalation",
  investigation_quality: "Investigation",
  data_integrity: "Data integrity",
  trend_penalty: "Trend",
};

const CAPABILITIES: Capability[] = ["Threat Detection", "Investigation", "Escalation", "Incident Response", "Security Operations", "Governance and Oversight", "Operational Discipline", "Cyber Resilience"];

function cellClass(v: number | null | undefined): string {
  if (v == null) return "bg-surface text-muted";
  if (v >= 75) return "bg-risk-critical-bg text-risk-critical";
  if (v >= 50) return "bg-risk-high-bg text-risk-high";
  if (v >= 25) return "bg-risk-elevated-bg text-risk-elevated";
  return "bg-risk-low-bg text-risk-low";
}

/** Entity x dimension (or capability) matrix. Cells carry the number, so colour is never the only cue. */
export function RiskHeatmap({ rows, lens, period, onCellClick }: { rows: HeatmapRow[]; lens: "sri" | "capability"; period: string; onCellClick?: (entityId: string, key: string) => void }) {
  const columns: string[] = lens === "capability" ? CAPABILITIES : (Object.keys(DIMENSION_LABELS) as SriDimension[]);
  const label = (c: string) => (lens === "capability" ? c : DIMENSION_LABELS[c as SriDimension]);
  const valueOf = (r: HeatmapRow, c: string) => (lens === "capability" ? r.capabilities[c as Capability] : r.dims[c as SriDimension]);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <caption className="sr-only">Entity risk by {lens === "capability" ? "capability area" : "supervisory dimension"} for {period}</caption>
        <thead>
          <tr>
            <th scope="col" className="border-b border-border px-2 py-1.5 text-left" title="Supervisory priority: SRI weighted by confidence and by sector/size impact">Rank</th>
            <th scope="col" className="border-b border-border px-2 py-1.5 text-left">Entity</th>
            <th scope="col" className="border-b border-border px-2 py-1.5 text-left">SRI</th>
            {columns.map((c) => (
              <th key={c} scope="col" className="border-b border-border px-2 py-1.5 text-left" title={label(c)}>
                {label(c)}
              </th>
            ))}
            <th scope="col" className="border-b border-border px-2 py-1.5 text-left">Findings</th>
            <th scope="col" className="border-b border-border px-2 py-1.5 text-left">Trend</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.entity_id} className="border-b border-border hover:bg-accent-bg/40">
              <td className="px-2 py-1.5 tabular text-muted">{r.priority_rank}</td>
              <td className="px-2 py-1.5">
                <Link to={{ pathname: `/entities/${r.entity_id}`, search: `?period=${period}` }} className="font-medium text-accent hover:underline">
                  {r.entity_id}
                </Link>
                <div className="text-xs text-muted">{r.name} · {r.sector}</div>
              </td>
              <td className="whitespace-nowrap px-2 py-1.5">
                <span className="tabular font-medium">{fmt1(r.sri)}</span> <RiskBadge band={r.band} compact />
              </td>
              {columns.map((c) => {
                const v = valueOf(r, c);
                return (
                  <td key={c} className="px-1 py-1">
                    <button
                      type="button"
                      onClick={() => onCellClick?.(r.entity_id, c)}
                      title={`${r.entity_id} · ${label(c)}: ${v == null ? "not scored" : fmt1(v)}`}
                      className={cn("w-full rounded-sm px-2 py-1 text-left tabular", cellClass(v))}
                    >
                      {v == null ? "—" : fmt1(v)}
                    </button>
                  </td>
                );
              })}
              <td className="px-2 py-1.5 tabular">
                {r.n_findings}
                {r.n_manual_review > 0 && <span className="ml-1 text-uncertain" title={`${r.n_manual_review} uncertain, need a decision`}>?{r.n_manual_review}</span>}
              </td>
              <td className="px-2 py-1.5">
                <Sparkline values={r.trend} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
