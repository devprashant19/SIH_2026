import { Link } from "react-router-dom";
import { cn } from "@/lib/cn";

export function StatTile({ label, value, delta, hint, to, tone = "neutral" }: { label: string; value: string | number; delta?: number | null; hint?: string; to?: string; tone?: "neutral" | "risk" | "uncertain" }) {
  const body = (
    <>
      <div className="text-xs text-muted">{label}</div>
      <div className={cn("tabular text-num font-semibold", tone === "risk" && "text-risk-high", tone === "uncertain" && "text-uncertain")}>{value}</div>
      {delta != null && delta !== 0 && (
        <div className={cn("text-xs", delta > 0 ? "text-risk-high" : "text-risk-low")}>
          {delta > 0 ? "▲" : "▼"} {Math.abs(delta)} vs previous period
        </div>
      )}
      {hint && <div className="text-xs text-muted">{hint}</div>}
    </>
  );
  return to ? (
    <Link to={to} className="card block p-3 hover:border-accent">
      {body}
    </Link>
  ) : (
    <div className="card p-3">{body}</div>
  );
}
