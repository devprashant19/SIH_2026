import type { Anchor } from "./model";
import type { Side } from "./usePlacement";

export type TourAction =
  | { type: "navigate"; to: string; params?: Record<string, string | undefined> }
  | { type: "expandNav" }
  | { type: "setParam"; key: string; value?: string }
  | { type: "click"; anchor: Anchor };

/** What to do when a step's anchor is not on the page. */
export type MissingPolicy =
  /** Advance silently. Right for a step that only makes sense with data. */
  | "skip"
  /** Show the popover unanchored, saying what would reveal the control. */
  | "explain"
  /** Keep watching and advance the moment it appears. Right for "click this to open a panel". */
  | "wait";

export interface TourStep {
  anchor: Anchor;
  title: string;
  body: string;
  /** Where the anchor lives. Used to detect that the user has navigated away. */
  routePattern: string;
  before?: readonly TourAction[];
  onMissing?: MissingPolicy;
  prefer?: readonly Side[];
  padding?: number;
  /** When true the target stays clickable through the spotlight hole. */
  interactive?: boolean;
}

export interface TourDefinition {
  id: string;
  title: string;
  description: string;
  steps: readonly TourStep[];
}

export const TOURS: readonly TourDefinition[] = [
  {
    id: "onboarding",
    title: "How a supervisor uses this tool",
    description:
      "Nine steps following the path the dashboard is built around: from the portfolio ranking down to the alerts behind one finding, and back up to the record of how it was produced.",
    steps: [
      {
        anchor: "global.period",
        title: "Everything belongs to a period",
        body: "Entities submit on a cycle and the whole screen answers for one of them. This selector is global: it follows you between screens and stays in the address bar, so any view can be shared as a link.",
        routePattern: "/portfolio",
        before: [{ type: "navigate", to: "/portfolio" }],
        prefer: ["bottom"],
      },
      {
        anchor: "portfolio.lens-capability",
        title: "Two ways to read the same portfolio",
        body: "The heatmap columns are the six dimensions of the risk score by default. Switch to capability areas and the same entities are re-columned into what a security operations centre is supposed to be able to do, which is the language a supervisory letter uses.",
        routePattern: "/portfolio",
        prefer: ["bottom", "left"],
      },
      {
        anchor: "portfolio.tile-uncertain",
        title: "The decisions the tool refuses to make",
        body: "Findings whose probability lands within the band around the decision threshold are never decided automatically. This count is the honest measure of how much examiner time the period needs, and it is deliberately not hidden.",
        routePattern: "/portfolio",
        onMissing: "skip",
        prefer: ["bottom"],
      },
      {
        anchor: "portfolio.heatmap",
        title: "Ranked by priority, not by score",
        body: "Row order combines the risk score with how confident the tool is in it and with how much the entity matters. Every cell prints its number as well as its colour, so nothing depends on colour alone.",
        routePattern: "/portfolio",
        onMissing: "skip",
        prefer: ["top"],
      },
      {
        anchor: "entity.sri-table",
        title: "The score taken apart",
        body: "Score, weight and contribution per dimension, adding up to the total in the heading. You can check the arithmetic by hand. Clicking a row filters the findings below to that dimension, which is how a number becomes a list of evidence.",
        routePattern: "/entities/:entityId",
        before: [{ type: "click", anchor: "portfolio.heatmap-cell" }],
        onMissing: "wait",
        prefer: ["bottom", "top"],
      },
      {
        anchor: "finding.threshold",
        title: "A decision is a position on a line",
        body: "The threshold comes from what the two mistakes cost, not from a guess. The shaded band around it is the region handed to a human. This finding's probability is marked, so you can see how close to the boundary it fell.",
        routePattern: "/findings/:findingId",
        before: [{ type: "click", anchor: "entity.findings-first-row" }],
        onMissing: "wait",
        prefer: ["bottom"],
      },
      {
        anchor: "finding.tab-records",
        title: "Three clicks to the actual alerts",
        body: "Portfolio, entity, finding, and here are the individual records underneath it, each traceable to the line it came from in the submitted file. Nothing is asserted that cannot be traced back.",
        routePattern: "/findings/:findingId",
        interactive: true,
        prefer: ["bottom"],
      },
      {
        anchor: "finding.feedback",
        title: "The examiner decides, and the tool learns",
        body: "Accept, reject or defer with a comment. Decisions are appended and never overwritten, and they are what calibrates model scores into probabilities. The tool is an aid, not an authority.",
        routePattern: "/findings/:findingId",
        prefer: ["top", "bottom"],
      },
      {
        anchor: "global.provenance",
        title: "Every number can be traced back",
        body: "This chip names the code and configuration that produced what you are looking at. Each run's hash covers the previous run's, so altering a past record breaks the chain, and the audit screen can prove it has not been.",
        routePattern: "/findings/:findingId",
        prefer: ["bottom", "left"],
      },
    ],
  },
];

export const TOUR_BY_ID: ReadonlyMap<string, TourDefinition> = new Map(TOURS.map((t) => [t.id, t]));
