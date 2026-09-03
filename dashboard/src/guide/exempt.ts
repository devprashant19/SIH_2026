/**
 * Interactive elements that deliberately carry no guide anchor.
 *
 * The drift test fails on any interactive element that is neither anchored nor listed here, so
 * adding a button to the dashboard forces a choice: describe it, or write down why not. The
 * reason is the point of this file. Keyed by file and symbol rather than line, so formatting
 * churn does not break it.
 */
export interface Exemption {
  file: string;
  symbol: string;
  reason: string;
}

export const EXEMPT_CONTROLS: readonly Exemption[] = [
  // ---- generic table and chart machinery, described once at the table level ----------------
  {
    file: "src/components/data/DataTable.tsx",
    symbol: "button",
    reason: "Column sort headers. Generic across every table; the behaviour is described on each table's own entry.",
  },
  {
    file: "src/components/data/DataTable.tsx",
    symbol: "tr",
    reason: "Row click. Anchored per table through firstRowGuide instead, so one row carries the anchor rather than all of them.",
  },
  {
    file: "src/components/charts/RiskHeatmap.tsx",
    symbol: "button",
    reason: "Every heatmap cell. Only the first is anchored, as portfolio.heatmap-cell.",
  },
  {
    file: "src/components/charts/PeerDistributionChart.tsx",
    symbol: "Scatter",
    reason: "Points drawn inside an SVG by the charting library, with no stable element to anchor. Described as peer.chart-mark.",
  },
  {
    file: "src/components/charts/TrendChart.tsx",
    symbol: "Line",
    reason: "Series drawn by the charting library. The chart as a whole carries the anchor.",
  },
  {
    file: "src/components/charts/TrendChart.tsx",
    symbol: "LineChart",
    reason: "The chart container, which takes a click handler for legend toggling. The card around it carries the anchor.",
  },

  // ---- primitives whose behaviour belongs to their caller ----------------------------------
  {
    file: "src/components/ui/primitives.tsx",
    symbol: "button",
    reason: "The Button and Tabs primitives themselves. Anchors are supplied by call sites.",
  },
  {
    file: "src/components/ui/primitives.tsx",
    symbol: "Button",
    reason: "The Drawer close button and the error-state retry, present on every drawer and every failed query.",
  },
  {
    file: "src/components/ui/primitives.tsx",
    symbol: "select",
    reason: "The Select primitive itself. Anchors are supplied by call sites.",
  },
  {
    file: "src/components/ui/primitives.tsx",
    symbol: "div",
    reason: "The Drawer backdrop, which closes on click. Described as part of whichever drawer opens it.",
  },
  {
    file: "src/components/data/FilterBar.tsx",
    symbol: "Select",
    reason: "The FilterSelect primitive. Each call site passes its own anchor through the guide prop.",
  },
  {
    file: "src/components/data/FilterBar.tsx",
    symbol: "input",
    reason: "The FilterToggle primitive. Each call site passes its own anchor through the guide prop.",
  },
  {
    file: "src/components/data/Pickers.tsx",
    symbol: "Select",
    reason: "PeriodPicker, EntityPicker and SectorPicker, all three anchored inside the component itself.",
  },

  // ---- affordances that are not supervisory controls ----------------------------------------
  {
    file: "src/components/ui/primitives.tsx",
    symbol: "HashChip",
    reason: "Copies a hash to the clipboard. A convenience on a readout, not a control of its own.",
  },
  {
    file: "src/features/finding/FindingPage.tsx",
    symbol: "tr",
    reason: "Evidence rows, selected by the model-attribution buttons. Described as part of finding.tab-evidence.",
  },
  {
    file: "src/features/finding/FindingPage.tsx",
    symbol: "Button",
    reason: "Evidence pagination and the record drawer's close. Standard paging on a table already described.",
  },
  {
    file: "src/features/entity/EntityPage.tsx",
    symbol: "tr",
    reason: "Scorecard rows beyond the first, which is anchored as entity.sri-row.",
  },
  {
    file: "src/features/audit/AuditPage.tsx",
    symbol: "tr",
    reason: "Audit rows beyond the first, which is anchored as audit.run-row.",
  },
  {
    file: "src/features/audit/AuditPage.tsx",
    symbol: "Button",
    reason: "The per-type filter buttons, described together as audit.type-filter.",
  },
  {
    file: "src/features/coverage/CoveragePage.tsx",
    symbol: "button",
    reason: "Matrix cells beyond the first, which is anchored as coverage.matrix-cell.",
  },
  {
    file: "src/features/coverage/CoveragePage.tsx",
    symbol: "Button",
    reason: "The cell panel's Close button.",
  },
  {
    file: "src/features/config/ConfigPage.tsx",
    symbol: "input",
    reason: "Per-dimension weight inputs and per-rule enable checkboxes, described together as config.weights and config.rules.",
  },
  {
    file: "src/features/reports/ReportsPage.tsx",
    symbol: "Select",
    reason: "The report period selector, described alongside reports.entity-select.",
  },
  {
    file: "src/features/reports/ReportsPage.tsx",
    symbol: "Button",
    reason: "The remaining portfolio CSV buttons, described together as reports.portfolio-csv.",
  },
  {
    file: "src/features/ingestion/IngestionPage.tsx",
    symbol: "tr",
    reason: "Submission rows, which expand their own validation detail. Described as part of ingestion.submissions.",
  },
  {
    file: "src/components/domain/FeedbackBar.tsx",
    symbol: "Button",
    reason: "Accept, Reject and Defer, described together as finding.feedback and queue.drawer-feedback.",
  },
  {
    file: "src/components/domain/FeedbackBar.tsx",
    symbol: "input",
    reason: "The comment and reviewer fields of the feedback bar.",
  },
  {
    file: "src/components/domain/FeedbackBar.tsx",
    symbol: "div",
    reason: "The bar itself, which carries the keyboard handler for its three shortcuts.",
  },
  {
    file: "src/components/data/PlaceholderPage.tsx",
    symbol: "Button",
    reason: "The not-found screen, which is not part of the supervisory workflow.",
  },
];
