"""Persist supervisor edits to the YAML configuration and answer what-if questions."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb
import yaml

from satsa.api.schemas import ConfigUpdate, WhatIfRequest
from satsa.audit.audit_log import record_event
from satsa.config import CONFIG_FILES, Settings, load_settings, reset_settings_cache
from satsa.db.repo import fetch_df, fetch_one, to_json


def effective_config(settings: Settings) -> dict[str, Any]:
    from satsa.analytics.rules.catalogue import rule_index
    from satsa.version import RULES_VERSION

    return {
        "config_hash": settings.config_hash, "weights_hash": settings.weights_hash,
        "sri_weights": {"dimensions": settings.sri_dimensions(), "bands": settings.sri_weights.get("bands")},
        "costs": {"band_halfwidth": settings.costs.get("band_halfwidth", 0.1), "classes": settings.costs.get("classes") or {}, "derived": {cls: {"t_star": settings.t_star(cls), "band_halfwidth": settings.band_halfwidth(cls)} for cls in ("execution_gap", "negative_space", "alert_sample")}},
        "rules": rule_index(settings), "controls": settings.rules.get("controls") or {}, "rules_version": RULES_VERSION,
        "pipeline": settings.pipeline.model_dump(), "features": settings.features.model_dump(),
    }


def _read(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _write(path: Path, data: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def validate_weights(dims: dict[str, Any]) -> None:
    total = sum(float(d.get("weight", 0)) for d in dims.values())
    if abs(total - 1.0) > 1e-6:
        raise ValueError(f"dimension weights must sum to 1.0 (got {total:.4f})")
    for name, d in dims.items():
        subs = d.get("subs") or {}
        if subs and abs(sum(float(w) for w in subs.values()) - 1.0) > 1e-6:
            raise ValueError(f"sub-indicator weights of {name} must sum to 1.0")


def save_config(conn: duckdb.DuckDBPyConnection, settings: Settings, update: ConfigUpdate) -> Settings:
    cfg_dir = settings.config_dir
    if update.sri_weights is not None:
        data = _read(cfg_dir / CONFIG_FILES["sri_weights"])
        for name, patch in (update.sri_weights.get("dimensions") or {}).items():
            if name not in data["dimensions"]:
                raise ValueError(f"unknown dimension {name}")
            if "weight" in patch:
                data["dimensions"][name]["weight"] = float(patch["weight"])
            if "subs" in patch and patch["subs"] is not None:
                data["dimensions"][name]["subs"] = {k: float(v) for k, v in patch["subs"].items()}
        validate_weights(data["dimensions"])
        _write(cfg_dir / CONFIG_FILES["sri_weights"], data)
    if update.costs is not None:
        data = _read(cfg_dir / CONFIG_FILES["costs"])
        if "band_halfwidth" in update.costs:
            data["band_halfwidth"] = float(update.costs["band_halfwidth"])
        for cls, block in (update.costs.get("classes") or {}).items():
            cur = data.setdefault("classes", {}).setdefault(cls, {"C_FP": 1.0, "C_FN": 3.0})
            for k in ("C_FP", "C_FN", "band_halfwidth"):
                if k in block:
                    v = float(block[k])
                    if k != "band_halfwidth" and v <= 0:
                        raise ValueError("costs must be positive")
                    cur[k] = v
        _write(cfg_dir / CONFIG_FILES["costs"], data)
    if update.rules is not None:
        data = _read(cfg_dir / CONFIG_FILES["rules"])
        for rid, patch in update.rules.items():
            if rid not in data["rules"]:
                raise ValueError(f"unknown rule {rid}")
            for k in ("enabled", "prior_weight"):
                if k in patch:
                    data["rules"][rid][k] = patch[k]
            if "params" in patch and patch["params"]:
                data["rules"][rid].setdefault("params", {}).update(patch["params"])
        _write(cfg_dir / CONFIG_FILES["rules"], data)
    reset_settings_cache()
    new = load_settings(cfg_dir)
    conn.execute("INSERT INTO config_history (config_hash, saved_at, saved_by, snapshot_json, note) VALUES (?, ?, ?, ?, ?)",
                 [new.config_hash, datetime.now(), update.saved_by, to_json({"sri_weights": new.sri_weights, "costs": new.costs, "rules": new.rules}), update.note])
    record_event(conn, new, run_type="CONFIG", period=None, triggered_by=update.saved_by, trigger_source="api",
                 manifest={"previous_config_hash": settings.config_hash, "new_config_hash": new.config_hash, "changed": [k for k in ("sri_weights", "costs", "rules") if getattr(update, k) is not None], "note": update.note})
    return new


def config_history(conn: duckdb.DuckDBPyConnection, limit: int = 50) -> list[dict[str, Any]]:
    import json

    df = fetch_df(conn, "SELECT config_hash, saved_at, saved_by, note, snapshot_json FROM config_history ORDER BY saved_at DESC LIMIT ?", [limit])
    out = json.loads(df.to_json(orient="records", date_format="iso")) if len(df) else []
    for r in out:
        r["snapshot"] = json.loads(r.pop("snapshot_json")) if isinstance(r.get("snapshot_json"), str) else r.pop("snapshot_json", None)
    return out


def what_if(conn: duckdb.DuckDBPyConnection, settings: Settings, req: WhatIfRequest) -> dict[str, Any]:
    from satsa.analytics.module_c_benchmark import band_for
    from satsa.analytics.module_d_prioritise import decide
    from satsa.api.queries import current_run

    p, run_id = current_run(conn, req.period)
    out: dict[str, Any] = {"period": p, "rows": [], "n_uncertain_before": 0, "n_uncertain_after": 0}
    if run_id is None:
        return out
    dims_cfg = settings.sri_dimensions()
    weights = {d: float(cfg["weight"]) for d, cfg in dims_cfg.items()}
    new_w = {**weights, **{k: float(v) for k, v in (req.sri_weights or {}).items()}}
    df = fetch_df(conn, "SELECT s.entity_id, e.name, s.sri, s.dim_execution_gap, s.dim_negative_space, s.dim_escalation_discipline, s.dim_investigation_quality, s.dim_data_integrity, s.dim_trend_penalty FROM sri_scores s JOIN entities e ON e.entity_id = s.entity_id WHERE s.run_id = ?", [run_id])
    for r in df.itertuples():
        dims = {d: getattr(r, f"dim_{d}") or 0.0 for d in new_w}
        sri_new = sum(new_w[d] * dims[d] for d in new_w)
        out["rows"].append({"entity_id": r.entity_id, "name": r.name, "sri_current": r.sri, "sri_what_if": sri_new, "band_current": band_for(r.sri, settings), "band_what_if": band_for(sri_new, settings)})
    f = fetch_df(conn, "SELECT finding_class, p_final, decision FROM findings WHERE run_id = ?", [run_id])
    out["n_uncertain_before"] = int((f["decision"] == "MANUAL_REVIEW").sum())
    after = 0
    for row in f.itertuples():
        cls = row.finding_class
        block = (req.costs or {}).get(cls) or {}
        c_fp, c_fn = settings.cost(cls)
        c_fp, c_fn = float(block.get("C_FP", c_fp)), float(block.get("C_FN", c_fn))
        t = c_fp / (c_fp + c_fn)
        d = float(block.get("band_halfwidth", settings.band_halfwidth(cls)))
        after += decide(row.p_final, t, d) == "MANUAL_REVIEW"
    out["n_uncertain_after"] = int(after)
    out["thresholds"] = {cls: {"t_star": (lambda b: float(b.get("C_FP", settings.cost(cls)[0])) / (float(b.get("C_FP", settings.cost(cls)[0])) + float(b.get("C_FN", settings.cost(cls)[1]))))((req.costs or {}).get(cls) or {})} for cls in ("execution_gap", "negative_space", "alert_sample")}
    return out
