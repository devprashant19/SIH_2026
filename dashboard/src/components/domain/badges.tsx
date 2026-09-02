import { cn } from "@/lib/cn";
import { fmtProb } from "@/lib/format";
import { BAND_CLASS, BAND_GLYPH, BAND_LABEL } from "@/lib/risk";
import type { Decision, FindingSource, RiskBand } from "@/api/types";

/** Severity is always colour + glyph + text so it never depends on colour alone. */
export function RiskBadge({ band, compact }: { band: RiskBand | null | undefined; compact?: boolean }) {
  if (!band) return <span className="text-muted">—</span>;
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium", BAND_CLASS[band])}>
      <span aria-hidden>{BAND_GLYPH[band]}</span>
      {!compact && BAND_LABEL[band]}
      <span className="sr-only">{BAND_LABEL[band]} risk</span>
    </span>
  );
}

/** Findings inside the cost-sensitive uncertainty band always need a human decision. */
export function UncertainBadge({ p, tStar, band }: { p?: number | null; tStar?: number | null; band?: [number, number] | null }) {
  const detail = tStar != null && p != null ? `p=${fmtProb(p)} · t*=${fmtProb(tStar)}${band ? ` · band ${fmtProb(band[0])}–${fmtProb(band[1])}` : ""}` : undefined;
  return (
    <span className="hatch-uncertain inline-flex items-center gap-1 rounded-sm px-2 py-0.5 text-xs font-medium text-uncertain" title={detail}>
      <span aria-hidden>?</span> Uncertain — recommend review
    </span>
  );
}

export function DecisionBadge({ decision, p, tStar, bandRange }: { decision: Decision; p?: number | null; tStar?: number | null; bandRange?: [number, number] | null }) {
  if (decision === "MANUAL_REVIEW") return <UncertainBadge p={p} tStar={tStar} band={bandRange} />;
  const cls = decision === "AUTO_FLAG" ? "bg-risk-high-bg text-risk-high" : "bg-risk-none-bg text-risk-none";
  return <span className={cn("inline-flex rounded-sm px-2 py-0.5 text-xs font-medium", cls)}>{decision === "AUTO_FLAG" ? "Flagged" : "Cleared"}</span>;
}

export function TypeBadge({ source }: { source: FindingSource }) {
  const label = source === "RULE" ? "Rule" : source === "ML" ? "Model" : "Rule + model";
  return <span className="inline-flex rounded-sm border border-border px-1.5 py-0.5 text-xs text-muted">{label}</span>;
}

export function FeedbackBadge({ status }: { status: string | null | undefined }) {
  if (!status) return null;
  const cls = status === "ACCEPT" ? "text-risk-low" : status === "REJECT" ? "text-muted" : "text-risk-elevated";
  return <span className={cn("text-xs font-medium", cls)}>{status === "ACCEPT" ? "Accepted" : status === "REJECT" ? "Rejected" : "Deferred"}</span>;
}

export function SupportBadge({ support }: { support: string | null | undefined }) {
  if (!support || support === "OK") return null;
  const text = { LOW_N: "few records", DEGENERATE: "no peer spread", MISSING: "not available" }[support] ?? support;
  return <span className="ml-1 rounded-sm bg-surface px-1 py-0.5 text-[11px] text-muted" title={`Support: ${support}`}>{text}</span>;
}
