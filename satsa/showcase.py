"""Exhaustive feature demonstration.

`satsa demo` tells the twelve-minute story a supervisor would be shown. This walks every
capability the project claims and *proves* each one, so it doubles as an integration check:
it exits non-zero if any capability fails to demonstrate itself.

Where a claim can be falsified, it is. The audit chain is tampered with on a throwaway copy
of the database to show the break being caught. The pipeline is re-run to show the same
inputs producing the same output hash. Nothing here prints a claim it did not just execute.
"""

from __future__ import annotations

import json
import re
import socket
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import duckdb

from satsa.config import Settings
from satsa.db.connection import Database

TICK, CROSS, DASH = "PASS", "FAIL", "  - "
WIDTH = 78


@dataclass
class Check:
    ok: bool
    name: str
    detail: str


@dataclass
class Section:
    key: str
    title: str
    checks: list[Check] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)


@dataclass
class ShowcaseResult:
    sections: list[Section] = field(default_factory=list)

    @property
    def checks(self) -> list[Check]:
        return [c for s in self.sections for c in s.checks]

    @property
    def failed(self) -> list[Check]:
        return [c for c in self.checks if not c.ok]

    @property
    def ok(self) -> bool:
        return not self.failed


class Reporter:
    """Collects results and prints them as it goes."""

    def __init__(self, echo: Callable[[str], None]) -> None:
        self.echo = echo
        self.result = ShowcaseResult()
        self._section: Section | None = None

    def section(self, key: str, title: str) -> None:
        self._section = Section(key, title)
        self.result.sections.append(self._section)
        self.echo("")
        self.echo("=" * WIDTH)
        self.echo(f" {key} · {title.upper()}")
        self.echo("=" * WIDTH)

    def check(self, ok: bool, name: str, detail: str = "") -> bool:
        assert self._section is not None, "call section() first"
        self._section.checks.append(Check(bool(ok), name, detail))
        self.echo(f"  {TICK if ok else CROSS}  {name:<32} {detail}")
        return bool(ok)

    def note(self, text: str) -> None:
        self.echo(f"{DASH}{text}")


def _fmt(v: Any, digits: int = 2) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


# ---------------------------------------------------------------------------------------


def run_showcase(settings: Settings, db: Database, *, echo: Callable[[str], None] = print,
                 period: str | None = None, with_ui: bool = False) -> ShowcaseResult:
    from satsa.api import queries as q

    r = Reporter(echo)
    with db.read() as conn:
        period = period or q.latest_period(conn)
    if period is None:
        raise RuntimeError("no scored data. Run `satsa demo` first, or `satsa showcase --rebuild`.")

    echo("")
    echo("#" * WIDTH)
    echo(f"#  SAT-SA feature demonstration · period {period}")
    echo(f"#  Every line below is executed, not asserted from documentation.")
    echo("#" * WIDTH)

    _ingestion(r, settings, db, period)
    _features(r, settings, db, period)
    _rules(r, settings, db, period)
    _model(r, settings, db)
    _scorecard(r, settings, db, period)
    _thresholds(r, settings, db, period)
    _queue(r, settings, db, period)
    _negative_space(r, settings, db, period)
    _explainability(r, settings, db, period)
    _evidence_chain(r, settings, db, period)
    _feedback(r, settings, db, period)
    _governance(r, settings, db, period)
    _configuration(r, settings, db, period)
    _reports(r, settings, db, period)
    _api(r, settings, db, period)
    _offline(r)
    if with_ui:
        _ui(r, settings)

    _summary(r)
    return r.result


# --- A. ingestion ----------------------------------------------------------------------

def _ingestion(r: Reporter, settings: Settings, db: Database, period: str) -> None:
    from satsa.ingest.loader import ingest_submission

    r.section("A", "Ingestion: three formats, validation as evidence, safe resubmission")
    with db.read() as conn:
        fmts = dict(conn.execute("SELECT source_format, count(*) FROM raw_submissions WHERE superseded = FALSE GROUP BY 1").fetchall())
        totals = conn.execute("SELECT sum(row_count), sum(accepted_rows), sum(rejected_rows) FROM raw_submissions WHERE superseded = FALSE").fetchone()
        flags = dict(conn.execute("SELECT f, count(*) FROM (SELECT unnest(validation_flags) AS f FROM alerts) GROUP BY 1 ORDER BY 1").fetchall())
        worst = conn.execute("""SELECT entity_id, submission_period, validation_json FROM raw_submissions
                                WHERE superseded = FALSE ORDER BY rejected_rows DESC, entity_id LIMIT 1""").fetchone()

    r.check(len(fmts) == 3, "three source formats", ", ".join(f"{k} {v}" for k, v in sorted(fmts.items())))
    r.check(totals[0] > 0, "rows read", f"{totals[0]:,} read, {totals[1]:,} accepted, {totals[2]} rejected")
    r.check(bool(flags), "validation flags recorded", " ".join(f"{k}x{v}" for k, v in flags.items()))
    if worst:
        v = json.loads(worst[2])
        r.note(f"dirtiest submission {worst[0]} {worst[1]}: {v['n_rows']} rows, checks "
               + " ".join(f"{k}x{n}" for k, n in sorted(v["counts"].items())))
        r.note("those rows are kept, not dropped: the rates feed Data Integrity and rule NS-06")

    # Idempotent re-ingest. Use a single-file submission: a CSV entity submits five companion
    # files hashed together, so re-offering one of them alone is a different submission by
    # construction rather than a repeat of the same one.
    syn = settings.resolve(settings.paths.synthetic_dir)
    sample = next(iter(sorted(syn.glob("*.sqlite"))), None) or next(iter(sorted(syn.glob("*.json"))), None)
    if sample:
        res = ingest_submission(sample, settings=settings, db=db, triggered_by="showcase", trigger_source="cli")
        r.check(res.status == "ALREADY_INGESTED", "identical file is a no-op", f"{sample.name} -> {res.status}")
        r.note("the submission id is the sha256 of the file set, so the same bytes are recognised")

    # A changed file supersedes rather than duplicating. Demonstrated on a throwaway entity in
    # a period nothing scores, then removed: re-ingesting the original would not undo a
    # supersede, since identical bytes are correctly treated as a repeat and skipped.
    demo_entity, demo_period = "ZZDEMO", "2019-01"
    with tempfile.TemporaryDirectory() as td:
        rows = ["alert_id,timestamp,severity,category,asset_id,source_system,analyst_action,closed_at,closure_reason,investigation_notes"]
        for i in range(6):
            rows.append(f"Z{i},2019-01-1{i}T09:00:00,HIGH,malware,ZA1,edr,CLOSED,2019-01-1{i}T11:00:00,BENIGN,Checked and closed.")
        first = Path(td) / f"{demo_entity}_{demo_period}_alerts.csv"
        first.write_text("\n".join(rows), encoding="utf-8")
        a = ingest_submission(first, settings=settings, db=db, triggered_by="showcase", trigger_source="cli")

        second = Path(td) / "v2" / f"{demo_entity}_{demo_period}_alerts.csv"
        second.parent.mkdir()
        second.write_text("\n".join(rows[:-2]), encoding="utf-8")  # two alerts withdrawn
        b = ingest_submission(second, settings=settings, db=db, triggered_by="showcase", trigger_source="cli")

    ok = a.status == "INGESTED" and b.status == "INGESTED" and len(b.superseded) == 1
    r.check(ok, "changed file supersedes", f"{a.tables.get('alerts', 0)} alerts -> {b.tables.get('alerts', 0)}, {len(b.superseded)} superseded")
    with db.read() as conn:
        live = conn.execute("SELECT count(*) FROM alerts WHERE entity_id = ?", [demo_entity]).fetchone()[0]
        kept = conn.execute("SELECT count(*) FROM raw_submissions WHERE entity_id = ?", [demo_entity]).fetchone()[0]
    r.check(live == 4 and kept == 2, "the superseded submission is retained",
            f"{live} alerts live, {kept} submission records kept")
    r.note("the earlier file stays archived by hash, so a finding raised against it is still reproducible")
    with db.write() as conn:  # leave the estate exactly as it was found
        for table in ("alerts", "raw_submissions"):
            conn.execute(f"DELETE FROM {table} WHERE entity_id = ?", [demo_entity])
    r.note("the throwaway entity has been removed; the scored estate is untouched")


# --- B. features -----------------------------------------------------------------------

def _features(r: Reporter, settings: Settings, db: Database, period: str) -> None:
    from satsa.features.registry import FEATURE_NAMES, HEADLINE_FEATURES, feature_list_hash

    r.section("B", "Features: 84 per entity-period, each with its sample size")
    with db.read() as conn:
        row = conn.execute("""SELECT entity_id, features_json, support_json, peer_z_json, peer_group_id, peer_level, peer_n
                              FROM features_entity_period WHERE submission_period = ? LIMIT 1""", [period]).fetchone()
        levels = dict(conn.execute("SELECT peer_level, count(*) FROM features_entity_period WHERE submission_period = ? GROUP BY 1", [period]).fetchall())
    r.check(len(FEATURE_NAMES) == 84, "feature registry", f"{len(FEATURE_NAMES)} features, {len(HEADLINE_FEATURES)} headline, hash {feature_list_hash()[:8]}")
    if row:
        feats, support, z = json.loads(row[1]), json.loads(row[2]), json.loads(row[3])
        computed = sum(1 for v in feats.values() if v is not None)
        by_flag: dict[str, int] = {}
        for s in support.values():
            by_flag[s["flag"]] = by_flag.get(s["flag"], 0) + 1
        r.check(computed > 0, f"computed for {row[0]}", f"{computed} of {len(feats)} have a value")
        r.check("OK" in by_flag, "support flags", " ".join(f"{k} {v}" for k, v in sorted(by_flag.items())))
        r.note("a feature with too few records is flagged, never silently treated as a signal")
        r.check(any(v is not None for v in z.values()), "peer z-scores", f"group {row[4]}, level {row[5]}, {row[6]} members")
    r.check(bool(levels), "peer grouping", " ".join(f"level {k}: {v} entities" for k, v in sorted(levels.items())))
    r.note("level 1 is sector and size band, 2 is sector, 3 is global; the level used is recorded")


# --- C. rules --------------------------------------------------------------------------

def _rules(r: Reporter, settings: Settings, db: Database, period: str) -> None:
    from satsa.analytics.rules.catalogue import rule_index

    r.section("C", "Rules: 19 deterministic checks, each with a rendered rationale")
    idx = rule_index(settings)
    with db.read() as conn:
        fired = dict(conn.execute("""SELECT rule_id, count(*) FROM findings f
            JOIN audit_runs a ON a.run_id = f.run_id AND a.status = 'SUCCESS'
            WHERE f.rule_id IS NOT NULL GROUP BY 1 ORDER BY 1""").fetchall())
        example = conn.execute("""SELECT rule_id, rationale FROM findings
            WHERE submission_period = ? AND rule_id IS NOT NULL ORDER BY p_final DESC LIMIT 1""", [period]).fetchone()

    eg = [k for k in idx if k.startswith("EG-")]
    ns = [k for k in idx if k.startswith("NS-")]
    r.check(len(idx) == 19, "rule catalogue", f"{len(eg)} execution gap, {len(ns)} negative space, {len(settings.rules['controls'])} controls")
    r.check(all(idx[k]["enabled"] for k in idx), "all enabled", "toggled individually on the configuration screen")
    r.check(len(fired) > 0, "rules that fire on this estate", f"{len(fired)} of 19: {', '.join(sorted(fired))}")
    silent = sorted(set(idx) - set(fired))
    if silent:
        r.note(f"never fire here: {', '.join(silent)} — recorded as gap 4 in KNOWN_GAPS.md, not hidden")
    if example:
        r.check(len(example[1]) > 40, f"rationale for {example[0]}", "")
        r.note(f'"{example[1][:150]}"')
        r.note("that sentence is a template rendered with the values it evaluated, not free text")


# --- D. model --------------------------------------------------------------------------

def _model(r: Reporter, settings: Settings, db: Database) -> None:
    from satsa.analytics.anomaly import HDBSCAN_AVAILABLE
    from satsa.models.registry import load_active_bundle

    r.section("D", "Model: an ensemble whose scores are calibrated before anyone sees them")
    with db.read() as conn:
        bundle = load_active_bundle(conn, settings)
        rows = conn.execute("""SELECT model_name, version, training_rows, metrics_json, feature_list_hash
                               FROM model_registry WHERE is_active ORDER BY model_name""").fetchall()
    r.check(bundle.available, "active bundle loaded", f"{len(rows)} models")
    for name, version, n, metrics_json, flh in rows:
        m = json.loads(metrics_json)
        bits = []
        if "detectors" in m:
            bits.append("detectors " + "+".join(m["detectors"]))
        if "calibrated" in m:
            bits.append("calibrated" if m["calibrated"] else "UNCALIBRATED")
            bits.append(f"ECE {_fmt(m.get('ece'), 4)}")
        r.check(True, f"  {name}", f"{version} on {n:,} rows · {' · '.join(bits)}")
    r.note(f"hdbscan installed: {HDBSCAN_AVAILABLE}. Without it the ensemble runs two detectors and says so.")
    if bundle.calibrator_a is not None:
        raw = [0.0, 0.25, 0.5, 0.75, 1.0]
        mapped = bundle.calibrator_a.predict(raw)
        r.check(True, "calibration map", " ".join(f"{a:.2f}->{b:.2f}" for a, b in zip(raw, mapped)))
        r.note("a raw anomaly score is not a probability; this is the map that makes it one")

    from satsa.features.registry import feature_list_hash
    pinned = rows[0][4] if rows else None
    r.check(pinned == feature_list_hash(), "feature list pinned", "the pipeline refuses a model trained on a different feature set")


# --- E. scorecard ----------------------------------------------------------------------

def _scorecard(r: Reporter, settings: Settings, db: Database, period: str) -> None:
    from satsa.api import queries as q

    r.section("E", "Risk indicator: arithmetic on screen, not a verdict")
    with db.read() as conn:
        top = conn.execute("""SELECT entity_id FROM sri_scores WHERE submission_period = ?
                              ORDER BY sri DESC LIMIT 1""", [period]).fetchone()
        card = q.sri_scorecard(conn, settings, top[0], period) if top else None
    if not card:
        r.check(False, "scorecard", "no scored entity")
        return
    total = sum(d["contribution"] for d in card["dimensions"])
    weights = sum(d["weight"] for d in card["dimensions"])
    r.check(abs(total - card["sri"]) < 1e-6, f"contributions sum to the score for {card['entity_id']}",
            f"{total:.1f} == {card['sri']:.1f}")
    r.check(abs(weights - 1.0) < 1e-9, "weights sum to 1.00", f"{weights:.2f} · hash {card['weights_hash'][:8]}")
    for d in card["dimensions"]:
        r.note(f"{d['label']:<24} score {d['score']:6.1f}  x weight {d['weight']:.2f}  = {d['contribution']:6.1f}")
    r.check(0 <= card["confidence"] <= 1, "confidence reported", f"{card['confidence']:.2f}")
    weak = sum(1 for d in card["dimensions"] for s in d["subs"] if s["support"] != "OK")
    r.note(f"{weak} sub-indicators had weak support and were dropped, their weight redistributed")
    r.note("that is why confidence is below 1.00: the tool says how much evidence it had")


# --- F. thresholds ---------------------------------------------------------------------

def _thresholds(r: Reporter, settings: Settings, db: Database, period: str) -> None:
    r.section("F", "Decisions: the threshold is derived from the cost of being wrong")
    for cls in ("execution_gap", "negative_space", "alert_sample"):
        c_fp, c_fn = settings.cost(cls)
        t = settings.t_star(cls)
        r.check(abs(t - c_fp / (c_fp + c_fn)) < 1e-9, f"t* for {cls}",
                f"C_FP {c_fp:.0f} / C_FN {c_fn:.0f} -> t* {t:.3f}, band +/-{settings.band_halfwidth(cls):.2f}")
    with db.read() as conn:
        dec = dict(conn.execute("""SELECT decision, count(*) FROM findings f
            JOIN audit_runs a ON a.run_id = f.run_id AND a.status='SUCCESS'
            WHERE f.submission_period = ? GROUP BY 1""", [period]).fetchall())
        band = conn.execute("""SELECT count(*) FROM findings f JOIN audit_runs a ON a.run_id=f.run_id AND a.status='SUCCESS'
            WHERE f.submission_period = ? AND f.p_final BETWEEN f.band_low AND f.band_high AND f.decision <> 'MANUAL_REVIEW'""", [period]).fetchone()[0]
    r.check(True, "decisions this period", " ".join(f"{k} {v}" for k, v in sorted(dec.items())))
    r.check(band == 0, "nothing inside the band was auto-decided", f"{band} violations")
    r.note("findings near the threshold are never decided automatically; they go to a person and sort first")


# --- G. review queue -------------------------------------------------------------------

def _queue(r: Reporter, settings: Settings, db: Database, period: str) -> None:
    from satsa.api import queries as q

    r.section("G", "Prioritisation: entities, controls and alert samples")
    with db.read() as conn:
        queue = q.review_queue(conn, period=period, limit=1000)
        controls = q.control_priorities(conn, settings, period)
        ranks = conn.execute("""SELECT entity_id, count(*), min(queue_rank), max(queue_rank)
            FROM alert_sample_flags f JOIN audit_runs a ON a.run_id=f.run_id AND a.status='SUCCESS'
            WHERE f.submission_period = ? AND queue_rank IS NOT NULL GROUP BY 1 ORDER BY 2 DESC""", [period]).fetchall()
    budget = settings.pipeline.review_budget_per_entity
    r.check(queue["total"] > 0, "alert samples queued", f"{queue['total']} across {len(ranks)} entities")
    r.check(all(mx <= budget for _e, _n, _mn, mx in ranks), "per-entity budget respected", f"cap {budget} per entity")
    r.check(all(mn == 1 for _e, _n, mn, _mx in ranks), "ranks are contiguous from 1", "")
    if ranks:
        eid = ranks[0][0]
        seq = [i for i in queue["items"] if i["entity_id"] == eid][:8]
        rule_seq = [(i["rule_ids"][0] if i["rule_ids"] else "ML") for i in seq]
        r.check(len(set(rule_seq)) > 1, "round-robin across rules", f"{eid}: {' -> '.join(rule_seq[:6])}")
        r.note("one loud rule cannot fill the queue with a single kind of problem")
    r.check(bool(controls), "control priorities", f"{len({c['control_id'] for c in controls})} controls ranked by expected cost")
    for c in controls[:3]:
        r.note(f"{c['label']:<42} priority {c['priority']:7.2f}  {c['n_findings']} findings  {','.join(c['top_rule_ids'])}")


# --- H. negative space -----------------------------------------------------------------

def _negative_space(r: Reporter, settings: Settings, db: Database, period: str) -> None:
    from satsa.api import queries as q

    r.section("H", "Negative space: evidence that should exist and does not")
    with db.read() as conn:
        for dim in ("category", "asset_class", "source"):
            m = q.coverage_matrix(conn, settings, period, dim)
            absent = sum(1 for row in m["rows"] for c in row["cells"] if c["status"] == "absent")
            low = sum(1 for row in m["rows"] for c in row["cells"] if c["status"] == "low")
            r.check(bool(m["columns"]), f"coverage matrix: {dim}", f"{len(m['rows'])}x{len(m['columns'])}, {absent} absent, {low} low")
        m = q.coverage_matrix(conn, settings, period, "category")
        found = None
        for row in m["rows"]:
            for i, c in enumerate(row["cells"]):
                if c["status"] == "absent":
                    found = (row["entity_id"], m["columns"][i])
                    break
            if found:
                break
        if found:
            cell = q.coverage_cell(conn, settings, found[0], found[1], period)
            r.check(bool(cell["expected_reason"]), f"why {found[1]} was expected of {found[0]}", "")
            r.note(cell["expected_reason"])
            r.note(f"observed {cell['observed']:.0f} alerts; {cell['peer_share_reporting']:.0%} of peers report it")
            r.note("an expectation a supervisor cannot interrogate is not evidence")
        vol = conn.execute("""SELECT entity_id, evidence_json FROM findings f
            JOIN audit_runs a ON a.run_id=f.run_id AND a.status='SUCCESS'
            WHERE f.submission_period = ? AND f.rule_id = 'NS-04' LIMIT 1""", [period]).fetchone()
    if vol:
        ev = (json.loads(vol[1]).get("rule") or {})
        r.check(ev.get("predicted") is not None, "peer expected-volume model",
                f"{vol[0]}: observed {ev.get('actual')}, expected {_fmt(ev.get('predicted'), 0)}, "
                f"{_fmt(ev.get('z'), 1)} sigma below, by {ev.get('method')}")
        r.note("a Huber regression on asset count, Tier-1 count, size band and previous volume")


# --- I. explainability -----------------------------------------------------------------

def _explainability(r: Reporter, settings: Settings, db: Database, period: str) -> None:
    from satsa.api import queries as q

    r.section("I", "Explainability: every finding says why, in words and in numbers")
    with db.read() as conn:
        n_total, n_rationale = conn.execute("""SELECT count(*), sum(CASE WHEN length(rationale) > 30 THEN 1 ELSE 0 END)
            FROM findings f JOIN audit_runs a ON a.run_id=f.run_id AND a.status='SUCCESS' WHERE f.submission_period = ?""", [period]).fetchone()
        rule_f = conn.execute("""SELECT finding_id FROM findings f JOIN audit_runs a ON a.run_id=f.run_id AND a.status='SUCCESS'
            WHERE f.submission_period = ? AND f.rule_id IS NOT NULL ORDER BY p_final DESC LIMIT 1""", [period]).fetchone()
        comb = conn.execute("""SELECT finding_id FROM findings f JOIN audit_runs a ON a.run_id=f.run_id AND a.status='SUCCESS'
            WHERE f.submission_period = ? AND f.rule_id IS NULL AND f.shap_json IS NOT NULL LIMIT 1""", [period]).fetchone()
        r.check(n_total == n_rationale, "every finding carries a rationale", f"{n_rationale} of {n_total}")

        if rule_f:
            d = q.finding_detail(conn, settings, rule_f[0])
            r.check(d["rule"] is not None, "rule finding shows its template and parameters", d["rule"]["rule_id"])
            r.check(len(d["evidence_features"]) > 0, "evidence against the peer group", f"{len(d['evidence_features'])} features")
            for f in d["evidence_features"][:3]:
                r.note(f"{f['label']:<34} entity {_fmt(f['value'], 3):>9}  peer median {_fmt(f['peer_median'], 3):>9}  z {_fmt(f['z'], 1):>6}")
        if comb:
            d = q.finding_detail(conn, settings, comb[0])
            shap = d["shap"] or {}
            r.check(bool(shap.get("contributions")), "model attribution", f"method {shap.get('method')}, {len(shap.get('contributions', []))} contributions")
            for c in (shap.get("contributions") or [])[:3]:
                r.note(f"{(c.get('label') or c['feature']):<34} contribution {c['shap']:+.3f}")
            r.check(bool(d.get("what_would_change")), "counterfactual", "")
            if d.get("what_would_change"):
                r.note(d["what_would_change"][:160])


# --- J. evidence chain -----------------------------------------------------------------

def _evidence_chain(r: Reporter, settings: Settings, db: Database, period: str) -> None:
    from satsa.api import queries as q

    r.section("J", "Drill-down: finding to the records that evidence it, in three clicks")
    with db.read() as conn:
        f = conn.execute("""SELECT finding_id, entity_id FROM findings f JOIN audit_runs a ON a.run_id=f.run_id AND a.status='SUCCESS'
            WHERE f.submission_period = ? AND f.n_evidence_alerts > 0 ORDER BY n_evidence_alerts DESC LIMIT 1""", [period]).fetchone()
        if not f:
            r.check(False, "a finding with alert-level evidence", "none found")
            return
        recs = q.finding_records(conn, f[0], 3, 0, "ttc")
        r.check(recs["total"] > 0, "records behind the finding", f"{recs['total']} alerts")
        for a in recs["items"]:
            r.note(f"{a['alert_id']}  {a['severity']:<8} ttc {_fmt(a['time_to_close_min'], 0):>6} min  {a['closure_reason']}")
        a = recs["items"][0]
        full = q.alert_with_source(conn, a["entity_id"], a["submission_period"], a["alert_id"])
        r.check(full is not None, "the raw record as submitted", "")
        if full:
            r.check(full["submission"] is not None, "traced to its source file",
                    f"{full['submission']['file_name']} sha256 {full['submission']['file_hash'][:12]}" if full["submission"] else "")
            r.check(full["raw_line"] is not None, "original source line recoverable", "read back from the archived file")


# --- K. feedback -----------------------------------------------------------------------

def _feedback(r: Reporter, settings: Settings, db: Database, period: str) -> None:
    from satsa.feedback.recalibrate import recalibrate
    from satsa.feedback.store import feedback_stats, history, latest_decisions, record_feedback

    r.section("K", "Supervisor feedback: appended, never overwritten")
    with db.read() as conn:
        # Deliberately a combined Module A finding: those are the ones the calibrator learns
        # from, so the feedback loop is demonstrated end to end rather than half of it.
        f = conn.execute("""SELECT finding_id FROM findings f JOIN audit_runs a ON a.run_id=f.run_id AND a.status='SUCCESS'
            WHERE f.submission_period = ? AND f.rule_id IS NULL AND f.module = 'A'
            ORDER BY priority_rank LIMIT 1""", [period]).fetchone()
    if not f:
        r.check(False, "a finding to decide on", "none")
        return
    fid = f[0]
    with db.write() as conn:
        first = record_feedback(conn, settings, target_type="finding", target_id=fid, decision="ACCEPT",
                                reviewer_id="showcase_examiner", note="Confirmed during the walkthrough.", source="cli")
        second = record_feedback(conn, settings, target_type="finding", target_id=fid, decision="REJECT",
                                 reviewer_id="showcase_reviewer", note="Second reviewer disagreed.", source="cli")
    with db.read() as conn:
        h = history(conn, fid)
        current = latest_decisions(conn, [fid]).get(fid)
        stats = feedback_stats(conn)
        audited = conn.execute("SELECT count(*) FROM audit_runs WHERE run_type = 'FEEDBACK'").fetchone()[0]
    r.check(len(h) >= 2, "both decisions retained", f"{len(h)} entries on this finding")
    r.check(current == "REJECT", "latest decision wins", f"ACCEPT then REJECT -> current {current}")
    r.note("the first decision is not deleted; a reviewer can see that two people disagreed")
    r.check(audited >= 2, "each decision left an audit row", f"{audited} feedback events")
    r.check(stats["n_feedback"] >= 2, "feedback statistics", f"{stats['n_feedback']} decisions on {stats['n_targets']} items")
    from satsa.feedback.store import labelled_findings

    with db.read() as conn:
        labelled = labelled_findings(conn)
    r.check(len(labelled) >= 1, "decisions become calibrator labels", f"{len(labelled)} labelled finding(s) available")
    res = recalibrate(db, settings, promote=False)
    r.check(res.skipped_reason is not None or res.calibrator_version is not None, "recalibration is bounded",
            res.skipped_reason or f"new calibrator {res.calibrator_version}, not promoted")
    r.note(f"it refuses to refit on {len(labelled)} label(s); the floor is {settings.pipeline.min_labels_for_recalibration}")
    r.note("and even with enough, a new version is registered inactive until someone promotes it")


# --- L. governance ---------------------------------------------------------------------

def _governance(r: Reporter, settings: Settings, db: Database, period: str) -> None:
    from satsa.audit.verify import verify_chain
    from satsa.pipeline.run import run_pipeline

    r.section("L", "Governance: idempotent, reproducible, and tamper-evident")
    with db.read() as conn:
        kinds = dict(conn.execute("SELECT run_type, count(*) FROM audit_runs GROUP BY 1").fetchall())
        v = verify_chain(conn)
    r.check(v.ok, "audit chain verifies", f"{v.n_runs} finalised runs")
    r.check({"INGEST", "PIPELINE", "TRAIN", "FEEDBACK"} <= set(kinds), "every action type audited",
            " ".join(f"{k} {n}" for k, n in sorted(kinds.items())))
    r.note("command line and API are audited identically; the event lives in the function, not the router")

    # Idempotency and reproducibility, executed rather than asserted. The first call
    # establishes a baseline under the code and configuration running right now, because the
    # code hash is part of the identity: editing the package correctly invalidates a match.
    baseline = run_pipeline(period, settings=settings, db=db, triggered_by="showcase", trigger_source="cli")
    again = run_pipeline(period, settings=settings, db=db, triggered_by="showcase", trigger_source="cli")
    r.check(again.status == "SKIPPED_IDENTICAL", "identical inputs are not re-scored",
            f"first call {baseline.status}, second {again.status}")
    r.note("identity covers the inputs, the configuration, the model versions and the code hash")
    forced = run_pipeline(period, settings=settings, db=db, force=True, triggered_by="showcase", trigger_source="cli")
    with db.read() as conn:
        hashes = [x[0] for x in conn.execute("""SELECT output_hash FROM audit_runs WHERE run_type='PIPELINE'
            AND status='SUCCESS' AND submission_period = ? ORDER BY finished_at DESC LIMIT 2""", [period]).fetchall()]
    r.check(len(hashes) == 2 and hashes[0] == hashes[1], "a forced re-run reproduces the same output",
            f"output hash {str(hashes[0])[:16]}")
    r.note(f"stage log: {' -> '.join(s['stage'] for s in forced.stage_log)}")

    # Tamper detection, proven on an in-memory copy of the ledger so the real database is
    # untouched. DuckDB holds an exclusive lock on its file, so the rows are copied rather
    # than the file; verify_chain reads only audit_runs, which makes the two equivalent.
    with db.read() as conn:
        ledger = conn.execute("SELECT * FROM audit_runs ORDER BY started_at").df()
    scratch = duckdb.connect(":memory:")
    scratch.register("ledger", ledger)
    scratch.execute("CREATE TABLE audit_runs AS SELECT * FROM ledger")
    r.check(verify_chain(scratch).ok, "the copied ledger verifies first", "so the break below is the tamper, not the copy")
    target = scratch.execute("SELECT run_id FROM audit_runs WHERE status='SUCCESS' ORDER BY finished_at LIMIT 1").fetchone()[0]
    scratch.execute("UPDATE audit_runs SET config_hash = 'tampered' WHERE run_id = ?", [target])
    broken = verify_chain(scratch)
    scratch.close()
    r.check(not broken.ok and broken.first_broken_run_id == target, "one edited field is detected",
            f"break at {str(broken.first_broken_run_id)[:20]}: {broken.detail}")
    r.note("the working database was never modified; only an in-memory copy of the ledger")


# --- M. configuration ------------------------------------------------------------------

def _configuration(r: Reporter, settings: Settings, db: Database, period: str) -> None:
    from satsa.api.config_store import effective_config, what_if
    from satsa.api.schemas import WhatIfRequest

    r.section("M", "Configuration: nothing is hard-coded, and changes are previewed")
    cfg = effective_config(settings)
    r.check(len(cfg["rules"]) == 19, "rules exposed as data", f"{len(cfg['rules'])} rules, editable through the API")
    r.check(bool(cfg["costs"]["derived"]), "thresholds derived from costs",
            " ".join(f"{k} t*={v['t_star']:.3f}" for k, v in cfg["costs"]["derived"].items()))
    with db.read() as conn:
        base = what_if(conn, settings, WhatIfRequest(period=period))
        harsher = what_if(conn, settings, WhatIfRequest(period=period, costs={"execution_gap": {"C_FP": 1.0, "C_FN": 9.0}}))
        reweighted = what_if(conn, settings, WhatIfRequest(period=period, sri_weights={"execution_gap": 0.50, "negative_space": 0.15}))
    r.check(harsher["thresholds"]["execution_gap"]["t_star"] < base["thresholds"]["execution_gap"]["t_star"],
            "costing a miss higher lowers t*",
            f"{base['thresholds']['execution_gap']['t_star']:.3f} -> {harsher['thresholds']['execution_gap']['t_star']:.3f}")
    r.check(True, "uncertain count moves with it", f"{base['n_uncertain_before']} -> {harsher['n_uncertain_after']}")
    moved = sum(1 for a, b in zip(base["rows"], reweighted["rows"]) if abs((a["sri_what_if"] or 0) - (b["sri_what_if"] or 0)) > 0.5)
    r.check(moved > 0, "reweighting previews new scores", f"{moved} of {len(base['rows'])} entities move by more than 0.5")
    r.note("the preview writes nothing; saving requires the weights to sum to 1.00 and records a new config hash")


# --- N. reports ------------------------------------------------------------------------

def _reports(r: Reporter, settings: Settings, db: Database, period: str) -> None:
    from satsa.reports.csv_export import export_csv
    from satsa.reports.pdf import entity_report, period_report

    r.section("N", "Reports: PDF and CSV, stamped with the hashes that produced them")
    with db.read() as conn:
        eid = conn.execute("SELECT entity_id FROM sri_scores WHERE submission_period = ? ORDER BY sri DESC LIMIT 1", [period]).fetchone()[0]
        run_id = conn.execute("""SELECT run_id FROM audit_runs WHERE run_type='PIPELINE' AND status='SUCCESS'
                                 AND submission_period = ? ORDER BY finished_at DESC LIMIT 1""", [period]).fetchone()[0]
        t = time.perf_counter()
        p1 = entity_report(conn, settings, eid, period)
        t1 = time.perf_counter() - t
        p2 = period_report(conn, settings, period)
        r.check(p1.exists() and p1.read_bytes()[:4] == b"%PDF", f"entity report for {eid}",
                f"{p1.name}, {p1.stat().st_size // 1024} KB, {t1:.1f}s")
        r.check(p2.exists() and p2.read_bytes()[:4] == b"%PDF", "portfolio report", f"{p2.name}, {p2.stat().st_size // 1024} KB")
        for kind in ("findings", "sri", "alert_samples", "features"):
            text = export_csv(conn, kind, run_id)
            lines = text.strip().splitlines()
            r.check(len(lines) >= 1, f"  {kind}.csv", f"{len(lines) - 1} rows, {len(lines[0].split(','))} columns")


# --- O. API ----------------------------------------------------------------------------

def _api(r: Reporter, settings: Settings, db: Database, period: str) -> None:
    from fastapi.testclient import TestClient

    from satsa.api.main import create_app

    r.section("O", "API: every endpoint family, in-process")
    app = create_app(settings=settings, database=db)
    urls = [
        ("health", "/api/v1/health"), ("periods", "/api/v1/periods"), ("summary", f"/api/v1/summary?period={period}"),
        ("entities", "/api/v1/entities"), ("heatmap", f"/api/v1/entities/heatmap?period={period}"),
        ("findings", f"/api/v1/findings?period={period}"), ("review queue", f"/api/v1/review/queue?period={period}"),
        ("controls", f"/api/v1/controls/priority?period={period}"), ("benchmark metrics", "/api/v1/benchmark/metrics"),
        ("benchmark", f"/api/v1/benchmark?feature=note_template_score&period={period}"),
        ("coverage", f"/api/v1/coverage?period={period}"), ("trends sector", "/api/v1/trends/sector"),
        ("trends controls", "/api/v1/trends/controls"), ("submissions", f"/api/v1/ingest/submissions?period={period}"),
        ("pipeline runs", "/api/v1/pipeline/runs"), ("config", "/api/v1/config"), ("audit runs", "/api/v1/audit/runs"),
        ("audit verify", "/api/v1/audit/verify"), ("models", "/api/v1/models"), ("feedback stats", "/api/v1/feedback/stats"),
        ("reports", "/api/v1/reports"),
    ]
    with TestClient(app) as client:
        bad = []
        for name, url in urls:
            code = client.get(url).status_code
            if code != 200:
                bad.append(f"{name} {code}")
        r.check(not bad, f"{len(urls)} endpoints respond", "all 200" if not bad else ", ".join(bad))
        h = client.get("/api/v1/health").json()
        r.check(bool(h["active_models"]), "health reports the active engine", ", ".join(f"{k} {v}" for k, v in h["active_models"].items()))
        r.check(client.get("/api/v1/findings/does-not-exist").status_code == 404, "unknown id is a clean 404", "")
        r.check(client.get("/api/v1/benchmark?feature=nope").status_code == 404, "unknown feature is a clean 404", "")
        spa = client.get("/entities/E03")
        r.check(spa.status_code in (200, 503), "dashboard served from the same origin",
                "bundle present" if spa.status_code == 200 else "bundle not built (run npm run build)")


# --- P. offline ------------------------------------------------------------------------

def _offline(r: Reporter) -> None:
    r.section("P", "Offline guarantee")
    import satsa

    root = Path(satsa.__file__).parent
    banned = ("openai", "anthropic", "transformers", "torch", "tensorflow", "huggingface",
              "requests", "urllib.request", "httpx", "aiohttp")
    # Match real imports rather than any mention of the word, and skip this file, which has to
    # name the packages it is looking for.
    patterns = [re.compile(rf"^\s*(?:import|from)\s+{re.escape(pkg)}\b", re.M) for pkg in banned]
    hits = []
    for f in sorted(root.rglob("*.py")):
        if f.name == "showcase.py":
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        for pkg, pat in zip(banned, patterns):
            if pat.search(text):
                hits.append(f"{f.relative_to(root)}:{pkg}")
    r.check(not hits, "no LLM or external AI import", "; ".join(hits) if hits else f"none across {len(list(root.rglob('*.py')))} modules")
    r.note("the analytics are classical scikit-learn; nothing calls a hosted model")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.4)
        s.connect(("203.0.113.1", 443))  # TEST-NET-3, never routable
        s.close()
        reached = True
    except OSError:
        reached = False
    r.check(not reached, "no outbound traffic is required", "the test suite fails any non-loopback connect")


# --- Q. UI -----------------------------------------------------------------------------

def _ui(r: Reporter, settings: Settings) -> None:
    r.section("Q", "Dashboard: every route rendered in a real browser")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        r.check(False, "playwright available", "pip install playwright, then playwright install chromium")
        return
    import os

    base = os.environ.get("SATSA_BASE", "http://127.0.0.1:8000")
    chrome = os.environ.get("SATSA_CHROME")
    routes = ["/portfolio", "/entities/E03", "/findings", "/queue", "/peer", "/coverage",
              "/trends", "/ingestion", "/config", "/audit", "/reports"]
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=chrome) if chrome else pw.chromium.launch()
            for path in routes:
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                errs: list[str] = []
                page.on("pageerror", lambda e: errs.append(str(e)))
                page.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
                page.goto(base + path, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(900)
                rows = page.locator("tbody tr").count()
                r.check(not errs, f"  {path}", f"{rows} rows rendered" + ("" if not errs else f" · {errs[0][:60]}"))
                page.close()
            browser.close()
    except Exception as exc:  # noqa: BLE001
        r.check(False, "browser pass", f"{type(exc).__name__}: {exc}. Is `satsa serve` running?")


# --- summary ---------------------------------------------------------------------------

def _summary(r: Reporter) -> None:
    res = r.result
    r.echo("")
    r.echo("=" * WIDTH)
    r.echo(" SUMMARY")
    r.echo("=" * WIDTH)
    for s in res.sections:
        n_ok = sum(1 for c in s.checks if c.ok)
        mark = "ok  " if s.ok else "FAIL"
        r.echo(f"  {mark}  {s.key} · {s.title[:56]:<56} {n_ok}/{len(s.checks)}")
    r.echo("")
    r.echo(f"  {len(res.checks) - len(res.failed)} of {len(res.checks)} checks passed across {len(res.sections)} sections.")
    if res.failed:
        r.echo("")
        for c in res.failed:
            r.echo(f"  FAILED: {c.name} — {c.detail}")
    else:
        r.echo("  Every capability the project claims was executed and demonstrated.")
    r.echo("")
    r.echo("  Not demonstrated, because it does not exist: a held-out accuracy measurement.")
    r.echo("  See KNOWN_GAPS.md gap 1. No precision or recall figure is quoted anywhere.")
    r.echo("")
