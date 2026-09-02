# SAT-SA — Model card and operating notes

## Purpose

SAT-SA scores batch submissions of SOC alert and case-management data to help human examiners
decide where to look. It produces indicators for review, never conclusions. Nothing in the
system takes an enforcement action or closes a finding on its own.

## Models

| Name | Type | Input | Output | Trained on |
|---|---|---|---|---|
| `entity_ensemble` | IsolationForest (300 trees) + Local Outlier Factor, optional HDBSCAN | 25 execution-gap features plus their peer z-scores, per entity-period | anomaly score in 0 to 1 | historical entity-period rows |
| `calibrator_a` | Isotonic regression | ensemble score | calibrated probability of an execution gap | labelled entity-periods: seeded ground truth at bootstrap, supervisor feedback thereafter |
| `alert_if` | IsolationForest (200 trees) | 9 per-alert features including note similarity | alert anomaly score | all alerts in the training periods |
| `calibrator_alert` | Isotonic regression | alert score | calibrated alert probability | labelled alerts |
| expected volume | Huber regression | asset count, Tier-1 count, size band, previous volume | expected alert volume for the peer model | entities in the scored period |

Preprocessing is a median imputer followed by a quantile transformer, chosen because
supervisory features are heavy-tailed and sample sizes are small.

## Why calibration matters here

A raw anomaly score is not a probability, and a supervisor reading it as one will
systematically mis-rank entities. Scores are therefore mapped through an isotonic calibrator
before they are shown or compared with a threshold. When there are too few labels to
calibrate honestly, the raw score is passed through unchanged and every affected finding is
marked uncalibrated in the interface rather than being quietly presented as a probability.

## Why the threshold is derived, not chosen

Flagging a healthy entity costs an examiner some hours. Missing a real weakness costs far
more. The decision threshold follows from that ratio, `t* = C_FP / (C_FP + C_FN)`, with the
costs set by the supervisor in configuration. Findings within a band around the threshold are
never auto-decided: they are surfaced as uncertain and sorted to the top of the queue, because
that is exactly the region where the tool should defer to a person.

## Data

Inputs are alert metadata, case-management records, escalation records, closure information
and asset inventory. The system does not require raw logs, packet captures or customer data.
Investigation notes are used only for similarity and length statistics, computed locally.

## Known limitations

- **Cold start.** With one submission period, history-dependent features are unavailable and
  the calibrator has no labels. Rules still work, and the interface says which parts are
  degraded rather than hiding it.
- **Small peer groups.** With few entities in a sector, peer statistics are weak. The system
  falls back to a wider group, records which level it used, and lowers the confidence score.
- **Synthetic-data tuning.** Thresholds are expressed relative to peers wherever possible, but
  they were tuned against seeded data. They should be re-examined against real submissions,
  which is what the feedback loop and the bounded threshold suggestions are for.
- **Templated notes.** Similarity detection is lexical. A SOC that paraphrases boilerplate
  will score lower than one that copies it, even if the substance is equally thin.
- **Not a detector.** SAT-SA assesses whether a SOC's process is working. It does not decide
  whether any individual alert was a true attack.

## Operating requirements

- CPU only, no GPU. Measured at 14,704 alerts across eight entities and six periods: 72
  seconds end to end, 0.33 GB peak resident memory, on one laptop core.
- One Docker image, no database server, no network at runtime.
- A scoring run takes about five seconds per period at that volume; training takes twelve
  seconds. Behaviour beyond this profile is untested and no larger figure is claimed.
- Retraining is manual and explicit. New model versions are registered inactive and become
  active only when promoted.

## Human oversight

Every finding shows its rationale, the peer comparison behind it and the records that
evidence it. Examiners accept, reject or defer, and those decisions are appended to an
audit-logged store. Recalibration uses them to refit the calibrator and to suggest bounded
threshold adjustments, which a person must promote. The audit chain lets anyone confirm that
a stated finding came from a particular code version, configuration and set of inputs.
