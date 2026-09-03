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
        title: "Time Period",
        body: "Every piece of data belongs to a specific month or quarter.",
        note: "This drop-down stays with you as you move around. Change it here, and the whole app instantly travels to that time period.",
        routePattern: "/portfolio",
        before: [{ type: "navigate", to: "/portfolio" }],
        prefer: ["bottom"],
      },
      {
        anchor: "portfolio.heatmap",
        title: "Who needs help first?",
        body: "This shows a list of companies. The ones at the top have the biggest security problems.",
        note: "We rank them by how sure we are about the problem, not just raw scores. A huge problem with solid proof goes to the very top.",
        routePattern: "/portfolio",
        onMissing: "skip",
        prefer: ["top"],
      },
      {
        anchor: "portfolio.lens-capability",
        title: "Two ways to look",
        body: "You can view these scores by 'Risk Category' or by 'Security Capability'.",
        note: "Just toggle this button to see the exact same data from a different perspective, without reloading anything.",
        routePattern: "/portfolio",
        prefer: ["bottom", "left"],
      },
      {
        anchor: "portfolio.tile-uncertain",
        title: "Borderline cases",
        body: "Sometimes the AI isn't 100% sure. We call these 'Uncertain' cases.",
        note: "Instead of guessing, the system flags these borderline cases so a human expert can look at them closely.",
        routePattern: "/portfolio",
        onMissing: "skip",
        prefer: ["bottom"],
      },

      // ---- entity --------------------------------------------------------------------
      {
        anchor: "entity.sri-table",
        title: "How the score is made",
        body: "This breaks down exactly how we calculated the final risk score for this company.",
        note: "We don't hide the math! You can see all the weights and scores adding up perfectly right here.",
        routePattern: "/entities/:entityId",
        before: [{ type: "click", anchor: "portfolio.heatmap-cell" }],
        onMissing: "wait",
        prefer: ["bottom", "top"],
      },
      {
        anchor: "entity.peer-chart",
        title: "Grading on a curve",
        body: "A score doesn't mean much on its own. This chart shows how this company compares to similar companies.",
        note: "If a company is doing badly, but everyone else in their industry is also doing badly, you'll see that context here.",
        routePattern: "/entities/:entityId",
        onMissing: "skip",
        prefer: ["left", "bottom"],
      },

      // ---- finding -------------------------------------------------------------------
      {
        anchor: "finding.threshold",
        title: "The decision line",
        body: "This line shows exactly why a problem was flagged.",
        note: "If a dot lands far to the right, it's a huge problem. If it lands near the middle band, we ask a human to double-check it.",
        routePattern: "/findings/:findingId",
        before: [
          { type: "setParam", key: "dimension" },
          { type: "setParam", key: "capability" },
          { type: "click", anchor: "entity.findings-first-row" },
        ],
        onMissing: "wait",
        prefer: ["bottom"],
      },
      {
        anchor: "finding.tab-records",
        title: "Show me the proof",
        body: "Don't just trust the AI! Click here to see the raw, original logs submitted by the company.",
        note: "Every single claim the system makes can be traced back to these exact log files.",
        routePattern: "/findings/:findingId",
        interactive: true,
        prefer: ["bottom"],
      },
      {
        anchor: "finding.feedback",
        title: "You are the boss",
        body: "Do you disagree with the AI? Tell it by clicking Reject.",
        note: "When you reject a finding, the system actually learns from your choice so it won't make the same mistake next month.",
        routePattern: "/findings/:findingId",
        prefer: ["top", "bottom"],
      },

      // ---- queue ---------------------------------------------------------------------
      {
        anchor: "queue.table",
        title: "Your To-Do List",
        body: "This is a prioritized list of exact alerts you need to review manually.",
        note: "The most important and borderline cases are pushed to the very top so you don't waste time on obvious stuff.",
        routePattern: "/queue",
        before: [{ type: "navigate", to: "/queue" }],
        onMissing: "skip",
        prefer: ["top"],
      },
      {
        anchor: "queue.scope-control",
        title: "Zoom out",
        body: "You can view your To-Do list by individual alerts, or group them by Companies and Processes.",
        note: "Sometimes seeing that a specific process is failing across five different companies is the most useful insight.",
        routePattern: "/queue",
        prefer: ["bottom"],
      },

      // ---- peer ----------------------------------------------------------------------
      {
        anchor: "peer.chart",
        title: "The Big Picture",
        body: "See how an entire industry is performing at a single glance.",
        note: "The selected company is highlighted so you can see exactly where they sit compared to their peers.",
        routePattern: "/peer",
        before: [{ type: "navigate", to: "/peer" }],
        onMissing: "skip",
        prefer: ["bottom", "top"],
      },

      // ---- coverage ------------------------------------------------------------------
      {
        anchor: "coverage.matrix",
        title: "What is missing?",
        body: "This looks for alerts that SHOULD exist, but don't. Missing cells are marked with lines.",
        note: "If a bank has servers but reports zero server alerts all month, this page will catch that silence.",
        routePattern: "/coverage",
        before: [{ type: "navigate", to: "/coverage" }],
        onMissing: "skip",
        prefer: ["top"],
      },

      // ---- trends --------------------------------------------------------------------
      {
        anchor: "trends.sri-chart",
        title: "Getting better or worse?",
        body: "This chart tracks a company's risk over many months.",
        note: "A single bad month is okay, but a line that keeps going up means the company is slowly falling apart.",
        routePattern: "/trends",
        before: [{ type: "navigate", to: "/trends" }],
        onMissing: "skip",
        prefer: ["top"],
      },

      // ---- ingestion -----------------------------------------------------------------
      {
        anchor: "ingestion.submissions",
        title: "Messy data is a red flag",
        body: "If a company submits broken or sloppy data, we don't throw it away.",
        note: "We actually penalize them for it! You can see exactly how many errors their files had right here.",
        routePattern: "/ingestion",
        before: [{ type: "navigate", to: "/ingestion" }],
        onMissing: "skip",
        prefer: ["top"],
      },
      {
        anchor: "ingestion.run",
        title: "Run the math",
        body: "Click here to process all the new data and generate fresh scores.",
        note: "The system only runs when you tell it to. It will analyze millions of alerts in just a few seconds.",
        routePattern: "/ingestion",
        prefer: ["bottom", "left"],
      },

      // ---- config --------------------------------------------------------------------
      {
        anchor: "config.cost-cfn",
        title: "Change how strict the AI is",
        body: "Want the system to be more aggressive or more relaxed? Adjust the slider here.",
        note: "This changes the math everywhere immediately, without needing to reload or retrain anything.",
        routePattern: "/config",
        before: [{ type: "navigate", to: "/config" }],
        onMissing: "explain",
        prefer: ["bottom", "top"],
      },
      {
        anchor: "config.rules",
        title: "The Brain",
        body: "These are the 19 hard-coded rules the system uses to catch bad security practices.",
        note: "You can see the exact logic behind every rule, and even turn them off if you want.",
        routePattern: "/config",
        prefer: ["top"],
      },

      // ---- audit ---------------------------------------------------------------------
      {
        anchor: "audit.verify",
        title: "Tamper-proof records",
        body: "Click Verify to mathematically prove that no one has secretly changed the data.",
        note: "Every action is cryptographically locked into a chain. If someone edits a database row behind your back, this button will catch them.",
        routePattern: "/audit",
        before: [{ type: "navigate", to: "/audit" }],
        prefer: ["bottom", "left"],
      },

      // ---- reports -------------------------------------------------------------------
      {
        anchor: "reports.entity-pdf",
        title: "Take it with you",
        body: "Export all these beautiful charts and findings into a PDF report.",
        note: "The PDF includes digital fingerprints showing exactly what version of the tool was used to create it.",
        routePattern: "/reports",
        before: [{ type: "navigate", to: "/reports" }],
        prefer: ["bottom", "top"],
      },
    ],
  },
];

export const TOUR_BY_ID: ReadonlyMap<string, TourDefinition> = new Map(TOURS.map((t) => [t.id, t]));
