"""Build the entity-period feature table for one submission period and persist it."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import duckdb
import pandas as pd

from satsa.config import Settings
from satsa.db.repo import fetch_df, insert_df, to_json
from satsa.features import registry
from satsa.features.base import OK, EntityContext, FeatureValue
from satsa.features.peer import PeerAssignment, assign_peer_groups, compute_peer_stats
from satsa.version import FEATURE_VERSION

HISTORY_PERIODS = 5
HEADLINE_COLUMNS = [
    "n_alerts", "n_alerts_critical", "n_alerts_high", "n_closed", "ttc_median_critical", "ttc_median_high", "ttc_cv_critical",
    "fast_close_rate_critical", "fast_close_rate_high", "ack_only_rate", "ack_then_close_no_invest_rate", "escalation_ratio",
    "escalation_ratio_critical", "critical_closed_no_escalation_rate", "closure_reason_entropy", "closure_reason_top_share",
    "fp_rate_critical", "note_missing_rate", "note_template_score", "note_dup_cluster_share", "note_distinct_ratio",
    "repeat_no_remediation_rate", "cross_period_repeat_rate", "coverage_gap_score", "coverage_gap_score_tier1",
    "silent_asset_rate_tier1", "silent_asset_rate_tier1_hist", "criticality_volume_ratio", "volume_delta_pct",
    "aact_inv_gap_30_wmean", "aact_inv_gap_30_max", "aact_inv_rate_slope_30", "batch_close_score", "val_err_rate",
    "val_warn_rate", "unknown_asset_alert_rate",
]


@dataclass
class FeatureBuildResult:
    period: str
    run_id: str
    rows: pd.DataFrame                 # one row per entity, ready for features_entity_period
    baselines: pd.DataFrame            # rows for peer_baselines
    contexts: dict[str, EntityContext]  # kept in memory for the analytics modules (extras/evidence)
    values: dict[str, dict[str, FeatureValue]]
    assignments: dict[str, PeerAssignment]
    seconds: float


def _periods_before(conn: duckdb.DuckDBPyConnection, period: str, k: int) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT submission_period FROM alerts WHERE submission_period < ? ORDER BY submission_period DESC LIMIT ?",
        [period, k],
    ).fetchall()
    return sorted(r[0] for r in rows)


def _validation_summary(conn: duckdb.DuckDBPyConnection, period: str) -> dict[str, dict[str, Any]]:
    subs = fetch_df(
        conn,
        "SELECT entity_id, validation_json FROM raw_submissions WHERE submission_period = ? AND superseded = FALSE",
        [period],
    )
    out: dict[str, dict[str, Any]] = {}
    for r in subs.itertuples():
        rep = json.loads(r.validation_json) if isinstance(r.validation_json, str) else (r.validation_json or {})
        agg = out.setdefault(str(r.entity_id), {"n_rows": 0, "ERROR": 0, "WARN": 0, "FATAL": 0})
        agg["n_rows"] += int(rep.get("n_rows", 0))
        for lvl, n in (rep.get("level_counts") or {}).items():
            agg[lvl] = agg.get(lvl, 0) + int(n)
        for cid, n in (rep.get("counts") or {}).items():
            agg[cid] = agg.get(cid, 0) + int(n)
        agg["fatal"] = bool(rep.get("fatal")) or agg.get("fatal", False)
    return out


def load_inputs(conn: duckdb.DuckDBPyConnection, period: str) -> dict[str, Any]:
    prior = _periods_before(conn, period, HISTORY_PERIODS)
    periods = prior + [period]
    ph = ",".join("?" * len(periods))
    alerts = fetch_df(conn, f"SELECT * FROM alerts WHERE submission_period IN ({ph})", periods)
    for col in ("ts", "acknowledged_at", "investigated_at", "closed_at", "escalated_at"):
        alerts[col] = pd.to_datetime(alerts[col])
    return {
        "prior_periods": prior,
        "alerts": alerts,
        "entities": fetch_df(conn, "SELECT * FROM entities ORDER BY entity_id"),
        "assets": fetch_df(conn, "SELECT * FROM assets"),
        "escalations": fetch_df(conn, "SELECT * FROM escalations WHERE submission_period = ?", [period]),
        "incidents": fetch_df(conn, "SELECT * FROM incidents WHERE submission_period = ?", [period]),
        "validation": _validation_summary(conn, period),
    }


def build_features(conn: duckdb.DuckDBPyConnection, settings: Settings, period: str, run_id: str) -> FeatureBuildResult:
    t0 = time.perf_counter()
    inputs = load_inputs(conn, period)
    alerts: pd.DataFrame = inputs["alerts"]
    entities: pd.DataFrame = inputs["entities"]
    current = alerts[alerts["submission_period"] == period]
    history = alerts[alerts["submission_period"] != period]

    # Entities to score: those with a submission this period (even if it had zero rows).
    submitted = set(inputs["validation"]) | set(current["entity_id"].astype(str))
    scored = entities[entities["entity_id"].astype(str).isin(submitted)]

    contexts: dict[str, EntityContext] = {}
    values: dict[str, dict[str, FeatureValue]] = {}
    for ent in scored.itertuples():
        eid = str(ent.entity_id)
        ctx = EntityContext(
            entity_id=eid, period=period, entity=ent._asdict(),
            alerts=current[current["entity_id"] == eid].reset_index(drop=True),
            history=history[history["entity_id"] == eid].reset_index(drop=True),
            prior_periods=inputs["prior_periods"],
            assets=inputs["assets"][inputs["assets"]["entity_id"] == eid].reset_index(drop=True),
            escalations=inputs["escalations"][inputs["escalations"]["entity_id"] == eid],
            incidents=inputs["incidents"][inputs["incidents"]["entity_id"] == eid],
            validation=inputs["validation"].get(eid, {"n_rows": 0}),
            global_alerts=alerts, settings=settings,
        )
        feats: dict[str, FeatureValue] = {}
        for mod in registry.MODULES:
            feats.update(mod.compute(ctx))
        contexts[eid] = ctx
        values[eid] = feats

    # Peer statistics over registered features.
    table = pd.DataFrame({eid: {k: v.value for k, v in f.items()} for eid, f in values.items()}).T
    table = table.reindex(columns=registry.FEATURE_NAMES)
    table.index.name = "entity_id"
    support = {eid: {k: v.flag for k, v in f.items()} for eid, f in values.items()}
    assignments = assign_peer_groups(scored, settings)
    z, pct, flags, baselines = compute_peer_stats(table, support, assignments, registry.FEATURE_NAMES, settings)

    rows = []
    now = datetime.now()
    for eid, feats in values.items():
        asg = assignments[eid]
        row: dict[str, Any] = {
            "entity_id": eid, "submission_period": period, "run_id": run_id, "feature_version": FEATURE_VERSION, "computed_at": now,
            "features_json": to_json({k: v.value for k, v in feats.items()}),
            "support_json": to_json({k: {"n": v.n, "flag": flags.get(eid, {}).get(k, v.flag)} for k, v in feats.items()}),
            "peer_z_json": to_json(z[eid]),
            "peer_pct_json": to_json(pct[eid]),
            "peer_group_id": asg.peer_group_id, "peer_level": asg.peer_level, "peer_n": len(asg.members),
        }
        for col in HEADLINE_COLUMNS:
            v = feats.get(col)
            row[col] = None if v is None else v.value
        rows.append(row)
    rows_df = pd.DataFrame(rows)
    for col in ("n_alerts", "n_alerts_critical", "n_alerts_high", "n_closed"):
        rows_df[col] = rows_df[col].astype("Int64")

    base_df = pd.DataFrame(baselines)
    if len(base_df):
        base_df["submission_period"] = period
        base_df["run_id"] = run_id
    return FeatureBuildResult(period, run_id, rows_df, base_df, contexts, values, assignments, time.perf_counter() - t0)


def persist_features(conn: duckdb.DuckDBPyConnection, result: FeatureBuildResult) -> dict[str, int]:
    return {
        "features_entity_period": insert_df(conn, "features_entity_period", result.rows),
        "peer_baselines": insert_df(conn, "peer_baselines", result.baselines) if len(result.baselines) else 0,
    }


def feature_frame(result: FeatureBuildResult) -> pd.DataFrame:
    """Convenience: entity x feature values as floats (NaN when missing), for models and rules."""
    return pd.DataFrame({eid: {k: v.value for k, v in f.items()} for eid, f in result.values.items()}).T.reindex(columns=registry.FEATURE_NAMES).astype(float)


def support_ok(result: FeatureBuildResult, entity_id: str, feature: str) -> bool:
    v = result.values.get(entity_id, {}).get(feature)
    return v is not None and v.flag == OK and v.value is not None
