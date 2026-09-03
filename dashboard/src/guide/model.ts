/**
 * The single source of truth for the in-app guide.
 *
 * Every control described here is anchored to a real element by a `data-guide` attribute whose
 * value is `${screen.id}.${control.id}`. A test reconciles the two in both directions, so a
 * renamed control fails the build rather than silently producing a guide that describes a
 * button nobody can find.
 */

/** The dotted string that appears verbatim in `data-guide="…"`. */
export type Anchor = string;

export type ControlKind =
  | "nav-link"
  | "button"
  | "toggle"
  | "select"
  | "checkbox"
  | "text-input"
  | "number-input"
  | "file-input"
  | "link"
  | "tab"
  | "table"
  | "table-row"
  | "table-cell"
  | "chart"
  | "badge"
  | "readout"
  | "panel";

/** Where the control physically is, which tells the tour what it must do before it can be seen. */
export type Availability =
  | "always" // present on first paint, no data required
  | "requires-data" // behind a query boundary; absent while loading or when the API returns nothing
  | "in-tab" // only rendered when a tab or scope parameter is set
  | "in-drawer" // only rendered while a drawer is open
  | "conditional"; // any other precondition, described in `requires`

export interface UrlParamEffect {
  /** The exact key passed to useSearchParamState or usePeriodParam. */
  param: string;
  /** Human enumeration of the values this control writes, e.g. "sri | capability". */
  values?: string;
  /** The value at which the parameter is deleted from the URL rather than written. */
  clearedAt?: string;
}

export interface KeyHint {
  /** Rendered inside <kbd>, e.g. "Shift + /" or "A". */
  keys: string;
  /** The scope in which the shortcut is live. */
  when?: string;
  description: string;
}

/** A first-time-user pitfall. Rendered with a distinct outline on every surface. */
export interface Trap {
  summary: string;
  symptom: string;
  fix: string;
}

export interface GuideControl {
  /** Kebab-case local id. `${screen.id}.${id}` is the data-guide value and is globally unique. */
  id: string;
  /** The exact on-screen text, or the aria-label when the control has no visible text. */
  label: string;
  kind: ControlKind;
  /** What literally happens when it is used. One sentence, present tense, observable. */
  does: string;
  /** The supervisory idea it makes visible. One or two sentences, not UI language. */
  demonstrates: string;
  /** Concept ids from concepts.ts that this control surfaces. */
  concepts?: readonly string[];
  /** Every URL parameter this control writes. */
  writesParams?: readonly UrlParamEffect[];
  /** Route pattern this control navigates to, e.g. "/entities/:entityId". */
  navigatesTo?: string;
  keys?: readonly KeyHint[];
  trap?: Trap;
  /** Defaults to "always". */
  availability?: Availability;
  /** Plain-language precondition. Required whenever availability is not "always". */
  requires?: string;
  /** The anchor that must be used first for this one to exist. */
  revealedBy?: Anchor;
  related?: readonly Anchor[];
  /** Repo-relative documentation paths. Never an http(s) URL: the offline build check bans them. */
  reading?: readonly { title: string; path: string }[];
  /**
   * Set when the control is described but deliberately carries no data-guide attribute, for
   * instance a whole family of charts described once. The drift test skips these in the
   * model-to-source direction.
   */
  undocumentedInDom?: boolean;
}

export interface GuideConcept {
  /** Kebab-case id referenced from GuideControl.concepts and GuideScreen.concepts. */
  id: string;
  term: string;
  /** One paragraph, no jargon. */
  plain: string;
  formula?: string;
  /** Anchors where the concept is visible on screen. */
  seenAt?: readonly Anchor[];
}

export interface GuideScreen {
  /** Stable id, equal to the nav key where one exists. Never renamed once shipped. */
  id: string;
  /** Must equal the on-screen h1. */
  title: string;
  /** React Router path pattern, matched with matchPath. "*" for the two pseudo-screens. */
  routePattern: string;
  /**
   * True for the two pseudo-screens that are not routes: "global", the chrome present on every
   * screen, and "shared", the filters that mean the same thing wherever they appear.
   */
  chrome?: boolean;
  /** The nav item that leads here, when one does. */
  navKey?: string;
  /** One sentence: the supervisory question this screen answers. */
  purpose: string;
  /** Parameters this screen reads. A superset of what its own controls write. */
  readsParams: readonly string[];
  /** How a user arrives here, in prose. */
  reachedBy: readonly string[];
  controls: readonly GuideControl[];
  /**
   * Anchors from the "shared" pseudo-screen that also appear here. Described once, listed on
   * every screen that uses them, so five screens do not carry five copies of "Sector".
   */
  sharedControls?: readonly Anchor[];
  concepts?: readonly string[];
}

export const anchorOf = (screen: { id: string }, control: { id: string }): Anchor => `${screen.id}.${control.id}`;

/**
 * Spread onto any element to anchor it: `<Button {...guide("portfolio.lens-sri")}>`.
 * The argument must be a string literal; the drift test enforces that, because a computed
 * anchor cannot be reconciled against the model by reading the source.
 */
export const guide = (anchor: Anchor) => ({ "data-guide": anchor }) as const;
