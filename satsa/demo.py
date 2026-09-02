"""Scripted end-to-end walkthrough of the supervisory workflow.

`satsa demo` rebuilds the synthetic dataset, ingests it in three formats, trains the models,
scores every period, then narrates what a supervisor would see and do: the portfolio ranking,
one entity's scorecard, one finding drilled down to its raw records, a recorded decision, the
negative-space evidence, the effect of changing the cost of a missed weakness, and the audit
chain. Every number printed comes from the database, not from the script.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from satsa.api import queries as q
from satsa.audit.verify import verify_chain
from satsa.config import Settings
from satsa.db.connection import Database
from satsa.db.migrate import apply_schema
from satsa.feedback.store import record_feedback
from satsa.ingest.loader import ingest_path
from satsa.models.train import train_models
from satsa.pipeline.run import run_pipeline
from simulator.entity_profiles import PERIODS
from simulator.generate import generate_dataset

RULE = "-" * 78


@dataclass
class Step:
    title: str
    lines: list[str] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)


@dataclass
class DemoResult:
    steps: list[Step] = field(default_factory=list)
    entity_id: str = ""
    finding_id: str = ""
    period: str = ""

    def add(self, title: str) -> Step:
        step = Step(title)
        self.steps.append(step)
        return step

    def text(self) -> str:
        out = []
        for i, s in enumerate(self.steps, start=1):
            out.append(f"\n{RULE}\n{i}. {s.title}\n{RULE}")
            out.extend(f"   {line}" for line in s.lines)
        return "\n".join(out)


def _pct(v: float | None, digits: int = 0) -> str:
    return "n/a" if v is None else f"{v * 100:.{digits}f}%"


def _num(v: float | None, digits: int = 2) -> str:
    return "n/a" if v is None else f"{v:.{digits}f}"


def run_demo(
    settings: Settings,
    db: Database,
    *,
    rebuild: bool = True,
    periods: list[str] | None = None,
    reviewer: str = "examiner_demo",
    echo: Callable[[str], None] | None = None,
) -> DemoResult:
    periods = periods or PERIODS
    train_on = periods[: max(1, len(periods) // 2)]
    result = DemoResult(period=periods[-1])
    say = echo or (lambda _s: None)

    def emit(step: Step, line: str) -> None:
        step.lines.append(line)
        say(f"   {line}")

    def start(title: str) -> Step:
        step = result.add(title)
        say(f"\n{RULE}\n{len(result.steps)}. {title}\n{RULE}")
        return step

    # ---- 1. Build and ingest -------------------------------------------------------
    step = start("Submissions arrive from the Critical Sector Entities")
    with db.write() as conn:
        apply_schema(conn)
    if rebuild:
        summary = generate_dataset(settings, periods=periods)
        emit(step, f"Generated {summary.total_alerts:,} alerts for {len(summary.alerts_per_entity_period) // len(periods)} entities across {len(periods)} periods.")
        results = ingest_path(settings.resolve(settings.paths.synthetic_dir), settings=settings, db=db)
        formats = sorted({r.file_name.rsplit('.', 1)[-1] for r in results})
        emit(step, f"Ingested {len(results)} submissions in {len(formats)} formats ({', '.join(formats)}); {sum(r.status == 'FATAL' for r in results)} unreadable.")
        worst = max((r for r in results if r.validation), key=lambda r: r.validation.rate("WARN"), default=None)
        if worst:
            v = worst.validation
            emit(step, f"Dirtiest submission: {worst.entity_id} {worst.submission_period} with {_pct(v.rate('WARN'), 1)} of rows carrying a validation warning.")
            emit(step, f"  checks triggered: {', '.join(f'{k}×{n}' for k, n in sorted(v.counts.items()))}")
            emit(step, "  Poor data quality is not discarded; it feeds the Data Integrity dimension and rule NS-06.")
    step.facts["ingested"] = True

    # ---- 2. Train ------------------------------------------------------------------
    step = start("Models are trained offline on historical periods")
    train = train_models(db, settings, train_on, promote=True)
    for name, metrics in train.metrics.items():
        emit(step, f"{name:<18} {train.versions[name]}  {metrics}")
    emit(step, f"Trained on {', '.join(train_on)} only, so scoring later periods is never trained on its own answers.")
    step.facts["model_versions"] = train.versions

    # ---- 3. Score ------------------------------------------------------------------
    step = start("The analytics pipeline scores every submission period")
    for p in periods:
        res = run_pipeline(p, settings=settings, db=db, triggered_by="demo", trigger_source="cli")
        secs = sum(s.get("seconds", 0) or 0 for s in res.stage_log)
        emit(step, f"{p}: {res.status} in {secs:.1f}s · {res.counts.get('findings', 0)} findings, {res.counts.get('alert_sample_flags', 0)} alert flags")
        if res.status == "FAILED":
            raise RuntimeError(f"pipeline failed for {p}: {res.error}")
    again = run_pipeline(periods[-1], settings=settings, db=db, triggered_by="demo", trigger_source="cli")
    emit(step, f"Re-running {periods[-1]} with unchanged inputs: {again.status} — identical work is never repeated.")
    step.facts["idempotent"] = again.status

    period = periods[-1]
    with db.read() as conn:
        # ---- 4. Portfolio ----------------------------------------------------------
        step = start(f"Portfolio view for {period}: who needs supervisory attention")
        s = q.summary(conn, period)
        emit(step, f"{s['n_entities']} entities scored · {s['n_high_risk']} high or critical · {s['n_open_findings']} open findings · {s['n_uncertain']} uncertain · {s['n_dq_failures']} data-quality failures")
        hm = q.heatmap(conn, period)
        emit(step, f"{'rank':<5}{'entity':<8}{'sri':>6}  {'band':<9}{'exec gap':>9}{'neg space':>10}  findings")
        for r in hm["rows"]:
            d = r["dims"]
            emit(step, f"{r['priority_rank']:<5}{r['entity_id']:<8}{r['sri']:>6.1f}  {r['band']:<9}{d.get('execution_gap') or 0:>9.1f}{d.get('negative_space') or 0:>10.1f}  {r['n_findings']}")
        top = hm["rows"][0]
        emit(step, "Rank is supervisory priority: the risk score weighted by confidence and by how much the entity matters.")
        result.entity_id = max(hm["rows"], key=lambda r: r["sri"] or 0)["entity_id"]
        step.facts["top_entity"] = top["entity_id"]
        step.facts["highest_sri_entity"] = result.entity_id

        # ---- 5. Entity scorecard ---------------------------------------------------
        eid = result.entity_id
        step = start(f"Entity {eid}: the risk score, shown as arithmetic rather than a verdict")
        card = q.sri_scorecard(conn, settings, eid, period)
        emit(step, f"Supervisory Risk Indicator {card['sri']:.1f} of 100 ({card['band']}), confidence {card['confidence']:.2f}")
        emit(step, f"{'dimension':<24}{'score':>7}{'weight':>8}{'contribution':>14}")
        for dim in card["dimensions"]:
            emit(step, f"{dim['label']:<24}{dim['score']:>7.1f}{dim['weight']:>8.2f}{dim['contribution']:>14.1f}")
        emit(step, f"{'total':<24}{'':>7}{'':>8}{card['sri']:>14.1f}   (weights {card['weights_hash'][:8]}, config {card['config_hash'][:8]})")
        step.facts["sri"] = card["sri"]

        # ---- 6. Finding ------------------------------------------------------------
        step = start("One finding, from claim to evidence")
        findings = q.list_findings(conn, period=period, entity_id=eid, limit=50)["items"]
        rule_findings = [f for f in findings if f["rule_id"]]
        chosen = max(rule_findings or findings, key=lambda f: f["p_final"])
        result.finding_id = chosen["finding_id"]
        detail = q.finding_detail(conn, settings, chosen["finding_id"])
        emit(step, f"{detail['rule_id'] or 'combined'} · {detail['title']} · severity {detail['severity']}")
        emit(step, f"Rationale: {detail['rationale']}")
        emit(step, f"Decision {detail['decision']} because p = {_num(detail['p_final'])} against t* = {_num(detail['t_star'])} with an uncertainty band of {_num(detail['band_low'])} to {_num(detail['band_high'])}.")
        emit(step, f"t* comes from the cost of being wrong: C_FP / (C_FP + C_FN). Missing a real weakness is costed higher, so the threshold sits low.")
        if detail["evidence_features"]:
            emit(step, "Evidence against the peer group:")
            for f in detail["evidence_features"][:4]:
                emit(step, f"  {f['label']:<38} entity {_num(f['value'], 3):>8}   peer median {_num(f['peer_median'], 3):>8}   z {_num(f['z'], 1):>6}")
        records = q.finding_records(conn, chosen["finding_id"], 3, 0, "ttc")
        emit(step, f"Underlying records: {records['total']} alerts. First three, three clicks from the portfolio:")
        for a in records["items"]:
            emit(step, f"  {a['alert_id']}  {a['severity']:<8} {str(a['category']):<20} closed in {_num(a['time_to_close_min'], 0)} min as {a['closure_reason']}")
            if a["investigation_notes"]:
                emit(step, f"     note: \"{a['investigation_notes'][:90]}\"")
        step.facts["finding"] = {"rule_id": detail["rule_id"], "p_final": detail["p_final"], "decision": detail["decision"], "n_records": records["total"]}

        # ---- 7. Review queue -------------------------------------------------------
        step = start("The alert samples chosen for manual review")
        queue = q.review_queue(conn, period=period, entity_id=eid, limit=6)
        emit(step, f"{queue['total']} samples queued for {eid}; sampling rotates across rules so one loud rule cannot fill the queue.")
        for it in queue["items"]:
            emit(step, f"  #{it['queue_rank']} {it['alert_id']}  {', '.join(it['rule_ids']) or 'model'}  p={_num(it['p_alert'])}  {it['decision']}")
        step.facts["queue_total"] = queue["total"]

    # ---- 8. Feedback ---------------------------------------------------------------
    step = start("The examiner decides, and the decision is recorded")
    with db.write() as conn:
        fb = record_feedback(conn, settings, target_type="finding", target_id=result.finding_id, decision="ACCEPT",
                             reviewer_id=reviewer, note="Confirmed with the entity's SOC lead during the review call.", source="cli")
    emit(step, f"Recorded {fb['decision']} by {fb['reviewer_id']} on {fb['target_id'][:16]}.")
    emit(step, "The decision is appended, never overwritten, and becomes a label the calibrator learns from.")
    with db.read() as conn:
        from satsa.feedback.store import feedback_stats

        stats = feedback_stats(conn)
        emit(step, f"{stats['n_feedback']} decision(s) recorded across {stats['n_targets']} item(s); {len(stats['rules'])} rule(s) now have supervisor labels.")
    step.facts["feedback_id"] = fb["feedback_id"]

    # ---- 9. Negative space ---------------------------------------------------------
    with db.read() as conn:
        step = start("Negative space: the evidence that should be there and is not")
        cov = q.coverage_matrix(conn, settings, period, "category")
        absent_rows = [(r, [cov["columns"][i] for i, c in enumerate(r["cells"]) if c["status"] == "absent"]) for r in cov["rows"]]
        absent_rows = [(r, cols) for r, cols in absent_rows if cols]
        for r, cols in absent_rows:
            emit(step, f"{r['entity_id']} is missing {', '.join(cols)}")
        if absent_rows:
            row, cols = absent_rows[0]
            cell = q.coverage_cell(conn, settings, row["entity_id"], cols[0], period)
            emit(step, f"Why '{cols[0]}' is expected for {row['entity_id']}: {cell['expected_reason']}.")
            emit(step, f"Observed {cell['observed']:.0f} alerts; {_pct(cell['peer_share_reporting'])} of peers report this category.")
        else:
            emit(step, "No expected category is entirely absent this period.")
        step.facts["absent_entities"] = [r["entity_id"] for r, _ in absent_rows]

        # ---- 10. Cost sensitivity --------------------------------------------------
        step = start("Changing the cost of a missed weakness changes what needs a human")
        from satsa.api.config_store import what_if
        from satsa.api.schemas import WhatIfRequest

        base_t = settings.t_star("execution_gap")
        wi = what_if(conn, settings, WhatIfRequest(period=period, costs={"execution_gap": {"C_FP": 1.0, "C_FN": 9.0}}))
        emit(step, f"Now: C_FN is {settings.cost('execution_gap')[1]:.0f}× C_FP, so t* = {base_t:.3f} and {wi['n_uncertain_before']} findings sit in the uncertainty band.")
        emit(step, f"If a missed weakness cost 9× a needless review, t* would fall to {wi['thresholds']['execution_gap']['t_star']:.3f} and {wi['n_uncertain_after']} findings would need a human decision.")
        emit(step, "Nothing is hard-coded: the supervisor sets the cost, and the threshold follows from it.")
        step.facts["what_if"] = {"before": wi["n_uncertain_before"], "after": wi["n_uncertain_after"]}

        # ---- 11. Reports -----------------------------------------------------------
        step = start("Reports a supervisor can hand over")
        from satsa.reports.pdf import entity_report, period_report

        pdf_entity = entity_report(conn, settings, eid, period)
        pdf_period = period_report(conn, settings, period)
        emit(step, f"Entity report: {pdf_entity.name} ({pdf_entity.stat().st_size // 1024} KB)")
        emit(step, f"Portfolio report: {pdf_period.name} ({pdf_period.stat().st_size // 1024} KB)")
        emit(step, "Both carry the code, configuration and model hashes that produced them.")
        step.facts["reports"] = [str(pdf_entity), str(pdf_period)]

        # ---- 12. Audit -------------------------------------------------------------
        step = start("Every step above is in the audit trail")
        runs = q.runs(conn, limit=8)
        emit(step, f"{'when':<20}{'type':<13}{'period':<10}{'status':<20}config")
        for r in runs:
            emit(step, f"{str(r['started_at'])[:19]:<20}{r['run_type']:<13}{str(r['submission_period'] or '-'):<10}{r['status']:<20}{str(r['config_hash'])[:8]}")
        v = verify_chain(conn)
        emit(step, f"Hash chain verification: {'intact' if v.ok else 'BROKEN at ' + str(v.first_broken_run_id)} across {v.n_runs} finalised runs.")
        emit(step, "Each run hashes the previous one, so a later edit to any row breaks the chain and is detected.")
        step.facts["audit_ok"] = v.ok
        step.facts["n_runs"] = v.n_runs

    return result


def demo_settings(settings: Settings, workdir: Path) -> Settings:
    """Settings pointed at a scratch directory, with the repo config copied in."""
    from satsa.config import load_settings

    cfg = workdir / "config"
    if not cfg.exists():
        shutil.copytree(settings.config_dir, cfg)
    return load_settings(cfg, {"paths": {
        "db_path": str(workdir / "satsa.duckdb"), "synthetic_dir": str(workdir / "synthetic"), "ground_truth_dir": str(workdir / "ground_truth"),
        "processed_dir": str(workdir / "processed"), "models_dir": str(workdir / "models"), "reports_dir": str(workdir / "reports"),
        "logs_dir": str(workdir / "logs"), "incoming_dir": str(workdir / "incoming"),
    }})
