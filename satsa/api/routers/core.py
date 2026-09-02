"""Meta, entities, findings, evidence, review queue and feedback endpoints."""

from __future__ import annotations

import duckdb
from fastapi import APIRouter, Depends, HTTPException, Query

from satsa.api import queries as q
from satsa.api.deps import get_db_dep, get_reader, get_settings_dep
from satsa.api.schemas import BulkFeedbackRequest, FeedbackRequest, HealthResponse, RecalibrateRequest
from satsa.config import Settings
from satsa.db.connection import Database
from satsa.feedback.store import feedback_stats, history, record_feedback
from satsa.models.registry import active_versions
from satsa.version import FEATURE_VERSION, RULES_VERSION, __version__, get_code_hash

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health(conn: duckdb.DuckDBPyConnection = Depends(get_reader), settings: Settings = Depends(get_settings_dep)) -> dict:
    return {"status": "ok", "app_version": __version__, "rules_version": RULES_VERSION, "feature_version": FEATURE_VERSION, "code_hash": get_code_hash(),
            "config_hash": settings.config_hash, "db_path": str(settings.db_path), "active_models": {k: v["version"] for k, v in active_versions(conn).items()}}


@router.get("/periods")
def periods(conn=Depends(get_reader)) -> list[dict]:
    return q.periods(conn)


@router.get("/summary")
def summary(period: str | None = None, conn=Depends(get_reader)) -> dict:
    return q.summary(conn, period)


@router.get("/entities")
def entities(conn=Depends(get_reader)) -> list[dict]:
    return q.entities(conn)


@router.get("/entities/heatmap")
def heatmap(period: str | None = None, lens: str = "sri", sector: str | None = None, conn=Depends(get_reader)) -> dict:
    return q.heatmap(conn, period, lens, sector)


@router.get("/entities/{entity_id}")
def entity_detail(entity_id: str, period: str | None = None, conn=Depends(get_reader), settings: Settings = Depends(get_settings_dep)) -> dict:
    ents = {e["entity_id"]: e for e in q.entities(conn)}
    if entity_id not in ents:
        raise HTTPException(404, f"entity {entity_id} not found")
    p, run_id = q.current_run(conn, period)
    findings = q.list_findings(conn, period=p, entity_id=entity_id, limit=10_000)["items"]
    by_class = {"execution_gap": 0, "negative_space": 0}
    by_decision = {"AUTO_FLAG": 0, "MANUAL_REVIEW": 0, "AUTO_CLEAR": 0}
    for f in findings:
        by_class[f["finding_class"]] = by_class.get(f["finding_class"], 0) + 1
        by_decision[f["decision"]] = by_decision.get(f["decision"], 0) + 1
    controls = [c for c in q.control_priorities(conn, settings, p) if c["entity_id"] == entity_id]
    trend = q.trend_entity(conn, entity_id)
    return {
        "entity": ents[entity_id], "period": p, "run_id": run_id, "sri": q.sri_scorecard(conn, settings, entity_id, p),
        "findings_summary": {"by_class": by_class, "by_decision": by_decision}, "headline_features": q.headline_features(conn, entity_id, run_id) if run_id else [],
        "controls": [{"control_id": c["control_id"], "label": c["label"], "priority": c["priority"], "n_findings": c["n_findings"], "top_rule_ids": c["top_rule_ids"]} for c in controls],
        "recent_periods": [{"period": pp, "sri": s} for pp, s in zip(trend["periods"], trend["sri"])], "data_quality": q.data_quality(conn, entity_id, p) if p else None,
    }


@router.get("/entities/{entity_id}/sri")
def entity_sri(entity_id: str, period: str | None = None, conn=Depends(get_reader), settings: Settings = Depends(get_settings_dep)) -> dict:
    card = q.sri_scorecard(conn, settings, entity_id, period)
    if card is None:
        raise HTTPException(404, "no scored run for this entity/period")
    return card


@router.get("/entities/{entity_id}/features")
def entity_features(entity_id: str, period: str | None = None, conn=Depends(get_reader)) -> dict:
    p, run_id = q.current_run(conn, period)
    if run_id is None:
        raise HTTPException(404, "no scored run for this period")
    row = conn.execute("SELECT features_json, support_json, peer_z_json, peer_pct_json, peer_group_id, peer_level, peer_n FROM features_entity_period WHERE run_id = ? AND entity_id = ?", [run_id, entity_id]).fetchone()
    if row is None:
        raise HTTPException(404, "entity not scored in this period")
    return {"period": p, "run_id": run_id, "features": q.loads(row[0]), "support": q.loads(row[1]), "peer_z": q.loads(row[2]), "peer_pct": q.loads(row[3]),
            "peer_group": {"id": row[4], "level": row[5], "n": row[6]}, "headline": q.headline_features(conn, entity_id, run_id)}


@router.get("/findings")
def findings(period: str | None = None, entity_id: str | None = None, module: str | None = None, decision: str | None = None, rule_id: str | None = None,
             control_id: str | None = None, min_p: float | None = None, dimension: str | None = None, status: str | None = None, sort: str = "priority",
             limit: int = Query(50, le=10_000), offset: int = 0, conn=Depends(get_reader)) -> dict:
    return q.list_findings(conn, period=period, entity_id=entity_id, module=module, decision=decision, rule_id=rule_id, control_id=control_id, min_p=min_p, dimension=dimension, status=status, sort=sort, limit=limit, offset=offset)


@router.get("/findings/{finding_id}")
def finding(finding_id: str, conn=Depends(get_reader), settings: Settings = Depends(get_settings_dep)) -> dict:
    d = q.finding_detail(conn, settings, finding_id)
    if d is None:
        raise HTTPException(404, "finding not found")
    return d


@router.get("/findings/{finding_id}/evidence")
def finding_evidence(finding_id: str, limit: int = Query(50, le=500), offset: int = 0, sort: str | None = None, conn=Depends(get_reader)) -> dict:
    return q.finding_records(conn, finding_id, limit, offset, sort)


@router.get("/alerts/{entity_id}/{period}/{alert_id}")
def alert(entity_id: str, period: str, alert_id: str, conn=Depends(get_reader)) -> dict:
    d = q.alert_with_source(conn, entity_id, period, alert_id)
    if d is None:
        raise HTTPException(404, "alert not found")
    return d


@router.get("/review/queue")
def review_queue(period: str | None = None, entity_id: str | None = None, decision: str | None = None, rule_id: str | None = None, sector: str | None = None,
                 limit: int = Query(50, le=5000), offset: int = 0, conn=Depends(get_reader)) -> dict:
    return q.review_queue(conn, period=period, entity_id=entity_id, decision=decision, rule_id=rule_id, sector=sector, limit=limit, offset=offset)


@router.get("/review/queue/{flag_id}")
def review_item(flag_id: str, conn=Depends(get_reader)) -> dict:
    d = q.queue_item(conn, flag_id)
    if d is None:
        raise HTTPException(404, "flag not found")
    return d


@router.get("/controls/priority")
def controls(period: str | None = None, sector: str | None = None, entity_id: str | None = None, conn=Depends(get_reader), settings: Settings = Depends(get_settings_dep)) -> list[dict]:
    rows = q.control_priorities(conn, settings, period, sector)
    if entity_id:
        return [r for r in rows if r["entity_id"] == entity_id]
    return rows


@router.post("/feedback", status_code=201)
def post_feedback(body: FeedbackRequest, db: Database = Depends(get_db_dep), settings: Settings = Depends(get_settings_dep)) -> dict:
    try:
        with db.write() as conn:
            return record_feedback(conn, settings, target_type=body.target_type, target_id=body.target_id, decision=body.decision, reviewer_id=body.reviewer_id, note=body.note)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/feedback/bulk", status_code=201)
def post_feedback_bulk(body: BulkFeedbackRequest, db: Database = Depends(get_db_dep), settings: Settings = Depends(get_settings_dep)) -> dict:
    out = []
    with db.write() as conn:
        for item in body.items:
            out.append(record_feedback(conn, settings, target_type=item.target_type, target_id=item.target_id, decision=item.decision, reviewer_id=item.reviewer_id, note=item.note))
    return {"recorded": len(out), "items": out}


@router.get("/feedback")
def get_feedback(target_id: str | None = None, entity_id: str | None = None, limit: int = 200, conn=Depends(get_reader)) -> list[dict]:
    if target_id:
        return history(conn, target_id)
    where, params = [], []
    if entity_id:
        where.append("entity_id = ?"); params.append(entity_id)
    sql = "SELECT feedback_id, target_type, target_id, entity_id, submission_period, rule_id, decision, reviewer_id, note, p_at_decision, created_at FROM feedback"
    if where:
        sql += " WHERE " + " AND ".join(where)
    return q.records(conn.execute(sql + " ORDER BY created_at DESC LIMIT ?", params + [limit]).df())


@router.get("/feedback/stats")
def get_feedback_stats(conn=Depends(get_reader)) -> dict:
    return feedback_stats(conn)


@router.post("/feedback/recalibrate")
def recalibrate(body: RecalibrateRequest, db: Database = Depends(get_db_dep), settings: Settings = Depends(get_settings_dep)) -> dict:
    from dataclasses import asdict

    from satsa.feedback.recalibrate import recalibrate as _recal

    res = _recal(db, settings, promote=body.promote)
    with db.write() as conn:
        from satsa.audit.audit_log import record_event

        record_event(conn, settings, run_type="RECALIBRATE", period=None, triggered_by="api", trigger_source="api", manifest=asdict(res))
    return asdict(res)
