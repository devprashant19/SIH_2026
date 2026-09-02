# SAT-SA — Architecture

Supervisory Analytics Tool for SOC Assessment. A deployable, fully offline analytics
capability that helps NCIIPC examiners assess SOC alert and case-management data from
Critical Sector Entities (CSEs) at scale, without replacing supervisory judgement.

## 1. What it does and does not do

| In scope | Out of scope |
|---|---|
| Batch analysis of periodic submissions (CSV, JSON, database export) | Operating as, or replacing, a CSE's SOC |
| Detecting **Execution Gaps** and **Negative Space** across entities | Real-time monitoring or continuous log collection |
| Peer benchmarking, entity risk indicators, prioritised review queues | SIEM functionality or a centralised multi-entity SOC |
| Explainability, evidence drill-down, audit trail, reporting | A national cyber monitoring platform |
| Local deployment on CPU-only hardware inside a controlled environment | Any cloud, SaaS or externally hosted model |

The pipeline runs only when a supervisor asks for it. There is no scheduler, no polling and
no outbound network call anywhere in the codebase; the test suite fails if one is attempted.

## 2. System shape

```
CSE submissions (CSV / JSON / SQLite)  ──►  data/incoming/
        │
        ▼
┌──────────────────────── satsa (Python package) ─────────────────────────────┐
│ ingest      adapters → column mapping → validation V-01..V-13 → DuckDB      │
│ features    per (entity, period): timing · escalation · closure · notes ·   │
│             repeat · coverage · volume · rolling investigated-rates ·       │
│             robust peer z-scores and percentiles                            │
│ analytics   A Execution Gap  : 11 rules + IsolationForest/LOF/HDBSCAN       │
│                                + isotonic calibration + geometric noisy-OR  │
│             B Negative Space : 8 deterministic detectors                     │
│             C Benchmarking   : peer baselines + SRI scorecard                │
│             D Prioritisation : t* = C_FP/(C_FP+C_FN), uncertainty band,      │
│                                entity / control / alert-sample ranking       │
│ explain     SHAP or peer-z attribution · templated rationale · evidence      │
│ audit       append-only run log, hash-chained, verifiable                    │
│ feedback    accept / reject / defer · bounded recalibration                  │
│ models      versioned artifacts, registry, offline promotion                 │
│ reports     PDF and CSV, stamped with code / config / model hashes           │
│ api         FastAPI at /api/v1, serves the dashboard at /                    │
└──────────────────────────────────────────────────────────────────────────────┘
        │ JSON
        ▼
dashboard (React, bundled locally, no external asset)   ── one Docker image
```

## 3. Data flow

1. **Ingest.** An adapter reads the file, a mapping renames source columns to the canonical
   schema, and thirteen validation checks run. Bad rows are recorded rather than discarded:
   a CSE that cannot submit clean data is itself supervisory evidence, feeding the Data
   Integrity dimension and rule NS-06. Re-submitting an identical file is a no-op; a changed
   file supersedes the previous one and the original stays archived by hash.
2. **Features.** About seventy features per entity-period, each carrying its sample size and
   a support flag. Thin evidence is never silently treated as a signal. Every feature is then
   compared with a peer group of the same sector and size band, falling back to a wider group
   when the sector is too small, using a median and MAD so a single outlier cannot move the
   baseline.
3. **Module A, Execution Gap.** Eleven deterministic rules fire first, each producing a
   bounded score, structured evidence and a plain-language rationale. An unsupervised
   ensemble scores the same feature vector. Raw anomaly scores are not probabilities, so an
   isotonic calibrator maps them using labels, and when there are too few labels the output
   is passed through unchanged and marked uncalibrated in the interface. Rules and model are
   then combined with a geometric noisy-OR that weights the deterministic layer higher.
4. **Module B, Negative Space.** Six detectors, all deterministic: a peer expected-volume
   model, missing expected categories, telemetry coverage gaps, previously active assets that
   have gone silent, missing escalation or investigation records, and unexplained drops in
   activity.
5. **Module C, Supervisory Risk Indicator.** Six weighted dimensions, each 0 to 100, summed
   into one score. Sub-indicators are peer percentiles in the risky direction, so the score is
   scale-free. Weights live in configuration, and the interface shows the arithmetic rather
   than a verdict. Sub-indicators with weak support are dropped and their weight redistributed,
   which lowers the confidence reported alongside the score.
6. **Module D, Prioritisation.** The decision threshold is derived from the cost of being
   wrong: `t* = C_FP / (C_FP + C_FN)`. Missing a real weakness is costed higher than an
   unnecessary review, so the threshold sits low. Findings within a band around the threshold
   are never auto-decided; they are surfaced as "uncertain, recommend review" and sorted
   first. Alert samples are drawn round-robin across rules so one loud rule cannot fill the
   queue.
7. **Explain, audit, report.** Every finding carries a rationale, the peer comparison behind
   it, and the identifiers of the alerts that evidence it. Every run appends an audit row
   containing the code hash, configuration hash, model versions, input manifest and output
   hash, chained to the previous run so a later edit is detectable.

## 4. Machine learning specifics

| Question | Answer |
|---|---|
| Architecture | IsolationForest (300 trees) and Local Outlier Factor over about fifty entity-period features, optionally HDBSCAN for a density baseline; a second IsolationForest at alert level; isotonic regression for calibration; Huber regression for expected alert volume; TF-IDF with nearest-neighbour cosine for note templating. |
| Hardware | CPU only. Reference: 4 vCPU, 8 GB RAM, 20 GB disk. Twenty thousand alerts across six periods complete in about two minutes. No GPU at any point. |
| Offline training | `satsa train --periods ... --promote` reads only the local database. Artifacts are written to `models/<name>/<version>/` with a metadata file recording hyperparameters, library versions and the training data hash. |
| Inference | The pipeline loads active models, never fits during scoring, and refuses to run if a model was trained against a different feature list. |
| Update mechanism | New versions are registered but inactive until promoted. Artifacts move between air-gapped hosts as a hashed tarball. Supervisor feedback drives recalibration, which produces a new calibrator version and bounded threshold suggestions, again inactive until promoted. |
| Explainability | SHAP over the isolation forest where available, otherwise peer z-score attribution, always labelled with the method used. Rule findings render a template with the evaluated values. Every finding names the two features whose return to the peer median would most reduce the score. |
| Auditability | Append-only run log with a hash chain, verifiable through the interface or `satsa verify-audit`. Every ingest, training run, scoring run, configuration change, feedback decision and report is recorded. |

## 5. Interfaces

**Command line.** `satsa init-db`, `seed`, `ingest`, `features`, `train`, `run`, `serve`,
`demo`, `verify-audit`.

**API.** `/api/v1` covering health and periods, entities and the risk heatmap, findings with
evidence and raw records, the review queue, feedback, peer benchmarking, coverage, trends,
ingestion, pipeline jobs, configuration with impact preview, audit, models and reports.

**Dashboard.** Ten screens: portfolio overview, entity detail, finding detail, review queue,
findings list, peer benchmarking, negative space, trends, ingestion and data quality,
configuration, audit log and reports. A supervisor reaches the raw records behind any finding
in three clicks: heatmap cell, finding row, records tab.

## 6. Deployment

One Docker image contains the API, the analytics and the built dashboard. `docker compose up`
is the whole installation. DuckDB is embedded, so there is no database server. The image can
be built with networking disabled once dependency wheels are vendored, and the container
needs no network at runtime.

Storage grows roughly linearly with submissions: the demonstration dataset of about fifteen
thousand alerts across eight entities and six periods occupies under one hundred megabytes
including models and archived source files.

## 7. Validation

The synthetic generator seeds eight entities with known ground truth: two healthy, two with
execution gaps, two with negative space and two noisy controls that must not be flagged. The
test suite asserts that the seeded weaknesses are found, that the healthy and noisy entities
produce no automatic flags, that a forced re-run reproduces the same output hash, that the
audit chain detects tampering, and that the three-click path from portfolio to raw records
resolves. `satsa demo` runs the same workflow end to end and narrates it.
