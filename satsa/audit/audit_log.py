"""Append-only run log with a hash chain. Rows are inserted once and finalised once."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

import duckdb

from satsa.audit.hashing import chain_hash, new_id
from satsa.config import Settings
from satsa.db.repo import fetch_one, to_json
from satsa.version import FEATURE_VERSION, RULES_VERSION, __version__, get_code_hash


def last_run_hash(conn: duckdb.DuckDBPyConnection) -> str | None:
    row = fetch_one(conn, "SELECT run_hash FROM audit_runs WHERE run_hash IS NOT NULL ORDER BY finished_at DESC, run_id DESC LIMIT 1")
    return row[0] if row else None


def start_run(conn: duckdb.DuckDBPyConnection, settings: Settings, *, run_type: str, period: str | None, triggered_by: str, trigger_source: str,
              model_versions: dict[str, str] | None = None, input_manifest: list[dict] | None = None, input_hash: str | None = None) -> str:
    run_id = new_id("run_")
    conn.execute(
        """INSERT INTO audit_runs (run_id, run_type, submission_period, triggered_by, trigger_source, started_at, status, app_version, code_hash,
           rules_version, feature_version, config_hash, config_snapshot_json, model_versions_json, input_manifest_json, input_hash, prev_run_hash)
           VALUES (?, ?, ?, ?, ?, ?, 'RUNNING', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [run_id, run_type, period, triggered_by, trigger_source, datetime.now(), __version__, get_code_hash(), RULES_VERSION, FEATURE_VERSION,
         settings.config_hash, to_json(_snapshot(settings)), to_json(model_versions or {}), to_json(input_manifest or []), input_hash, last_run_hash(conn)],
    )
    return run_id


def finish_run(conn: duckdb.DuckDBPyConnection, settings: Settings, run_id: str, *, status: str, output_manifest: dict[str, Any] | None = None,
               output_hash: str | None = None, stage_log: list[dict] | None = None, error_text: str | None = None) -> str:
    row = fetch_one(conn, "SELECT status, finished_at, prev_run_hash, config_hash, code_hash, input_hash FROM audit_runs WHERE run_id = ?", [run_id])
    if row is None:
        raise KeyError(run_id)
    if row[1] is not None:
        raise RuntimeError(f"audit run {run_id} is already finalised; audit rows are append-only")
    run_hash = chain_hash(row[2], run_id, row[3], row[4], row[5], output_hash, status)
    conn.execute(
        "UPDATE audit_runs SET status = ?, finished_at = ?, output_manifest_json = ?, output_hash = ?, stage_log_json = ?, error_text = ?, run_hash = ? WHERE run_id = ?",
        [status, datetime.now(), to_json(output_manifest or {}), output_hash, to_json(stage_log or []), error_text, run_hash, run_id],
    )
    _append_jsonl(settings, {"run_id": run_id, "status": status, "run_hash": run_hash, "prev_run_hash": row[2], "finished_at": datetime.now().isoformat(timespec="seconds")})
    return run_hash


def record_event(conn: duckdb.DuckDBPyConnection, settings: Settings, *, run_type: str, period: str | None, triggered_by: str, trigger_source: str, manifest: dict[str, Any], output_hash: str | None = None) -> str:
    """Single-shot audit row for ingest / feedback / report / config / train events."""
    run_id = start_run(conn, settings, run_type=run_type, period=period, triggered_by=triggered_by, trigger_source=trigger_source, input_manifest=[manifest])
    finish_run(conn, settings, run_id, status="SUCCESS", output_manifest=manifest, output_hash=output_hash)
    return run_id


def _snapshot(settings: Settings) -> dict[str, Any]:
    return {"sri_weights": settings.sri_weights, "costs": settings.costs, "rules": settings.rules, "peer_groups": settings.peer_groups, "pipeline": settings.pipeline.model_dump(), "features": settings.features.model_dump()}


def _append_jsonl(settings: Settings, record: dict[str, Any]) -> None:
    logs = settings.resolve(settings.paths.logs_dir)
    logs.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(logs / "audit.jsonl"), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    with os.fdopen(fd, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
