"""Feedback store. Every decision is a new row; the latest row per target is the current one."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import duckdb

from satsa.audit.audit_log import record_event
from satsa.audit.hashing import new_id
from satsa.config import Settings
from satsa.db.repo import fetch_df, fetch_one, to_json

DECISIONS = {"ACCEPT", "REJECT", "DEFER"}


def record_feedback(conn: duckdb.DuckDBPyConnection, settings: Settings, *, target_type: str, target_id: str, decision: str,
                    reviewer_id: str, note: str | None = None, source: str = "api") -> dict[str, Any]:
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {sorted(DECISIONS)}")
    if target_type == "finding":
        row = fetch_one(conn, "SELECT run_id, entity_id, submission_period, rule_id, p_final FROM findings WHERE finding_id = ?", [target_id])
    elif target_type == "alert_flag":
        row = fetch_one(conn, "SELECT run_id, entity_id, submission_period, NULL, p_alert FROM alert_sample_flags WHERE flag_id = ?", [target_id])
    else:
        raise ValueError("target_type must be finding or alert_flag")
    if row is None:
        raise KeyError(f"{target_type} {target_id} not found")
    run_id, entity_id, period, rule_id, p = row
    versions = fetch_one(conn, "SELECT model_versions_json FROM audit_runs WHERE run_id = ?", [run_id])
    feedback_id = new_id("fb_")
    conn.execute(
        """INSERT INTO feedback (feedback_id, run_id, target_type, target_id, entity_id, submission_period, rule_id, decision, reviewer_id, note, p_at_decision, model_versions_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [feedback_id, run_id, target_type, target_id, entity_id, period, rule_id, decision, reviewer_id, note, p, versions[0] if versions else None, datetime.now()],
    )
    record_event(conn, settings, run_type="FEEDBACK", period=period, triggered_by=reviewer_id, trigger_source=source,
                 manifest={"feedback_id": feedback_id, "target_type": target_type, "target_id": target_id, "decision": decision})
    return {"feedback_id": feedback_id, "run_id": run_id, "target_type": target_type, "target_id": target_id, "decision": decision, "reviewer_id": reviewer_id, "note": note, "p_at_decision": p, "created_at": datetime.now().isoformat(timespec="seconds")}


def latest_decisions(conn: duckdb.DuckDBPyConnection, target_ids: list[str]) -> dict[str, str]:
    if not target_ids:
        return {}
    ph = ",".join("?" * len(target_ids))
    df = fetch_df(conn, f"""
        SELECT target_id, decision FROM (
            SELECT target_id, decision, row_number() OVER (PARTITION BY target_id ORDER BY created_at DESC) AS rn
            FROM feedback WHERE target_id IN ({ph})
        ) WHERE rn = 1""", target_ids)
    return dict(zip(df["target_id"], df["decision"]))


def history(conn: duckdb.DuckDBPyConnection, target_id: str) -> list[dict[str, Any]]:
    df = fetch_df(conn, "SELECT feedback_id, target_type, target_id, decision, reviewer_id, note, p_at_decision, created_at FROM feedback WHERE target_id = ? ORDER BY created_at DESC", [target_id])
    return _records(df)


def feedback_stats(conn: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    rules = fetch_df(conn, """
        SELECT rule_id, count(*) AS n, avg(CASE WHEN decision = 'ACCEPT' THEN 1.0 WHEN decision = 'REJECT' THEN 0.0 END) AS accept_rate
        FROM (SELECT rule_id, decision, row_number() OVER (PARTITION BY target_id ORDER BY created_at DESC) AS rn FROM feedback WHERE rule_id IS NOT NULL)
        WHERE rn = 1 GROUP BY rule_id ORDER BY rule_id""")
    cals = fetch_df(conn, "SELECT model_name AS name, version, training_rows AS n_labels, metrics_json FROM model_registry WHERE is_active = TRUE AND model_name LIKE 'calibrator_%'")
    import json

    calibrators = []
    for r in cals.itertuples(index=False):
        m = json.loads(r.metrics_json) if isinstance(r.metrics_json, str) else (r.metrics_json or {})
        calibrators.append({"name": r.name, "version": r.version, "n_labels": int(r.n_labels or 0), "ece": m.get("ece"), "calibrated": bool(m.get("calibrated"))})
    total = fetch_one(conn, "SELECT count(*), count(DISTINCT target_id) FROM feedback")
    return {"rules": _records(rules), "calibrators": calibrators, "n_feedback": int(total[0]), "n_targets": int(total[1])}


def _records(df) -> list[dict[str, Any]]:
    import json

    return json.loads(df.to_json(orient="records", date_format="iso")) if len(df) else []


def labelled_findings(conn: duckdb.DuckDBPyConnection) -> list[tuple[str, float | None, float]]:
    """(finding_id, raw ML score, label) for combined findings with ACCEPT/REJECT feedback."""
    df = fetch_df(conn, """
        SELECT f.finding_id, f.score_components_json, fb.decision FROM findings f
        JOIN (SELECT target_id, decision, row_number() OVER (PARTITION BY target_id ORDER BY created_at DESC) AS rn FROM feedback WHERE target_type = 'finding') fb
          ON fb.target_id = f.finding_id AND fb.rn = 1
        WHERE f.rule_id IS NULL AND f.module = 'A' AND fb.decision IN ('ACCEPT', 'REJECT')""")
    import json

    out = []
    for r in df.itertuples(index=False):
        comp = json.loads(r.score_components_json) if isinstance(r.score_components_json, str) else (r.score_components_json or {})
        ml = comp.get("ml") or {}
        out.append((r.finding_id, ml.get("s_ml"), 1.0 if r.decision == "ACCEPT" else 0.0))
    return out


def rule_precision(conn: duckdb.DuckDBPyConnection, min_decisions: int = 15) -> list[dict[str, Any]]:
    """Per-rule accept precision from the latest decision on each rule finding, with a bounded suggestion."""
    stats = feedback_stats(conn)["rules"]
    out = []
    for r in stats:
        n, q = int(r["n"]), r.get("accept_rate")
        suggestion = None
        if n >= min_decisions and q is not None:
            if q < 0.4:
                suggestion = "raise threshold one step (low precision)"
            elif q > 0.9:
                suggestion = "consider lowering threshold one step (very high precision)"
        out.append({"rule_id": r["rule_id"], "n": n, "accept_rate": q, "suggestion": suggestion, "prior_weight_posterior": None if q is None else round((q * n + 1) / (n + 2), 3)})
    return out


def as_json(obj: Any) -> str:
    return to_json(obj)
