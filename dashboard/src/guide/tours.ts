import type { Anchor } from "./model";
import type { Side } from "./usePlacement";

export type TourAction =
  | { type: "navigate"; to: string; params?: Record<string, string | undefined> }
  | { type: "expandNav" }
  | { type: "setParam"; key: string; value?: string }
  | { type: "click"; anchor: Anchor };

/** What to do when a step's target is not on the page. */
export type MissingPolicy =
  /** Advance silently. Right for a step that only makes sense with data. */
  | "skip"
  /** Show the popup unanchored, saying what would reveal the control. */
  | "explain"
  /** Keep watching and advance the moment it appears. Right for "click this to open a panel". */
  | "wait";

export interface TourStep {
  /** The `data-guide` value of the element to spotlight. */
  anchor: Anchor;
  /** Short heading. */
  title: string;
  /** What the feature does, in one or two sentences. */
  body: string;
  /** Optional: how it is built. Rendered under a quieter "How it works" heading. */
  note?: string;
  /** The route the target lives on. Also used to detect that the user has navigated away. */
  routePattern: string;
  /** Navigation, filtering or clicking to perform before the target can be seen. */
  before?: readonly TourAction[];
  onMissing?: MissingPolicy;
  /** Preferred popup sides, in order. */
  prefer?: readonly Side[];
  /** Extra spotlight padding in pixels. */
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

/**
 * The whole product in 20 steps, one pass through all eleven screens.
 *
 * Edit `title`, `body` and `note` freely — they are the only prose here. `anchor` must stay a
 * value that some element carries as `data-guide`; the drift test fails the build otherwise.
 */
export const TOURS: readonly TourDefinition[] = [
  {
    id: "onboarding",
    title: "Every feature, in order",
    description: "One pass through all eleven screens, following the path a supervisor actually works.",
    steps: [
      // ---- portfolio -----------------------------------------------------------------
      {
        anchor: "global.period",
        title: "Everything belongs to a period",
        body: "Entities submit their records on a cycle, and the whole screen answers for one of them. This selector is global: it follows you between screens, so any two screens are always about the same submission.",
        note: "It writes the period into the address bar rather than into component state, so every view is a shareable link and the browser back button works.",
        routePattern: "/portfolio",
        before: [{ type: "navigate", to: "/portfolio" }],
        prefer: ["bottom"],
      },
      {
        anchor: "portfolio.heatmap",
        title: "Who needs attention first",
        body: "One row per entity, ordered by supervisory priority rather than by raw score, with a cell per risk dimension. Every cell prints its number as well as its colour.",
        note: "Priority combines the risk score with the confidence in it and with how much the entity matters by sector and size, so a high score computed from thin data ranks below a moderate one computed from full data.",
        routePattern: "/portfolio",
        onMissing: "skip",
        prefer: ["top"],
      },
      {
        anchor: "portfolio.lens-capability",
        title: "Two ways to read the same portfolio",
        body: "The columns are the six dimensions of the risk score by default. Switch to capability areas and the same entities are re-columned into what a security operations centre is supposed to be able to do.",
        note: "Every rule is mapped to both a risk dimension and a capability area, so one set of findings supports both framings without recomputing anything.",
        routePattern: "/portfolio",
        prefer: ["bottom", "left"],
      },
      {
        anchor: "portfolio.tile-uncertain",
        title: "The decisions the tool refuses to make",
        body: "Findings whose probability lands inside the band around the decision threshold are never decided automatically. This count is the honest measure of how much examiner time the period needs.",
        note: "The threshold comes from what the two mistakes cost, false-positive cost over the sum of both costs, with a fixed band either side of it. Anything inside that band is routed to a human by design.",
        routePattern: "/portfolio",
        onMissing: "skip",
        prefer: ["bottom"],
      },

      // ---- entity --------------------------------------------------------------------
      {
        anchor: "entity.sri-table",
        title: "The score, taken apart",
        body: "Score, weight and contribution for each dimension, adding up to the total in the heading. You can check the arithmetic by hand. Clicking a row filters the findings below to that dimension.",
        note: "A plain weighted sum, deliberately, so no part of the headline number is hidden inside a model. The weights live in configuration and are hashed into every run that uses them.",
        routePattern: "/entities/:entityId",
        before: [{ type: "click", anchor: "portfolio.heatmap-cell" }],
        onMissing: "wait",
        prefer: ["bottom", "top"],
      },
      {
        anchor: "entity.peer-chart",
        title: "Compared with its peers",
        body: "Where this entity sits among comparable entities for the chosen metric. A raw value means little on its own; its position among peers is the supervisory question.",
        note: "Peers are the same sector and size band, widening to sector then to the whole portfolio when too few exist. Comparisons use the median and median absolute deviation, so one outlier cannot move the baseline it is judged against.",
        routePattern: "/entities/:entityId",
        onMissing: "skip",
        prefer: ["left", "bottom"],
      },

      // ---- finding -------------------------------------------------------------------
      {
        anchor: "finding.threshold",
        title: "A decision is a position on a line",
        body: "The threshold, the band handed to a human, and this finding's probability marked on it, so you can see how close to the boundary it fell.",
        note: "Cost-derived rather than tuned. Missing a real weakness is costed higher than an unnecessary review, which pushes the threshold down and makes the tool favour catching things.",
        routePattern: "/findings/:findingId",
        before: [
          // The heatmap cell arrives with a dimension filter set, which can leave the
          // findings table empty. Clear it before asking for the top row.
          { type: "setParam", key: "dimension" },
          { type: "setParam", key: "capability" },
          { type: "click", anchor: "entity.findings-first-row" },
        ],
        onMissing: "wait",
        prefer: ["bottom"],
      },
      {
        anchor: "finding.tab-records",
        title: "Down to the actual alerts",
        body: "Portfolio, entity, finding, and here are the individual records underneath the claim, each traceable to the line it came from in the submitted file.",
        note: "Findings store the alert ids they rest on, and every ingested row keeps its source line number, so nothing is asserted that cannot be traced back.",
        routePattern: "/findings/:findingId",
        interactive: true,
        prefer: ["bottom"],
      },
      {
        anchor: "finding.feedback",
        title: "The examiner decides, and the tool learns",
        body: "Accept, reject or defer with a comment. The tool is an aid, not an authority.",
        note: "Decisions are appended and never overwritten, so the record shows what was thought and when. They are also the labels that calibrate raw model scores into probabilities.",
        routePattern: "/findings/:findingId",
        prefer: ["top", "bottom"],
      },

      // ---- queue ---------------------------------------------------------------------
      {
        anchor: "queue.table",
        title: "What to examine next",
        body: "Alerts selected for manual inspection, in rank order, with the rules that flagged each one.",
        note: "Ranked by expected cost, the probability multiplied by the cost of missing it, so the top of the list is where the next hour of examiner time pays back most. Sampling is round-robin across rules, so every kind of weakness is represented rather than the loudest one filling the list.",
        routePattern: "/queue",
        before: [{ type: "navigate", to: "/queue" }],
        onMissing: "skip",
        prefer: ["top"],
      },
      {
        anchor: "queue.scope-control",
        title: "Entities, alerts, or processes",
        body: "The same queue at three grains. Controls and processes groups findings by the control they implicate and sums the expected cost of each group.",
        note: "Often the most useful supervisory output is not an entity but a process: one control failing across several entities at once.",
        routePattern: "/queue",
        prefer: ["bottom"],
      },

      // ---- peer ----------------------------------------------------------------------
      {
        anchor: "peer.chart",
        title: "The whole peer group at once",
        body: "Every entity in the group plotted for one metric, with the median and the tenth to ninetieth percentile band, and the selected entity marked.",
        note: "The line underneath names which peer group was used and how it was chosen, because a comparison against three peers is worth less than one against thirty and should not be able to hide that.",
        routePattern: "/peer",
        before: [{ type: "navigate", to: "/peer" }],
        onMissing: "skip",
        prefer: ["bottom", "top"],
      },

      // ---- coverage ------------------------------------------------------------------
      {
        anchor: "coverage.matrix",
        title: "Evidence that should be there and is not",
        body: "One row per entity, one column per expected item. Absent cells are hatched and labelled, never colour alone. The totals down the right and along the bottom are the point.",
        note: "This is the harder half of the problem. An execution gap leaves bad records behind, but negative space leaves nothing on screen to look at. Expectation is derived from the entity's own asset inventory, from its sector, and from what its peers actually report.",
        routePattern: "/coverage",
        before: [{ type: "navigate", to: "/coverage" }],
        onMissing: "skip",
        prefer: ["top"],
      },

      // ---- trends --------------------------------------------------------------------
      {
        anchor: "trends.sri-chart",
        title: "Movement across periods",
        body: "Risk over successive submissions, per entity, against the dashed sector median.",
        note: "One period is a snapshot. A weakness that appears and then persists is a different matter from a single bad month, and against a rising median a flat entity is falling behind.",
        routePattern: "/trends",
        before: [{ type: "navigate", to: "/trends" }],
        onMissing: "skip",
        prefer: ["top"],
      },

      // ---- ingestion -----------------------------------------------------------------
      {
        anchor: "ingestion.submissions",
        title: "Dirty data is itself a finding",
        body: "Every submission with its format, row counts and error and warning rates. A row expands to show which checks fired and on which rows.",
        note: "Thirteen validation checks run on ingest and their results are recorded rather than merely rejected. The error and warning rates become features, because an entity that cannot produce clean records is telling you something about its operation.",
        routePattern: "/ingestion",
        before: [{ type: "navigate", to: "/ingestion" }],
        onMissing: "skip",
        prefer: ["top"],
      },
      {
        anchor: "ingestion.run",
        title: "Batch, and only when asked",
        body: "Starts the analysis for the selected period and reports each stage as it completes.",
        note: "There is no scheduler and no continuous collection anywhere in the tool. That is the boundary between supervising a security operations centre and operating one. Re-running on unchanged inputs is skipped rather than repeated, because the pipeline is idempotent.",
        routePattern: "/ingestion",
        prefer: ["bottom", "left"],
      },

      // ---- config --------------------------------------------------------------------
      {
        anchor: "config.cost-cfn",
        title: "Change the posture, not the thresholds",
        body: "Set what it costs to miss a real weakness and the decision threshold recomputes as you type, with the band redrawn on the line below.",
        note: "This is where the caution actually comes from. Because the threshold is derived from the two costs rather than picked by hand, a change in supervisory posture is one number instead of a retuning exercise. Preview shows the effect on every entity before anything is saved.",
        routePattern: "/config",
        before: [{ type: "navigate", to: "/config" }],
        onMissing: "explain",
        prefer: ["bottom", "top"],
      },
      {
        anchor: "config.rules",
        title: "Rules first, model second",
        body: "All nineteen rules with the control and capability each maps to, its parameters, and a checkbox to disable it.",
        note: "Every rule is readable here with the exact thresholds it uses, which is what makes a finding arguable rather than merely asserted. The model only ever adjusts a probability; it never raises a finding without a rule or a template behind it.",
        routePattern: "/config",
        prefer: ["top"],
      },

      // ---- audit ---------------------------------------------------------------------
      {
        anchor: "audit.verify",
        title: "Prove the record was not altered",
        body: "Recomputes every run hash from the one before it and reports either that the chain is intact or the first run where it breaks.",
        note: "Each run's hash covers the previous run's hash, so changing any past record breaks every hash after it. This is the answer to how a finding can be defended months later.",
        routePattern: "/audit",
        before: [{ type: "navigate", to: "/audit" }],
        prefer: ["bottom", "left"],
      },

      // ---- reports -------------------------------------------------------------------
      {
        anchor: "reports.entity-pdf",
        title: "Getting it out of the tool",
        body: "A document with the scorecard arithmetic, every finding with its rationale, the alerts selected for review, and the feedback recorded so far.",
        note: "Each export records the code, configuration and model versions that produced it, so the document is self-contained and a reader without access to the tool can still follow the reasoning.",
        routePattern: "/reports",
        before: [{ type: "navigate", to: "/reports" }],
        prefer: ["bottom", "top"],
      },
    ],
  },
];

export const TOUR_BY_ID: ReadonlyMap<string, TourDefinition> = new Map(TOURS.map((t) => [t.id, t]));
