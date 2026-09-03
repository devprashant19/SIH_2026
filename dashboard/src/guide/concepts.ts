import type { GuideConcept } from "./model";

/**
 * The ideas a reader needs in order to understand what the screens are showing. These are what
 * turn a list of buttons into an explanation of the tool.
 */
export const CONCEPTS: readonly GuideConcept[] = [
  {
    id: "period",
    term: "Submission period",
    plain:
      "Entities submit their SOC records on a cycle, one batch per month. Everything the tool produces belongs to one period: features, findings, peer baselines and the risk score. Two periods are never mixed, because a weakness found in March is a statement about March.",
    seenAt: ["global.period"],
  },
  {
    id: "execution-gap",
    term: "Execution gap",
    plain:
      "A capability the entity documents but does not appear to exercise. The records show the alerts arriving and being closed, but the work in between is missing or implausible: closures faster than a human could investigate, notes copied between cases, critical alerts closed without escalation.",
    seenAt: ["portfolio.heatmap"],
  },
  {
    id: "negative-space",
    term: "Negative space",
    plain:
      "Evidence that should be present and is not. A critical asset that reported alerts for three periods and now reports none. A category every peer sees and this entity never does. Negative space is harder to spot than a bad alert, because there is nothing on screen to look at, which is exactly why the tool looks for it.",
    seenAt: ["coverage.matrix"],
  },
  {
    id: "sri",
    term: "Supervisory Risk Indicator",
    plain:
      "One number from 0 to 100 per entity per period, built as a plain weighted sum of six dimensions so the arithmetic can be read off the screen. Execution gap carries 0.30, negative space 0.25, escalation discipline and investigation quality 0.15 each, data integrity 0.10 and a trend penalty 0.05. Bands: below 25 is low, then elevated, high, and 75 or above is critical.",
    formula: "SRI = Σ weight_d × score_d",
    seenAt: ["entity.sri-table", "portfolio.heatmap"],
  },
  {
    id: "t-star",
    term: "Decision threshold t*",
    plain:
      "Where the tool stops guessing and starts deciding. It is derived from what the two mistakes cost rather than chosen by hand. Missing a real weakness is costed higher than sending a healthy entity for review, so the threshold sits low and the tool favours catching things. Execution gap findings use 1 against 4, giving 0.20; negative space uses 1 against 3, giving 0.25.",
    formula: "t* = C_FP / (C_FP + C_FN)",
    seenAt: ["config.cost-cfn", "finding.threshold"],
  },
  {
    id: "uncertainty-band",
    term: "Uncertainty band",
    plain:
      "A margin either side of the threshold, 0.10 wide by default, inside which the tool refuses to decide. Anything landing there is marked uncertain and goes to a human, sorted first. The count of uncertain findings is the honest measure of how much examiner time a period actually needs.",
    formula: "auto-flag if p ≥ t* + δ · auto-clear if p ≤ t* − δ · otherwise a human decides",
    seenAt: ["portfolio.tile-uncertain", "finding.threshold"],
  },
  {
    id: "expected-cost",
    term: "Expected cost",
    plain:
      "A finding's probability multiplied by the cost of missing it. It is what the review queue is sorted by, so the top of the queue is where an examiner's next hour is worth the most, rather than simply where the score is highest.",
    formula: "expected cost = p × C_FN",
    seenAt: ["queue.table"],
  },
  {
    id: "priority-rank",
    term: "Supervisory priority",
    plain:
      "The order entities appear in. It combines the risk score with how confident the tool is in it and with how much the entity matters, judged by sector and size. A high score computed from thin data ranks below a moderate score computed from full data.",
    seenAt: ["portfolio.heatmap"],
  },
  {
    id: "peer-group",
    term: "Peer group",
    plain:
      "Entities are compared against others of the same sector and size band. Where too few peers exist the group widens to the sector, then to the whole portfolio, and the screen says which level was used. Comparisons use the median and the median absolute deviation rather than the mean, so one outlier cannot move the baseline.",
    seenAt: ["peer.chart", "finding.tab-evidence"],
  },
  {
    id: "calibration",
    term: "Calibration",
    plain:
      "An anomaly score is a ranking, not a probability. Calibration maps scores onto probabilities using labelled outcomes, which is what makes a threshold meaningful. Until enough labelled feedback exists the tool says so and shows the score uncalibrated rather than dressing a rank up as a probability.",
    seenAt: ["finding.threshold"],
  },
  {
    id: "support",
    term: "Support",
    plain:
      "How many records a number rests on. A closure-time median over six alerts is not evidence. Every feature carries its count, thin ones are marked and excluded from rules and peer comparison, and the risk score's confidence falls when many of its inputs are thin.",
    seenAt: ["entity.sri-table"],
  },
  {
    id: "provenance-chain",
    term: "Provenance chain",
    plain:
      "Every run records the hash of the code, the configuration and the inputs, and links to the hash of the run before it. Changing a past record breaks the chain and the verify button says so. It is what lets a finding be defended months later.",
    seenAt: ["global.provenance", "audit.verify"],
  },
];

export const CONCEPT_IDS: readonly string[] = CONCEPTS.map((c) => c.id);
