# SAT-SA — Supervisory Analytics Tool for SOC Assessment

Team - Revenant

Smart India Hackathon 2026 · Problem Statement 26157 · NTRO / NCIIPC

SAT-SA helps NCIIPC examiners analyse batch submissions of SOC alert and case-management
data from many Critical Sector Entities (CSEs). It detects **Execution Gaps** (documented
capability not matched by operational evidence) and **Negative Space** (expected evidence
that is absent), benchmarks entities against peers, produces a transparent Supervisory Risk
Indicator (SRI), and prioritises entities, controls and alert samples for manual review —
with every finding traceable to the underlying records.

It is a **supervisory analytics** capability: batch-only, fully offline, no SIEM, no
real-time monitoring, no cloud or hosted AI.

## See it work in one command

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
.\.venv\Scripts\satsa demo
```

`satsa demo` generates a synthetic multi-entity dataset with known weaknesses, ingests it in
three formats, trains the models, scores every period, then walks through what a supervisor
would see: the portfolio ranking, one entity's scorecard as arithmetic, one finding drilled
down to the alerts that evidence it, a recorded decision, the missing evidence, the effect of
changing the cost of a missed weakness, and the audit chain. Every number it prints comes from
the database.

Then start the interface and follow the same path in the browser:

```powershell
.\.venv\Scripts\satsa serve      # http://localhost:8000
```

## Docker

```bash
docker compose up --build
```

To prove the air-gap, uncomment `network_mode: none` in `docker-compose.yml`, or build with
vendored wheels: `make wheels && docker build --network none .`

## Command line

| Command | Purpose |
|---|---|
| `satsa info` | Version, code hash, configuration hash and the derived decision thresholds |
| `satsa init-db` | Create the DuckDB store |
| `satsa seed` | Generate the synthetic dataset with seeded ground truth |
| `satsa ingest <path>` | Ingest a submission file or a directory of them |
| `satsa features <period>` | Compute entity-period features (diagnostic) |
| `satsa train --periods a,b,c --promote` | Train and activate models |
| `satsa run <period>` | Score one submission period |
| `satsa serve` | Start the API and dashboard |
| `satsa demo` | Narrated end-to-end walkthrough |
| `satsa verify-audit` | Recompute the audit hash chain |

## How it decides

- **Rules first, model second.** Nineteen deterministic rules produce findings with a
  plain-language rationale and named evidence. An unsupervised ensemble adds a second opinion,
  and its score is calibrated before anyone sees it.
- **Everything is peer-relative.** Metrics are compared inside a peer group of the same sector
  and size band, using a median and MAD so one outlier cannot move the baseline.
- **The threshold follows from cost.** `t* = C_FP / (C_FP + C_FN)`. Missing a real weakness is
  costed higher than an unnecessary review. Findings near the threshold are never auto-decided.
- **Thin evidence is not a signal.** Every feature carries its sample size; weak support lowers
  the confidence shown beside the score instead of being hidden.
- **Nothing is unexplained.** Every finding shows its rationale, its peer comparison and the
  records behind it, three clicks from the portfolio.

## Repository map

| Path | Purpose |
|---|---|
| `satsa/` | Ingestion, features, analytics, explainability, audit, feedback, models, reports, API |
| `config/` | All tunable behaviour: SRI weights, costs, rule thresholds, peer groups, expected categories |
| `simulator/` | Synthetic multi-entity generator with seeded ground truth |
| `dashboard/` | React dashboard, bundled locally and served by the API |
| `docs/` | Architecture and model card |
| `tests/` | pytest suite; an autouse fixture blocks all outbound network access |

## Development

```powershell
.\.venv\Scripts\pytest                 # backend suite
cd dashboard; npm install; npm run build; node scripts/check-offline.mjs
```

The offline check fails the build if the compiled bundle references any external host.

See `docs/architecture.md` for the system design and `docs/model_card.md` for the analytics
methodology, hardware requirements, model update mechanism and audit controls.
