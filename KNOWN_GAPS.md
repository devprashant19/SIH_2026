# Known gaps

What is not done, and what is claimed more strongly than the evidence supports. Ordered by
how much it matters to someone deciding whether to trust the tool.

A gap listed here is worth more than a gap discovered by a judge.

---

## 1. There is no held-out split, so the accuracy claims are circular

**What is wrong.** Rule thresholds in `config/rules.yaml` were tuned while observing which
entities flagged on the demo profile. The results reported in the README come from that same
profile. Numbers produced this way overstate themselves, because the thresholds have already
seen the answers.

**Why it matters.** This is the first question an evaluator asks, and the honest answer today
is "we cannot separate what the tool learned from what it was told". A precision or recall
figure computed on this basis would be misleading, which is why the README quotes none.

**The fix.** The approved implementation plan specified it: tune on part of the ground truth,
report only on the rest. Concretely, split the eight entities or the six periods into a
tuning set and a reporting set, re-tune thresholds against the tuning set alone, and report
every figure from the reporting set. A day of work.

**Interim honesty.** The README states this in the results section rather than presenting
the seeded-weakness detection as a validated result.

---

## 2. Ground truth is generated and never graded against

**What is wrong.** `simulator/ground_truth.py` writes three label files. Two are used:
`entity_period_labels.csv` trains the execution-gap calibrator, and `alert_labels.csv`
trains the alert calibrator. The third, `expected_findings.csv`, names which rule should fire
for which entity-period and is read by nothing except a test asserting the file exists.

**Why it matters.** Per-rule precision and recall are computable today. Without them, a
statement like "the rules work" rests on eyeballing which entities appear in a table.

**The fix.** Score each rule against `expected_findings.csv` and report per-rule precision
and recall, naming the weakest rule rather than averaging it away.

---

## 3. There is no baseline

**What is wrong.** Nothing measures what a naive approach achieves on the same data. A
plausible one would be flagging any entity whose escalation ratio falls below the peer median.

**Why it matters.** Without a baseline the lift is unquantified. A tool that finds the seeded
weaknesses is unimpressive if a one-line rule finds them too.

**The fix.** Implement one or two naive baselines and report them beside the full pipeline.

---

## 4. Five of nineteen rules never fire

**What is wrong.** On the demo profile, EG-04 (uniform closure times), EG-08 (closure-reason
collapse), EG-09 (mass closure), EG-11 (escalated without an incident record) and NS-08
(critical assets under-monitored) produce no findings in any period.

**Why it matters.** Either the simulator does not generate those patterns, or the thresholds
are too tight to catch the ones it does. Those are very different problems and it has not
been established which applies. Untested code paths in a supervisory tool are a liability.

**The fix.** For each of the five, determine whether the pattern exists in the data. Where it
does not, seed it. Where it does, examine why the threshold misses it.

---

## 5. The validation harness in the plan was not built

**What is wrong.** `validation/` is an empty directory. The approved plan specified a
backtest across five seeds with per-module and per-rule metrics, a calibration reliability
check with an expected-calibration-error target, and a manual-review parity protocol
comparing the tool against blind human review.

**Why it matters.** The problem statement asks explicitly how the solution will be validated
against findings derived from expert manual review. The architecture document describes the
methodology; the code implementing it does not exist. The traceability table marks this row
**Not built** rather than claiming it.

**The fix.** Build the three modules. The backtest depends on gap 1 being fixed first, since
it needs the split to report against.

---

## 6. Scale is unverified beyond the demo profile

**What is wrong.** Measured behaviour stops at 14,704 alerts across eight entities: 72
seconds, 0.33 GB. An earlier draft of the model card claimed the system would handle roughly
two million alerts on 16 GB. That figure came from reasoning about DuckDB, not from a
measurement, and has been removed.

**Why it matters.** "Scalability and Performance" is a stated evaluation criterion, and an
unverified number is worse than an absent one.

**The fix.** Generate a larger profile and measure it, reporting where it degrades. Expected
pressure points are the note-similarity computation, which is quadratic within an
entity-period before the nearest-neighbour cap, and holding all periods in memory during
feature building.

---

## 7. No frontend unit tests, and no accessibility audit

**What is wrong.** The dashboard has no Vitest tests despite Vitest and Testing Library being
configured. The accessibility work was designed in, colour is never the only cue, every chart
carries a hidden data table, focus rings are preserved, but it has never been audited with a
tool.

**What has since been done.** All eleven routes are loaded in a real browser and checked for
console errors, failed requests and rendered content, and the three-click drill-down is
exercised end to end. That pass found two defects, both fixed: a rule finding described its
score as "uncalibrated" when no model was involved, and two heatmap columns shared the
heading "Trend". `dashboard/scripts/screenshots.py` regenerates every README image from the
running application.

**Why the rest still matters.** A browser smoke pass is not a unit test suite; it catches
crashes, not wrong values. An axe pass would replace assertion with measurement.

**The fix.** Vitest render tests per route against mocked responses, and axe on each route.

---

## 8. The ERP-style integration boundary does not exist

**What is wrong.** SAT-SA reads submissions and writes findings. It does not write back to
any system a supervisor or entity uses.

**Why it matters.** This is a deliberate scope decision rather than an oversight: the problem
statement asks for a supervisory analytics capability, not an operational one, and writing
into a CSE's systems would cross the scope boundary the statement draws. It is listed here so
the absence is visibly a choice rather than a gap.

---

## Not gaps, but worth stating

- **HDBSCAN is not installed** on the demo profile, so the ensemble runs two detectors rather
  than three. This is reported by the model registry and `/api/v1/health`, and every quoted
  number is from the two-detector configuration.
- **The execution-gap calibrator has 24 labels.** That is few. It reports a low expected
  calibration error, which on 24 points should be read as "not obviously miscalibrated"
  rather than "well calibrated".
- **Rules fire on exactly one entity each.** Good specificity, but it also means the demo
  profile exercises each rule against a single behaviour pattern.
