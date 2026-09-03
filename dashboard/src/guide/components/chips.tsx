import type { KeyHint, Trap, UrlParamEffect } from "../model";

/** A URL parameter this control writes. Muted, never a risk colour: this is not a warning. */
export function ParamChip({ effect }: { effect: UrlParamEffect }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-sm border border-border px-1.5 py-0.5 text-xs text-muted">
      <span className="font-mono">?{effect.param}</span>
      {effect.values && <span>{effect.values}</span>}
      {effect.clearedAt !== undefined && (
        <span className="text-muted">· removed at {effect.clearedAt === "" ? "All" : effect.clearedAt}</span>
      )}
    </span>
  );
}

export function KeyChip({ hint }: { hint: KeyHint }) {
  return (
    <span className="inline-flex items-center gap-1 text-xs text-muted">
      <kbd className="rounded-sm border border-border bg-surface px-1.5 py-0.5 font-mono text-xs">{hint.keys}</kbd>
      <span>{hint.description}</span>
      {hint.when && <span>({hint.when})</span>}
    </span>
  );
}

/** Dashed border and a glyph, deliberately not a risk colour: a trap is a surprise, not a fault. */
export function TrapNote({ trap }: { trap: Trap }) {
  return (
    <div className="rounded-sm border border-dashed border-border p-2 text-xs">
      <p className="font-medium">
        <span aria-hidden>⚠ </span>
        Watch out: {trap.summary}
      </p>
      <p className="mt-1 text-muted">
        <span className="font-medium">What you see:</span> {trap.symptom}
      </p>
      <p className="mt-0.5 text-muted">
        <span className="font-medium">What to do:</span> {trap.fix}
      </p>
    </div>
  );
}

export function KindBadge({ kind }: { kind: string }) {
  return <span className="rounded-sm border border-border px-1.5 py-0.5 text-xs text-muted">{kind.replace(/-/g, " ")}</span>;
}
