"""CSV exports of the current run's outputs."""

from __future__ import annotations

import duckdb

from satsa.db.repo import fetch_df

QUERIES = {
    "findings": "SELECT finding_id, entity_id, submission_period, module, finding_class, source, rule_id, control_id, capability, severity, p_rule, p_ml, p_final, calibrated, decision, t_star, expected_cost, priority_rank, title, rationale, n_evidence_alerts FROM findings WHERE run_id = ? {ent} ORDER BY priority_rank",
    "sri": "SELECT entity_id, submission_period, sri, band, confidence, priority_rank, priority_score, dim_execution_gap, dim_negative_space, dim_escalation_discipline, dim_investigation_quality, dim_data_integrity, dim_trend_penalty, sri_delta_prev, weights_hash FROM sri_scores WHERE run_id = ? {ent} ORDER BY priority_rank",
    "alert_samples": "SELECT q.entity_id, q.submission_period, q.alert_id, array_to_string(q.rule_ids, '|') AS rule_ids, q.flag_source, q.p_alert, q.decision, q.queue_rank, q.queue_reason, q.rationale, a.severity, a.category, a.asset_id, a.time_to_close_min, a.closure_reason FROM alert_sample_flags q LEFT JOIN alerts a ON a.entity_id = q.entity_id AND a.submission_period = q.submission_period AND a.alert_id = q.alert_id WHERE q.run_id = ? AND q.queue_rank IS NOT NULL {entq} ORDER BY q.entity_id, q.queue_rank",
    "features": "SELECT * EXCLUDE (features_json, support_json, peer_z_json, peer_pct_json) FROM features_entity_period WHERE run_id = ? {ent} ORDER BY entity_id",
}


def export_csv(conn: duckdb.DuckDBPyConnection, kind: str, run_id: str, entity_id: str | None = None) -> str:
    sql = QUERIES[kind].format(ent="AND entity_id = ?" if entity_id else "", entq="AND q.entity_id = ?" if entity_id else "")
    df = fetch_df(conn, sql, [run_id] + ([entity_id] if entity_id else []))
    return df.to_csv(index=False)
