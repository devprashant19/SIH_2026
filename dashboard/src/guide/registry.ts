import { matchPath } from "react-router-dom";
import { CONCEPTS } from "./concepts";
import { GUIDE } from "./content";
import { anchorOf, type Anchor, type ControlKind, type GuideConcept, type GuideControl, type GuideScreen } from "./model";

export const SCREENS: readonly GuideScreen[] = GUIDE;

/** The two pseudo-screens are not routes, so they are excluded from path matching. */
export const ROUTE_SCREENS: readonly GuideScreen[] = GUIDE.filter((s) => !s.chrome);
export const GLOBAL_SCREEN = GUIDE.find((s) => s.id === "global")!;
export const SHARED_SCREEN = GUIDE.find((s) => s.id === "shared")!;

export interface AnchorEntry {
  anchor: Anchor;
  screen: GuideScreen;
  control: GuideControl;
}

const byAnchor = new Map<Anchor, AnchorEntry>();
const byScreenId = new Map<string, GuideScreen>();
for (const screen of GUIDE) {
  byScreenId.set(screen.id, screen);
  for (const control of screen.controls) {
    byAnchor.set(anchorOf(screen, control), { anchor: anchorOf(screen, control), screen, control });
  }
}

export const BY_ANCHOR: ReadonlyMap<Anchor, AnchorEntry> = byAnchor;
export const BY_SCREEN_ID: ReadonlyMap<string, GuideScreen> = byScreenId;
export const ALL_ANCHORS: readonly Anchor[] = [...byAnchor.keys()];

const conceptById = new Map(CONCEPTS.map((c) => [c.id, c]));
export const BY_CONCEPT_ID: ReadonlyMap<string, GuideConcept> = conceptById;

/** Screens whose route pattern matches this path, most specific first. */
export function screenForPath(pathname: string): GuideScreen | undefined {
  const hits = ROUTE_SCREENS.filter((s) => matchPath({ path: s.routePattern, end: true }, pathname));
  if (hits.length <= 1) return hits[0];
  // A literal segment beats a parameter, so "/findings" wins over "/findings/:findingId"
  // only when both match, which they cannot; this orders by specificity for safety.
  return hits.sort((a, b) => b.routePattern.split("/").length - a.routePattern.split("/").length)[0];
}

/** The controls a screen shows: its own, plus the shared filters it declares. */
export function controlsFor(screen: GuideScreen): readonly AnchorEntry[] {
  const own = screen.controls.map((c) => byAnchor.get(anchorOf(screen, c))!);
  const shared = (screen.sharedControls ?? []).map((a) => byAnchor.get(a)).filter((e): e is AnchorEntry => !!e);
  return [...own, ...shared];
}

// ---- search ------------------------------------------------------------------------------

export interface SearchFilters {
  screenId?: string;
  kind?: ControlKind | "";
  trapsOnly?: boolean;
}

export interface SearchHit extends AnchorEntry {
  score: number;
}

interface Row {
  entry: AnchorEntry;
  /** [label, kind + params, does, demonstrates + trap] lower-cased once at module load. */
  fields: readonly [string, string, string, string];
}

const WEIGHTS = [8, 4, 2, 1] as const;

const ROWS: readonly Row[] = [...byAnchor.values()].map((entry) => {
  const c = entry.control;
  const params = (c.writesParams ?? []).map((p) => `${p.param} ${p.values ?? ""}`).join(" ");
  const keys = (c.keys ?? []).map((k) => k.keys).join(" ");
  const trap = c.trap ? `${c.trap.summary} ${c.trap.symptom} ${c.trap.fix}` : "";
  return {
    entry,
    fields: [
      `${c.label} ${entry.anchor} ${entry.screen.title}`.toLowerCase(),
      `${c.kind} ${params} ${keys}`.toLowerCase(),
      c.does.toLowerCase(),
      `${c.demonstrates} ${trap}`.toLowerCase(),
    ],
  };
});

/** Every token must hit at least one field. The score is the sum of each token's best field. */
export function search(query: string, filters: SearchFilters = {}): readonly SearchHit[] {
  const tokens = query.toLowerCase().split(/\s+/).filter(Boolean);
  const hits: SearchHit[] = [];
  for (const row of ROWS) {
    const { entry } = row;
    if (filters.screenId && entry.screen.id !== filters.screenId) continue;
    if (filters.kind && entry.control.kind !== filters.kind) continue;
    if (filters.trapsOnly && !entry.control.trap) continue;
    let score = 0;
    let matchedAll = true;
    for (const token of tokens) {
      let best = 0;
      for (let i = 0; i < row.fields.length; i++) {
        if (row.fields[i].includes(token)) best = Math.max(best, WEIGHTS[i]);
      }
      if (best === 0) {
        matchedAll = false;
        break;
      }
      score += best;
    }
    if (matchedAll) hits.push({ ...entry, score });
  }
  // Stable: score first, then the order the model declares, so an empty query renders in
  // screen order rather than in map-iteration order.
  return hits.sort((a, b) => b.score - a.score || ALL_ANCHORS.indexOf(a.anchor) - ALL_ANCHORS.indexOf(b.anchor));
}

export const CONTROL_KINDS: readonly ControlKind[] = [...new Set([...byAnchor.values()].map((e) => e.control.kind))].sort();

/**
 * Model self-consistency, used by the drift test. Kept here rather than in the test so a
 * violation can also be caught in development by calling it from a scratch script.
 */
export function assertModelIntegrity(): void {
  const problems: string[] = [];
  const seen = new Set<Anchor>();
  const kebab = /^[a-z0-9]+(-[a-z0-9]+)*$/;
  for (const screen of GUIDE) {
    if (!kebab.test(screen.id)) problems.push(`screen id "${screen.id}" is not kebab-case`);
    for (const control of screen.controls) {
      const anchor = anchorOf(screen, control);
      if (!kebab.test(control.id)) problems.push(`${anchor}: control id is not kebab-case`);
      if (seen.has(anchor)) problems.push(`${anchor}: duplicate anchor`);
      seen.add(anchor);
      if (control.availability && control.availability !== "always" && !control.requires) {
        problems.push(`${anchor}: availability "${control.availability}" needs a plain-language requires`);
      }
      if (control.revealedBy && !byAnchor.has(control.revealedBy)) {
        problems.push(`${anchor}: revealedBy "${control.revealedBy}" is not a known anchor`);
      }
      for (const rel of control.related ?? []) {
        if (!byAnchor.has(rel)) problems.push(`${anchor}: related "${rel}" is not a known anchor`);
      }
      for (const id of control.concepts ?? []) {
        if (!conceptById.has(id)) problems.push(`${anchor}: concept "${id}" is not defined in concepts.ts`);
      }
      for (const r of control.reading ?? []) {
        if (/^https?:/i.test(r.path)) problems.push(`${anchor}: reading "${r.path}" must be a repo-relative path`);
      }
    }
    for (const id of screen.concepts ?? []) {
      if (!conceptById.has(id)) problems.push(`${screen.id}: concept "${id}" is not defined in concepts.ts`);
    }
    for (const a of screen.sharedControls ?? []) {
      if (!a.startsWith("shared.")) problems.push(`${screen.id}: sharedControls entry "${a}" is not from the shared screen`);
      if (!byAnchor.has(a)) problems.push(`${screen.id}: sharedControls entry "${a}" is not a known anchor`);
    }
  }
  for (const concept of CONCEPTS) {
    for (const a of concept.seenAt ?? []) {
      if (!byAnchor.has(a)) problems.push(`concept ${concept.id}: seenAt "${a}" is not a known anchor`);
    }
  }
  if (problems.length) throw new Error(`Guide model is inconsistent:\n  ${problems.join("\n  ")}`);
}
