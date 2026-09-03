import { cn } from "@/lib/cn";
import type { AnchorEntry } from "../registry";
import { KeyChip, KindBadge, ParamChip, TrapNote } from "./chips";

const AVAILABILITY_PREFIX: Record<string, string> = {
  "requires-data": "Appears once",
  "in-tab": "Appears when",
  "in-drawer": "Appears while",
  conditional: "Appears when",
};

/** One control, described. Rendered by the help panel; "Show me" spotlights it in place. */
export function ControlCard({
  entry,
  compact = false,
  onShowMe,
}: {
  entry: AnchorEntry;
  compact?: boolean;
  onShowMe: (anchor: string) => void;
}) {
  const { control: c, anchor } = entry;
  const availability = c.availability && c.availability !== "always" ? c.availability : null;

  return (
    <li
      id={`guide-${anchor}`}
      // Read by dashboard/scripts/check_guide.py to enumerate the model from the running app.
      data-anchor={anchor}
      data-availability={c.availability ?? "always"}
      data-in-dom={c.undocumentedInDom ? "no" : "yes"}
      tabIndex={-1}
      className={cn("rounded-md border border-border p-3", compact && "p-2")}
    >
      <div className="flex flex-wrap items-baseline gap-2">
        <h3 className={cn("font-semibold", compact ? "text-sm" : "text-base")}>{c.label}</h3>
        <KindBadge kind={c.kind} />
        {!compact && <span className="font-mono text-xs text-muted">{anchor}</span>}
      </div>

      {availability && (
        <p className="mt-1 text-xs text-muted">
          {AVAILABILITY_PREFIX[availability] ?? "Appears when"} {c.requires}.
        </p>
      )}

      <p className="mt-1.5 text-sm">
        <span className="text-muted">What it does. </span>
        {c.does}
      </p>
      <p className="mt-1 text-sm">
        <span className="text-muted">Why it is there. </span>
        {c.demonstrates}
      </p>

      {(c.writesParams?.length || c.keys?.length || c.navigatesTo) && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {c.navigatesTo && (
            <span className="inline-flex items-center gap-1 rounded-sm border border-border px-1.5 py-0.5 text-xs text-muted">
              goes to <span className="font-mono">{c.navigatesTo}</span>
            </span>
          )}
          {(c.writesParams ?? []).map((p) => (
            <ParamChip key={p.param} effect={p} />
          ))}
          {(c.keys ?? []).map((k) => (
            <KeyChip key={k.keys} hint={k} />
          ))}
        </div>
      )}

      {c.trap && (
        <div className="mt-2">
          <TrapNote trap={c.trap} />
        </div>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-3 text-xs">
        <button type="button" className="text-accent hover:underline" onClick={() => onShowMe(anchor)}>
          Show me
        </button>
        {(c.reading ?? []).map((r) => (
          <span key={r.path} className="text-muted">
            See <span className="font-mono">{r.path}</span> · {r.title}
          </span>
        ))}
      </div>
    </li>
  );
}
