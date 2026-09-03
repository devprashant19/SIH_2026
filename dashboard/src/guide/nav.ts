/** Query-string helpers. Every guide navigation goes through these so the globally selected
 *  period, and any filter the user had set, survive a jump between screens. */

/**
 * Merge `patch` into the current parameters and render the result as a `?a=b` string.
 * An empty or undefined value removes the key, matching useSearchParamState's own rule.
 */
export function withSearch(params: URLSearchParams, patch: Record<string, string | undefined> = {}): string {
  const next = new URLSearchParams(params);
  for (const [k, v] of Object.entries(patch)) {
    if (v === undefined || v === "") next.delete(k);
    else next.set(k, v);
  }
  const s = next.toString();
  return s ? `?${s}` : "";
}

/** `?tour=` carries the tour id and the step index in one parameter, so a navigation that
 *  rebuilds the query string has one fewer thing to drop. */
export function formatTourParam(tourId: string, stepIndex: number): string {
  return `${tourId}.${stepIndex}`;
}

export function parseTourParam(value: string | null | undefined): { id: string; step: number } | null {
  if (!value) return null;
  const dot = value.lastIndexOf(".");
  if (dot <= 0) return null;
  const id = value.slice(0, dot);
  const step = Number(value.slice(dot + 1));
  if (!id || !Number.isInteger(step) || step < 0) return null;
  return { id, step };
}

/** Fill `:params` in a route pattern. Unfilled parameters are left in place so the caller can
 *  detect that the pattern was not resolvable and fall back to skipping the step. */
export function fillRoute(pattern: string, values: Record<string, string | undefined> = {}): string {
  return pattern.replace(/:([A-Za-z0-9_]+)/g, (whole, key: string) => values[key] ?? whole);
}

export function isResolvedRoute(path: string): boolean {
  return !path.includes(":");
}
