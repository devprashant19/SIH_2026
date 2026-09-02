"""Read-side query helpers shared by the routers. All results are plain dicts shaped like
dashboard/src/api/types.ts."""

from __future__ import annotations

import json
from typing import Any

import duckdb
import pandas as pd

from satsa.config import Settings
from satsa.db.repo import fetch_df, fetch_one, latest_success_run_id
from satsa.feedback.store import latest_decisions
from satsa.features.registry import REGISTRY

DIMENSIONS = ["execution_gap", "negative_space", "escalation_discipline", "investigation_quality", "data_integrity", "trend_penalty"]


def records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return json.loads(df.to_json(orient="records", date_format="iso")) if len(df) else []


def loads(v: Any) -> Any:
    if v is None:
        return None
    return json.loads(v) if isinstance(v, str) else v


def periods(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    df = fetch_df(conn, """
        SELECT s.submission_period AS period, count(DISTINCT s.entity_id) AS n_entities, count(*) AS n_submissions,
               (SELECT run_id FROM audit_runs r WHERE r.run_type = 'PIPELINE' AND r.status = 'SUCCESS' AND r.submission_period = s.submission_period ORDER BY finished_at DESC LIMIT 1) AS latest_run_id
        FROM raw_submissions s WHERE s.superseded = FALSE GROUP BY 1 ORDER BY 1""")
    out = records(df)
    for r in out:
        r["status"] = "SUCCESS" if r["latest_run_id"] else None
    return out


def latest_period(conn: duckdb.DuckDBPyConnection) -> str | None:
    row = fetch_one(conn, "SELECT max(submission_period) FROM audit_runs WHERE run_type = 'PIPELINE' AND status = 'SUCCESS'")
    if row and row[0]:
        return row[0]
    row = fetch_one(conn, "SELECT max(submission_period) FROM raw_submissions WHERE superseded = FALSE")
    return row[0] if row else None


def resolve_period(conn: duckdb.DuckDBPyConnection, period: str | None) -> str | None:
    return period if period and period != "latest" else latest_period(conn)


def current_run(conn: duckdb.DuckDBPyConnection, period: str | None) -> tuple[str | None, str | None]:
    p = resolve_period(conn, period)
    return p, (latest_success_run_id(conn, p) if p else None)


def current_runs(conn: duckdb.DuckDBPyConnection) -> dict[str, str]:
    df = fetch_df(conn, """
        SELECT submission_period, run_id FROM (
            SELECT submission_period, run_id, row_number() OVER (PARTITION BY submission_period ORDER BY finished_at DESC) AS rn
            FROM audit_runs WHERE run_type = 'PIPELINE' AND status = 'SUCCESS') WHERE rn = 1""")
    return dict(zip(df["submission_period"], df["run_id"]))


# ---- entities / heatmap ------------------------------------------------------------------

def entities(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    return records(fetch_df(conn, "SELECT entity_id, name, sector, size_band, documented_soc_tier, documented_asset_count, peer_group_id FROM entities ORDER BY entity_id"))


def sri_history(conn: duckdb.DuckDBPyConnection, k: int = 6) -> dict[str, list[float | None]]:
    runs = current_runs(conn)
    if not runs:
        return {}
    ph = ",".join("?" * len(runs))
    df = fetch_df(conn, f"SELECT entity_id, submission_period, sri FROM sri_scores WHERE run_id IN ({ph}) ORDER BY submission_period", list(runs.values()))
    out: dict[str, list[float | None]] = {}
    for eid, grp in df.groupby("entity_id"):
        out[str(eid)] = [None if pd.isna(v) else float(v) for v in grp["sri"].tail(k)]
    return out


def heatmap(conn: duckdb.DuckDBPyConnection, period: str | None, lens: str = "sri", sector: str | None = None) -> dict[str, Any]:
    p, run_id = current_run(conn, period)
    if run_id is None:
        return {"period": p, "run_id": None, "lens": lens, "rows": []}
    df = fetch_df(conn, """
        SELECT s.entity_id, e.name, e.sector, e.size_band, s.sri, s.band, s.confidence, s.priority_rank,
               s.dim_execution_gap, s.dim_negative_space, s.dim_escalation_discipline, s.dim_investigation_quality, s.dim_data_integrity, s.dim_trend_penalty,
               s.capability_json,
               (SELECT count(*) FROM findings f WHERE f.run_id = s.run_id AND f.entity_id = s.entity_id AND f.decision <> 'AUTO_CLEAR') AS n_findings,
               (SELECT count(*) FROM findings f WHERE f.run_id = s.run_id AND f.entity_id = s.entity_id AND f.decision = 'MANUAL_REVIEW') AS n_manual_review
        FROM sri_scores s JOIN entities e ON e.entity_id = s.entity_id WHERE s.run_id = ? ORDER BY s.priority_rank""", [run_id])
    if sector:
        df = df[df["sector"] == sector]
    hist = sri_history(conn)
    rows = []
    for r in records(df):
        rows.append({
            "entity_id": r["entity_id"], "name": r["name"], "sector": r["sector"], "size_band": r["size_band"], "sri": r["sri"], "band": r["band"],
            "confidence": r["confidence"], "priority_rank": r["priority_rank"],
            "dims": {d: r.get(f"dim_{d}") for d in DIMENSIONS}, "capabilities": loads(r["capability_json"]) or {},
            "n_findings": r["n_findings"], "n_manual_review": r["n_manual_review"], "uncertain": (r["n_manual_review"] or 0) > 0,
            "trend": hist.get(r["entity_id"], []),
        })
    return {"period": p, "run_id": run_id, "lens": lens, "rows": rows}


def summary(conn: duckdb.DuckDBPyConnection, period: str | None) -> dict[str, Any]:
    p, run_id = current_run(conn, period)
    out = {"period": p, "run_id": run_id, "n_entities": 0, "n_high_risk": 0, "high_risk_delta": None, "n_open_findings": 0, "n_uncertain": 0, "n_dq_failures": 0}
    if run_id is None:
        return out
    row = fetch_one(conn, "SELECT count(*), sum(CASE WHEN band IN ('HIGH','CRITICAL') THEN 1 ELSE 0 END) FROM sri_scores WHERE run_id = ?", [run_id])
    out["n_entities"], out["n_high_risk"] = int(row[0]), int(row[1] or 0)
    fnd = fetch_df(conn, "SELECT finding_id, decision, rule_id FROM findings WHERE run_id = ?", [run_id])
    decided = latest_decisions(conn, list(fnd["finding_id"])) if len(fnd) else {}
    open_mask = (fnd["decision"] != "AUTO_CLEAR") & ~fnd["finding_id"].map(lambda i: decided.get(i) in ("ACCEPT", "REJECT"))
    out["n_open_findings"] = int(open_mask.sum())
    out["n_uncertain"] = int((fnd["decision"] == "MANUAL_REVIEW").sum())
    out["n_dq_failures"] = int(fetch_one(conn, "SELECT count(*) FROM raw_submissions WHERE submission_period = ? AND superseded = FALSE AND fatal", [p])[0]) + int((fnd["rule_id"] == "NS-06").sum())
    prev = fetch_one(conn, "SELECT max(submission_period) FROM sri_scores WHERE submission_period < ?", [p])
    if prev and prev[0]:
        prev_run = latest_success_run_id(conn, prev[0])
        if prev_run:
            hr = fetch_one(conn, "SELECT sum(CASE WHEN band IN ('HIGH','CRITICAL') THEN 1 ELSE 0 END) FROM sri_scores WHERE run_id = ?", [prev_run])
            out["high_risk_delta"] = out["n_high_risk"] - int(hr[0] or 0)
    return out


def sri_scorecard(conn: duckdb.DuckDBPyConnection, settings: Settings, entity_id: str, period: str | None) -> dict[str, Any] | None:
    p, run_id = current_run(conn, period)
    if run_id is None:
        return None
    row = fetch_one(conn, "SELECT sri, band, confidence, weights_hash, components_json, sri_delta_prev FROM sri_scores WHERE run_id = ? AND entity_id = ?", [run_id, entity_id])
    if row is None:
        return None
    comps = loads(row[4]) or []
    dims_cfg = settings.sri_dimensions()
    dims = []
    for name, cfg in dims_cfg.items():
        subs = [c for c in comps if c["dimension"] == name]
        score = sum((c["score"] or 0) * c["effective_weight"] for c in subs) if cfg.get("subs") else (subs[0]["score"] if subs else 0.0)
        dims.append({
            "name": name, "label": cfg.get("label", name), "weight": float(cfg["weight"]), "score": score, "contribution": float(cfg["weight"]) * score,
            "capabilities": cfg.get("capabilities") or [],
            "subs": [{"name": c["sub"], "raw": c["raw"], "percentile": c["percentile"], "higher_is_worse": c["higher_is_worse"], "weight": c["weight"], "effective_weight": c["effective_weight"], "contribution": (c["score"] or 0) * c["effective_weight"] * float(cfg["weight"]), "support": c["support"], "peer_median": c["peer_median"]} for c in subs],
        })
    return {"entity_id": entity_id, "period": p, "run_id": run_id, "sri": row[0], "band": row[1], "confidence": row[2], "weights_hash": row[3], "config_hash": settings.config_hash, "sri_delta_prev": row[5], "dimensions": dims}


def headline_features(conn: duckdb.DuckDBPyConnection, entity_id: str, run_id: str) -> list[dict[str, Any]]:
    row = fetch_one(conn, "SELECT features_json, support_json, peer_z_json, peer_pct_json, peer_group_id FROM features_entity_period WHERE run_id = ? AND entity_id = ?", [run_id, entity_id])
    if row is None:
        return []
    feats, support, z, pct = loads(row[0]) or {}, loads(row[1]) or {}, loads(row[2]) or {}, loads(row[3]) or {}
    base = fetch_df(conn, "SELECT feature, median, p10, p90 FROM peer_baselines WHERE run_id = ? AND peer_group_id = ?", [run_id, row[4]])
    stats = {r.feature: r for r in base.itertuples()}
    out = []
    for name, meta in REGISTRY.items():
        if not meta.headline:
            continue
        b = stats.get(name)
        out.append({"name": name, "label": meta.label, "value": feats.get(name), "peer_median": b.median if b else None, "p10": b.p10 if b else None, "p90": b.p90 if b else None,
                    "z": z.get(name), "percentile": pct.get(name), "support": (support.get(name) or {}).get("flag", "MISSING"), "higher_is_worse": meta.higher_is_worse, "unit": meta.unit, "group": meta.group})
    return out


def data_quality(conn: duckdb.DuckDBPyConnection, entity_id: str, period: str) -> dict[str, Any] | None:
    df = fetch_df(conn, "SELECT row_count, validation_json, fatal FROM raw_submissions WHERE entity_id = ? AND submission_period = ? AND superseded = FALSE", [entity_id, period])
    if df.empty:
        return None
    rows, err, warn, fatal = 0, 0, 0, False
    for r in df.itertuples():
        v = loads(r.validation_json) or {}
        rows += int(v.get("n_rows", 0))
        lc = v.get("level_counts") or {}
        err += int(lc.get("ERROR", 0))
        warn += int(lc.get("WARN", 0))
        fatal = fatal or bool(r.fatal)
    return {"rows": rows, "val_err_rate": (err / rows) if rows else 0.0, "val_warn_rate": (warn / rows) if rows else 0.0, "fatal": fatal}


# ---- findings ---------------------------------------------------------------------------

FINDING_LIST_COLS = "f.finding_id, f.entity_id, e.name AS entity_name, f.submission_period AS period, f.module, f.finding_class, f.source, f.rule_id, f.control_id, f.capability, f.title, f.severity, f.p_final, f.decision, f.priority_rank"


def dimension_for(finding: dict[str, Any]) -> str:
    if finding.get("finding_class") == "negative_space":
        return "negative_space"
    rid = finding.get("rule_id") or ""
    if rid in ("EG-03", "EG-11"):
        return "escalation_discipline"
    if rid in ("EG-05", "EG-06", "EG-08"):
        return "investigation_quality"
    return "execution_gap"


def list_findings(conn: duckdb.DuckDBPyConnection, *, period: str | None, run_ids: list[str] | None = None, entity_id: str | None = None, module: str | None = None,
                  decision: str | None = None, rule_id: str | None = None, control_id: str | None = None, min_p: float | None = None, dimension: str | None = None,
                  status: str | None = None, sort: str = "priority", limit: int = 50, offset: int = 0) -> dict[str, Any]:
    if run_ids is None:
        p, run_id = current_run(conn, period)
        run_ids = [run_id] if run_id else []
    if not run_ids:
        return {"total": 0, "items": [], "limit": limit, "offset": offset}
    where, params = [f"f.run_id IN ({','.join('?' * len(run_ids))})"], list(run_ids)
    if entity_id:
        where.append("f.entity_id = ?"); params.append(entity_id)
    if module:
        where.append("f.module = ?"); params.append(module)
    if decision:
        where.append("f.decision = ?"); params.append(decision)
    if rule_id:
        where.append("f.rule_id = ?"); params.append(rule_id)
    if control_id:
        where.append("f.control_id = ?"); params.append(control_id)
    if min_p is not None:
        where.append("f.p_final >= ?"); params.append(min_p)
    order = {"priority": "f.priority_rank", "p": "f.p_final DESC", "entity": "f.entity_id, f.priority_rank", "recent": "f.created_at DESC"}.get(sort, "f.priority_rank")
    df = fetch_df(conn, f"SELECT {FINDING_LIST_COLS} FROM findings f JOIN entities e ON e.entity_id = f.entity_id WHERE {' AND '.join(where)} ORDER BY {order}", params)
    items = records(df)
    decided = latest_decisions(conn, [i["finding_id"] for i in items])
    for i in items:
        i["feedback_status"] = decided.get(i["finding_id"])
        i["dimension"] = dimension_for(i)
    if dimension:
        items = [i for i in items if i["dimension"] == dimension]
    if status == "open":
        items = [i for i in items if i["decision"] != "AUTO_CLEAR" and i["feedback_status"] not in ("ACCEPT", "REJECT")]
    elif status == "reviewed":
        items = [i for i in items if i["feedback_status"] in ("ACCEPT", "REJECT")]
    elif status == "uncertain":
        items = [i for i in items if i["decision"] == "MANUAL_REVIEW"]
    total = len(items)
    return {"total": total, "items": items[offset: offset + limit], "limit": limit, "offset": offset}


def finding_detail(conn: duckdb.DuckDBPyConnection, settings: Settings, finding_id: str) -> dict[str, Any] | None:
    df = fetch_df(conn, "SELECT f.*, e.name AS entity_name FROM findings f JOIN entities e ON e.entity_id = f.entity_id WHERE f.finding_id = ?", [finding_id])
    if df.empty:
        return None
    r = records(df)[0]
    evidence = loads(r.pop("evidence_json")) or {}
    shap = loads(r.pop("shap_json"))
    comps = loads(r.pop("score_components_json")) or {}
    snapshot = evidence.get("feature_snapshot") or {}
    from satsa.analytics.rules.catalogue import rule_index
    from satsa.analytics.rules.templates import TEMPLATES
    from satsa.feedback.store import history

    rule = None
    if r["rule_id"]:
        info = rule_index(settings).get(r["rule_id"], {})
        rule = {"rule_id": r["rule_id"], "version": r["rule_version"], "name": info.get("name", r["rule_id"]), "template": TEMPLATES.get(r["rule_id"], ""), "params": info.get("params", {}), "evaluated": {k: v for k, v in (evidence.get("rule") or {}).items() if k not in ("groups", "distribution", "validation", "classes", "peer_class_rates", "dropped_assets")}}
    what = None
    if r["rationale"] and "The strongest contributors are" in r["rationale"]:
        what = r["rationale"].split("The strongest contributors are", 1)[1].strip()
        what = "The strongest contributors are " + what
    return {
        **{k: r[k] for k in ("finding_id", "entity_id", "entity_name", "module", "finding_class", "source", "rule_id", "rule_version", "control_id", "capability", "scope", "asset_id", "title", "severity", "p_rule", "p_ml", "p_final", "calibrated", "decision", "t_star", "band_low", "band_high", "expected_cost", "priority_rank", "rationale", "n_evidence_alerts", "created_at")},
        "period": r["submission_period"], "dimension": dimension_for(r), "what_would_change": what, "score_components": comps,
        "evidence_features": [{"name": k, "label": v.get("label", REGISTRY[k].label if k in REGISTRY else k), "value": v.get("value"), "peer_median": v.get("peer_median"), "p10": v.get("p10"), "p90": v.get("p90"), "z": v.get("z"), "percentile": v.get("pct"), "higher_is_worse": v.get("higher_is_worse", REGISTRY[k].higher_is_worse if k in REGISTRY else True)} for k, v in snapshot.items()],
        "shap": None if not shap else {"method": shap.get("method"), "base_value": shap.get("base_value"), "output": shap.get("output"), "contributions": shap.get("contributions", [])},
        "rule": rule, "evidence_alert_ids": evidence.get("alert_ids") or [], "evidence_asset_ids": evidence.get("asset_ids") or [], "rule_evidence": evidence.get("rule") or {},
        "feedback": history(conn, finding_id), "feedback_status": (latest_decisions(conn, [finding_id]) or {}).get(finding_id),
    }


ALERT_COLS = "alert_id, entity_id, submission_period, submission_id, raw_row_index, ts, severity, category, asset_id, source_system, analyst_id, analyst_action, acknowledged_at, investigated_at, closed_at, time_to_close_min, escalation_flag, escalated_at, closure_reason, investigation_notes, root_cause_flag, remediation_ticket_id, rule_name, validation_flags"


def finding_records(conn: duckdb.DuckDBPyConnection, finding_id: str, limit: int, offset: int, sort: str | None = None) -> dict[str, Any]:
    row = fetch_one(conn, "SELECT entity_id, submission_period, evidence_json FROM findings WHERE finding_id = ?", [finding_id])
    if row is None:
        return {"total": 0, "items": [], "limit": limit, "offset": offset}
    ids = (loads(row[2]) or {}).get("alert_ids") or []
    if not ids:
        return {"total": 0, "items": [], "limit": limit, "offset": offset}
    order = {"ttc": "time_to_close_min", "ts": "ts", "severity": "severity"}.get(sort or "", "ts")
    ph = ",".join("?" * len(ids))
    df = fetch_df(conn, f"SELECT {ALERT_COLS} FROM alerts WHERE entity_id = ? AND submission_period = ? AND alert_id IN ({ph}) ORDER BY {order} LIMIT ? OFFSET ?", [row[0], row[1], *ids, limit, offset])
    return {"total": len(ids), "items": _alert_rows(df), "limit": limit, "offset": offset}


def _alert_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    out = records(df)
    for r in out:
        r["validation_flags"] = list(r.get("validation_flags") or [])
        r["escalation_flag"] = bool(r.get("escalation_flag"))
    return out


def alert_with_source(conn: duckdb.DuckDBPyConnection, entity_id: str, period: str, alert_id: str) -> dict[str, Any] | None:
    df = fetch_df(conn, f"SELECT {ALERT_COLS} FROM alerts WHERE entity_id = ? AND submission_period = ? AND alert_id = ?", [entity_id, period, alert_id])
    if df.empty:
        return None
    alert = _alert_rows(df)[0]
    sub = fetch_one(conn, "SELECT file_name, file_hash, file_path, source_format FROM raw_submissions WHERE submission_id = ?", [alert["submission_id"]]) if alert.get("submission_id") else None
    raw_line = _raw_line(sub, alert) if sub else None
    flags = records(fetch_df(conn, "SELECT flag_id, rule_ids, p_alert, decision FROM alert_sample_flags WHERE entity_id = ? AND submission_period = ? AND alert_id = ? ORDER BY created_at DESC", [entity_id, period, alert_id]))
    for f in flags:
        f["rule_ids"] = list(f.get("rule_ids") or [])
    return {"alert": alert, "raw_line": raw_line, "submission": {"file_name": sub[0], "file_hash": sub[1]} if sub else None, "flags": flags}


def _raw_line(sub: tuple, alert: dict[str, Any]) -> str | None:
    from pathlib import Path

    path = Path(sub[2]) if sub[2] else None
    if path is None or not path.exists():
        return None
    try:
        if sub[3] == "csv":
            idx = alert.get("raw_row_index")
            with path.open("r", encoding="utf-8-sig", errors="replace") as fh:
                header = fh.readline().rstrip("\n")
                for i, line in enumerate(fh):
                    if i == idx:
                        return header + "\n" + line.rstrip("\n")
        elif sub[3] == "json":
            doc = json.loads(path.read_text(encoding="utf-8-sig"))
            rows = doc.get("alerts", doc) if isinstance(doc, dict) else doc
            for rec in rows:
                if str(rec.get("alert_id")) == alert["alert_id"]:
                    return json.dumps(rec, indent=1)
        elif sub[3] == "sqlite":
            import sqlite3

            with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as c:
                c.row_factory = sqlite3.Row
                row = c.execute("SELECT * FROM alerts WHERE alert_id = ?", [alert["alert_id"]]).fetchone()
                return json.dumps(dict(row), indent=1, default=str) if row else None
    except Exception:  # pragma: no cover - best effort
        return None
    return None


# ---- review queue -----------------------------------------------------------------------

def review_queue(conn: duckdb.DuckDBPyConnection, *, period: str | None, entity_id: str | None = None, decision: str | None = None, rule_id: str | None = None,
                 sector: str | None = None, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    p, run_id = current_run(conn, period)
    if run_id is None:
        return {"total": 0, "items": [], "limit": limit, "offset": offset}
    where, params = ["q.run_id = ?", "q.queue_rank IS NOT NULL"], [run_id]
    if entity_id:
        where.append("q.entity_id = ?"); params.append(entity_id)
    if decision:
        where.append("q.decision = ?"); params.append(decision)
    if rule_id:
        where.append("list_contains(q.rule_ids, ?)"); params.append(rule_id)
    if sector:
        where.append("e.sector = ?"); params.append(sector)
    df = fetch_df(conn, f"""
        SELECT q.flag_id, q.entity_id, e.name AS entity_name, q.submission_period AS period, q.alert_id, q.rule_ids, q.flag_source, q.p_alert, q.decision, q.queue_rank, q.queue_reason, q.rationale,
               a.severity, a.category, a.asset_id, a.time_to_close_min, a.analyst_action, a.closure_reason, left(coalesce(a.investigation_notes, ''), 140) AS notes_excerpt
        FROM alert_sample_flags q JOIN entities e ON e.entity_id = q.entity_id
        LEFT JOIN alerts a ON a.entity_id = q.entity_id AND a.submission_period = q.submission_period AND a.alert_id = q.alert_id
        WHERE {' AND '.join(where)} ORDER BY q.entity_id, q.queue_rank""", params)
    items = records(df)
    decided = latest_decisions(conn, [i["flag_id"] for i in items])
    out = []
    for i in items:
        out.append({**{k: i[k] for k in ("flag_id", "entity_id", "entity_name", "period", "alert_id", "flag_source", "p_alert", "decision", "queue_rank", "queue_reason", "rationale")},
                    "rule_ids": list(i.get("rule_ids") or []), "feedback_status": decided.get(i["flag_id"]),
                    "alert": {"severity": i["severity"], "category": i["category"], "asset_id": i["asset_id"], "time_to_close_min": i["time_to_close_min"], "analyst_action": i["analyst_action"], "closure_reason": i["closure_reason"], "notes_excerpt": i["notes_excerpt"] or None}})
    return {"total": len(out), "items": out[offset: offset + limit], "limit": limit, "offset": offset}


def queue_item(conn: duckdb.DuckDBPyConnection, flag_id: str) -> dict[str, Any] | None:
    row = fetch_one(conn, "SELECT entity_id, submission_period, alert_id, evidence_json, rationale, rule_ids, p_alert, decision, queue_rank, queue_reason, flag_source FROM alert_sample_flags WHERE flag_id = ?", [flag_id])
    if row is None:
        return None
    alert = alert_with_source(conn, row[0], row[1], row[2])
    ev = loads(row[3]) or {}
    related = []
    eg05 = (ev.get("details") or {}).get("EG-05")
    if eg05 and eg05.get("note"):
        related = _alert_rows(fetch_df(conn, "SELECT " + ALERT_COLS + " FROM alerts WHERE entity_id = ? AND submission_period = ? AND alert_id <> ? AND investigation_notes = (SELECT investigation_notes FROM alerts WHERE entity_id = ? AND submission_period = ? AND alert_id = ?) LIMIT 5", [row[0], row[1], row[2], row[0], row[1], row[2]]))
    from satsa.feedback.store import history

    return {"flag": {"flag_id": flag_id, "entity_id": row[0], "period": row[1], "alert_id": row[2], "rationale": row[4], "rule_ids": list(row[5] or []), "p_alert": row[6], "decision": row[7], "queue_rank": row[8], "queue_reason": row[9], "flag_source": row[10], "evidence": ev},
            "alert": alert, "related_alerts": related, "feedback": history(conn, flag_id)}


def control_priorities(conn: duckdb.DuckDBPyConnection, settings: Settings, period: str | None, sector: str | None = None) -> list[dict[str, Any]]:
    from satsa.analytics.module_d_prioritise import control_priorities as cp

    p, run_id = current_run(conn, period)
    if run_id is None:
        return []
    df = fetch_df(conn, "SELECT f.entity_id, f.rule_id, f.control_id, f.expected_cost FROM findings f JOIN entities e ON e.entity_id = f.entity_id WHERE f.run_id = ? AND f.rule_id IS NOT NULL AND f.decision <> 'AUTO_CLEAR'" + (" AND e.sector = ?" if sector else ""), [run_id] + ([sector] if sector else []))
    return cp(records(df), settings)


# ---- benchmark / coverage / trends ------------------------------------------------------

def benchmark(conn: duckdb.DuckDBPyConnection, feature: str, period: str | None, entity_id: str | None = None, peer_group: str | None = None) -> dict[str, Any] | None:
    p, run_id = current_run(conn, period)
    if run_id is None or feature not in REGISTRY:
        return None
    df = fetch_df(conn, "SELECT f.entity_id, e.name, f.features_json, f.peer_z_json, f.peer_pct_json, f.peer_group_id, f.peer_level FROM features_entity_period f JOIN entities e ON e.entity_id = f.entity_id WHERE f.run_id = ?", [run_id])
    if df.empty:
        return None
    group = peer_group
    if group is None and entity_id:
        me = df[df["entity_id"] == entity_id]
        group = me["peer_group_id"].iloc[0] if len(me) else None
    if group:
        df = df[df["peer_group_id"] == group]
    level = int(df["peer_level"].iloc[0]) if len(df) else 1
    ents, entity_value = [], None
    for r in df.itertuples():
        feats, z, pct = loads(r.features_json) or {}, loads(r.peer_z_json) or {}, loads(r.peer_pct_json) or {}
        v = feats.get(feature)
        ents.append({"entity_id": r.entity_id, "name": r.name, "value": v, "z": z.get(feature), "percentile": pct.get(feature)})
        if r.entity_id == entity_id:
            entity_value = v
    stats = fetch_one(conn, "SELECT n, median, mad, p10, p90 FROM peer_baselines WHERE run_id = ? AND feature = ? AND peer_group_id = ?", [run_id, feature, group or ""])
    meta = REGISTRY[feature]
    return {"feature": feature, "label": meta.label, "unit": meta.unit, "higher_is_worse": meta.higher_is_worse, "period": p, "peer_group_id": group or "global", "peer_level": level,
            "stats": {"n": stats[0] if stats else len(ents), "median": stats[1] if stats else None, "mad": stats[2] if stats else None, "p10": stats[3] if stats else None, "p90": stats[4] if stats else None},
            "entities": sorted(ents, key=lambda x: (x["value"] is None, x["value"])), "entity_value": entity_value}


def benchmark_rank(conn: duckdb.DuckDBPyConnection, period: str | None, sector: str | None = None, features: list[str] | None = None) -> dict[str, Any]:
    p, run_id = current_run(conn, period)
    feats = features or ["escalation_ratio_critical", "critical_closed_no_escalation_rate", "ttc_median_critical", "fast_close_rate_critical", "note_template_score", "closure_reason_entropy", "silent_asset_rate_tier1_hist", "coverage_gap_score_tier1"]
    if run_id is None:
        return {"period": p, "features": feats, "rows": []}
    df = fetch_df(conn, "SELECT f.entity_id, e.name, e.sector, f.features_json, f.peer_pct_json, s.sri, s.band FROM features_entity_period f JOIN entities e ON e.entity_id = f.entity_id LEFT JOIN sri_scores s ON s.run_id = f.run_id AND s.entity_id = f.entity_id WHERE f.run_id = ?" + (" AND e.sector = ?" if sector else ""), [run_id] + ([sector] if sector else []))
    rows = []
    for r in df.itertuples():
        feats_v, pct = loads(r.features_json) or {}, loads(r.peer_pct_json) or {}
        rows.append({"entity_id": r.entity_id, "name": r.name, "sector": r.sector, "sri": r.sri, "band": r.band, "values": {k: feats_v.get(k) for k in feats}, "percentiles": {k: pct.get(k) for k in feats}})
    return {"period": p, "features": [{"key": k, "label": REGISTRY[k].label, "higher_is_worse": REGISTRY[k].higher_is_worse} for k in feats if k in REGISTRY], "rows": sorted(rows, key=lambda x: -(x["sri"] or 0))}


def coverage_matrix(conn: duckdb.DuckDBPyConnection, settings: Settings, period: str | None, dimension: str = "category", sector: str | None = None) -> dict[str, Any]:
    p, run_id = current_run(conn, period)
    ents = fetch_df(conn, "SELECT entity_id, name, sector FROM entities" + (" WHERE sector = ?" if sector else "") + " ORDER BY entity_id", [sector] if sector else [])
    if p is None or ents.empty:
        return {"period": p, "dimension": dimension, "columns": [], "rows": []}
    findings = fetch_df(conn, "SELECT finding_id, entity_id, rule_id FROM findings WHERE run_id = ? AND rule_id IN ('NS-01','NS-02','NS-03','NS-07')", [run_id]) if run_id else pd.DataFrame(columns=["finding_id", "entity_id", "rule_id"])
    cfg = settings.expected_categories
    if dimension == "category":
        counts = fetch_df(conn, "SELECT entity_id, category AS col, count(*) AS n FROM alerts WHERE submission_period = ? GROUP BY 1, 2", [p])
        columns = sorted({c for lst in (cfg.get("by_sector") or {}).values() for c in lst} | set(counts["col"].astype(str)))
        classes = fetch_df(conn, "SELECT entity_id, asset_class FROM assets")
        def expected_for(eid: str, sec: str) -> set[str]:
            exp = set((cfg.get("by_sector") or {}).get(sec, []))
            for cls in classes[classes["entity_id"] == eid]["asset_class"].astype(str):
                exp |= set((cfg.get("by_asset_class") or {}).get(cls, []))
            return exp
        rule = "NS-03"
    elif dimension == "asset_class":
        counts = fetch_df(conn, "SELECT a.entity_id, s.asset_class AS col, count(*) * 1.0 / nullif((SELECT count(*) FROM assets x WHERE x.entity_id = a.entity_id AND x.asset_class = s.asset_class), 0) AS n FROM alerts a JOIN assets s ON s.entity_id = a.entity_id AND s.asset_id = a.asset_id WHERE a.submission_period = ? GROUP BY 1, 2", [p])
        columns = sorted(set(fetch_df(conn, "SELECT DISTINCT asset_class FROM assets")["asset_class"].astype(str)))
        classes = fetch_df(conn, "SELECT entity_id, asset_class FROM assets")
        def expected_for(eid: str, sec: str) -> set[str]:
            return set(classes[classes["entity_id"] == eid]["asset_class"].astype(str))
        rule = "NS-07"
    else:
        counts = fetch_df(conn, "SELECT entity_id, source_system AS col, count(*) AS n FROM alerts WHERE submission_period = ? AND source_system IS NOT NULL GROUP BY 1, 2", [p])
        srcs = fetch_df(conn, "SELECT entity_id, unnest(expected_telemetry_sources) AS src FROM assets")
        columns = sorted(set(srcs["src"].astype(str)) | set(counts["col"].astype(str)))
        def expected_for(eid: str, sec: str) -> set[str]:
            return set(srcs[srcs["entity_id"] == eid]["src"].astype(str))
        rule = "NS-02"
    pivot = counts.pivot_table(index="entity_id", columns="col", values="n", aggfunc="sum").reindex(columns=columns) if len(counts) else pd.DataFrame(columns=columns)
    p10 = {c: float(pivot[c].dropna().quantile(0.10)) if c in pivot and pivot[c].notna().sum() >= 3 else None for c in columns}
    med = {c: float(pivot[c].dropna().median()) if c in pivot and pivot[c].notna().sum() >= 1 else None for c in columns}
    rows = []
    for e in ents.itertuples():
        exp = expected_for(str(e.entity_id), str(e.sector))
        fid = findings[(findings["entity_id"] == e.entity_id) & (findings["rule_id"] == rule)]["finding_id"]
        cells = []
        for c in columns:
            n = float(pivot.loc[e.entity_id, c]) if e.entity_id in pivot.index and c in pivot and not pd.isna(pivot.loc[e.entity_id, c]) else 0.0
            if n > 0:
                status = "low" if p10.get(c) is not None and n < p10[c] else "present"
            else:
                status = "absent" if c in exp else "na"
            cells.append({"status": status, "count": n if n > 0 or c in exp else None, "peer_median": med.get(c), "finding_id": fid.iloc[0] if status in ("absent", "low") and len(fid) else None})
        rows.append({"entity_id": e.entity_id, "name": e.name, "sector": e.sector, "cells": cells})
    return {"period": p, "dimension": dimension, "columns": columns, "rows": rows}


def coverage_cell(conn: duckdb.DuckDBPyConnection, settings: Settings, entity_id: str, column: str, period: str | None, dimension: str = "category") -> dict[str, Any]:
    matrix = coverage_matrix(conn, settings, period, dimension)
    if column not in matrix["columns"]:
        return {"entity_id": entity_id, "column": column, "status": "na", "observed": 0, "expected_reason": "not expected", "peer_share_reporting": None, "peer_median": None, "finding_id": None}
    ci = matrix["columns"].index(column)
    row = next((r for r in matrix["rows"] if r["entity_id"] == entity_id), None)
    cell = row["cells"][ci] if row else {"status": "na", "count": 0, "peer_median": None, "finding_id": None}
    reporting = sum(1 for r in matrix["rows"] if r["cells"][ci]["status"] in ("present", "low"))
    total = len(matrix["rows"]) or 1
    sec = row["sector"] if row else None
    cfg = settings.expected_categories
    reasons = []
    if dimension == "category":
        if column in (cfg.get("by_sector") or {}).get(sec or "", []):
            reasons.append(f"expected for the {sec} sector")
        # Only name the asset classes this entity actually declares, not every class in the catalogue.
        own = set(fetch_df(conn, "SELECT DISTINCT asset_class FROM assets WHERE entity_id = ?", [entity_id])["asset_class"].astype(str))
        cls = [c for c, lst in (cfg.get("by_asset_class") or {}).items() if column in lst and c in own]
        if cls:
            reasons.append(f"expected because this entity declares {', '.join(sorted(cls)[:3])} assets")
    reasons.append(f"reported by {reporting} of {total} peers this period")
    return {"entity_id": entity_id, "column": column, "status": cell["status"], "observed": cell.get("count") or 0, "expected_reason": "; ".join(reasons), "peer_share_reporting": reporting / total, "peer_median": cell.get("peer_median"), "finding_id": cell.get("finding_id")}


def trend_entity(conn: duckdb.DuckDBPyConnection, entity_id: str, start: str | None = None, end: str | None = None) -> dict[str, Any]:
    runs = current_runs(conn)
    runs = {p: r for p, r in runs.items() if (not start or p >= start) and (not end or p <= end)}
    if not runs:
        return {"periods": [], "sri": [], "dims": {d: [] for d in DIMENSIONS}, "features": {}, "findings_count": {"A": [], "B": []}}
    ph = ",".join("?" * len(runs))
    s = fetch_df(conn, f"SELECT submission_period, sri, dim_execution_gap, dim_negative_space, dim_escalation_discipline, dim_investigation_quality, dim_data_integrity, dim_trend_penalty FROM sri_scores WHERE entity_id = ? AND run_id IN ({ph}) ORDER BY submission_period", [entity_id, *runs.values()])
    f = fetch_df(conn, f"SELECT submission_period, features_json FROM features_entity_period WHERE entity_id = ? AND run_id IN ({ph}) ORDER BY submission_period", [entity_id, *runs.values()])
    t = fetch_df(conn, f"SELECT submission_period, n_findings_a, n_findings_b FROM trend_entity WHERE entity_id = ? AND run_id IN ({ph}) ORDER BY submission_period", [entity_id, *runs.values()])
    periods_ = list(s["submission_period"])
    feats: dict[str, list] = {}
    for r in f.itertuples():
        fj = loads(r.features_json) or {}
        for name, meta in REGISTRY.items():
            if meta.headline:
                feats.setdefault(name, []).append(fj.get(name))
    return {"periods": periods_, "sri": [None if pd.isna(v) else float(v) for v in s["sri"]],
            "dims": {d: [None if pd.isna(v) else float(v) for v in s[f"dim_{d}"]] for d in DIMENSIONS}, "features": feats,
            "findings_count": {"A": [int(v) for v in t["n_findings_a"]], "B": [int(v) for v in t["n_findings_b"]]}}


def trend_sector(conn: duckdb.DuckDBPyConnection, sector: str | None = None, start: str | None = None, end: str | None = None) -> dict[str, Any]:
    runs = {p: r for p, r in current_runs(conn).items() if (not start or p >= start) and (not end or p <= end)}
    if not runs:
        return {"periods": [], "median_sri": [], "p25": [], "p75": [], "entities": {}}
    ph = ",".join("?" * len(runs))
    df = fetch_df(conn, f"SELECT s.submission_period, s.entity_id, s.sri FROM sri_scores s JOIN entities e ON e.entity_id = s.entity_id WHERE s.run_id IN ({ph})" + (" AND e.sector = ?" if sector else "") + " ORDER BY 1, 2", [*runs.values()] + ([sector] if sector else []))
    periods_ = sorted(df["submission_period"].unique())
    g = df.groupby("submission_period")["sri"]
    ents = {eid: [None if p not in grp.set_index("submission_period")["sri"] else float(grp.set_index("submission_period")["sri"][p]) for p in periods_] for eid, grp in df.groupby("entity_id")}
    return {"periods": periods_, "median_sri": [float(g.median()[p]) for p in periods_], "p25": [float(g.quantile(0.25)[p]) for p in periods_], "p75": [float(g.quantile(0.75)[p]) for p in periods_], "entities": ents}


def trend_controls(conn: duckdb.DuckDBPyConnection, settings: Settings, start: str | None = None, end: str | None = None) -> dict[str, Any]:
    runs = {p: r for p, r in current_runs(conn).items() if (not start or p >= start) and (not end or p <= end)}
    if not runs:
        return {"periods": [], "controls": []}
    ph = ",".join("?" * len(runs))
    df = fetch_df(conn, f"SELECT submission_period, control_id, sum(expected_cost) AS priority, count(*) AS n FROM findings WHERE run_id IN ({ph}) AND rule_id IS NOT NULL AND decision <> 'AUTO_CLEAR' GROUP BY 1, 2", list(runs.values()))
    periods_ = sorted(runs)
    labels = settings.rules.get("controls") or {}
    out = []
    for cid, grp in df.groupby("control_id"):
        by = grp.set_index("submission_period")
        out.append({"control_id": cid, "label": labels.get(cid, cid), "series": [float(by["priority"].get(p, 0.0)) for p in periods_], "n_findings": [int(by["n"].get(p, 0)) for p in periods_]})
    return {"periods": periods_, "controls": sorted(out, key=lambda c: -sum(c["series"]))}


# ---- submissions / runs / audit / models ------------------------------------------------

def submissions(conn: duckdb.DuckDBPyConnection, period: str | None = None, entity_id: str | None = None) -> list[dict[str, Any]]:
    where, params = ["superseded = FALSE"], []
    if period and period != "latest":
        where.append("submission_period = ?"); params.append(period)
    if entity_id:
        where.append("entity_id = ?"); params.append(entity_id)
    df = fetch_df(conn, f"SELECT submission_id, entity_id, submission_period, source_format, file_name, file_hash, received_at, row_count, accepted_rows, rejected_rows, fatal, superseded, validation_json FROM raw_submissions WHERE {' AND '.join(where)} ORDER BY submission_period DESC, entity_id", params)
    out = records(df)
    for r in out:
        v = loads(r.pop("validation_json")) or None
        r["validation"] = None if v is None else {"fatal": v.get("fatal", False), "n_rows": v.get("n_rows", 0), "n_accepted": v.get("n_accepted", 0), "n_rejected": v.get("n_rejected", 0), "counts": v.get("counts", {}), "samples": v.get("samples", {}), "unmapped_columns": v.get("unmapped_columns", []), "messages": v.get("messages", []), "level_counts": v.get("level_counts", {})}
    return out


def runs(conn: duckdb.DuckDBPyConnection, run_type: str | None = None, period: str | None = None, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    where, params = [], []
    if run_type:
        where.append("run_type = ?"); params.append(run_type)
    if period and period != "latest":
        where.append("submission_period = ?"); params.append(period)
    sql = "SELECT run_id, run_type, submission_period, triggered_by, trigger_source, started_at, finished_at, status, app_version, code_hash, rules_version, feature_version, config_hash, model_versions_json, input_hash, output_hash, run_hash, prev_run_hash, error_text, stage_log_json FROM audit_runs"
    if where:
        sql += " WHERE " + " AND ".join(where)
    df = fetch_df(conn, sql + " ORDER BY started_at DESC LIMIT ? OFFSET ?", params + [limit, offset])
    return [_run_row(r) for r in records(df)]


def _run_row(r: dict[str, Any]) -> dict[str, Any]:
    stages = loads(r.pop("stage_log_json")) or []
    return {**r, "model_versions": loads(r.pop("model_versions_json")) or {}, "stages": [{"stage": s.get("stage"), "status": s.get("status"), "rows": s.get("rows"), "seconds": s.get("seconds"), "error": s.get("error"), **{k: v for k, v in s.items() if k not in ("stage", "status", "rows", "seconds", "error", "trace")}} for s in stages]}


def run_detail(conn: duckdb.DuckDBPyConnection, run_id: str) -> dict[str, Any] | None:
    df = fetch_df(conn, "SELECT * FROM audit_runs WHERE run_id = ?", [run_id])
    if df.empty:
        return None
    r = records(df)[0]
    out = _run_row({k: v for k, v in r.items() if k not in ("config_snapshot_json", "input_manifest_json", "output_manifest_json")})
    out["config_snapshot"] = loads(r["config_snapshot_json"])
    out["input_manifest"] = loads(r["input_manifest_json"])
    out["output_manifest"] = loads(r["output_manifest_json"])
    return out


def models(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    df = fetch_df(conn, "SELECT model_name, version, is_active, trained_at, training_periods, training_rows, feature_list_hash, metrics_json, hyperparams_json, parent_version, artifact_hash, library_versions_json, trained_on_feedback_count FROM model_registry ORDER BY model_name, trained_at DESC")
    out = []
    for r in records(df):
        out.append({**{k: r[k] for k in ("model_name", "version", "is_active", "trained_at", "training_rows", "feature_list_hash", "parent_version", "artifact_hash", "trained_on_feedback_count")},
                    "training_periods": list(r.get("training_periods") or []), "metrics": loads(r["metrics_json"]) or {}, "hyperparams": loads(r["hyperparams_json"]) or {}, "library_versions": loads(r["library_versions_json"]) or {}})
    return out
