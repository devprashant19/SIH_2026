"""Model registry: DuckDB table + models/registry.json mirror, and the active bundle loader."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import duckdb

from satsa.analytics.anomaly import AlertAnomalyModel, EntityAnomalyEnsemble
from satsa.analytics.calibration import Calibrator
from satsa.config import Settings
from satsa.db.repo import fetch_df, to_json
from satsa.features.registry import feature_list_hash
from satsa.models.artifacts import load_artifact
from satsa.version import FEATURE_VERSION

ENTITY_ENSEMBLE, CALIBRATOR_A, ALERT_IF, CALIBRATOR_ALERT = "entity_ensemble", "calibrator_a", "alert_if", "calibrator_alert"
MODEL_NAMES = [ENTITY_ENSEMBLE, CALIBRATOR_A, ALERT_IF, CALIBRATOR_ALERT]


@dataclass
class ModelBundle:
    versions: dict[str, str]
    ensemble: EntityAnomalyEnsemble | None = None
    calibrator_a: Calibrator | None = None
    alert_if: AlertAnomalyModel | None = None
    calibrator_alert: Calibrator | None = None
    meta: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def available(self) -> bool:
        return self.ensemble is not None


def register(conn: duckdb.DuckDBPyConnection, settings: Settings, *, name: str, version: str, path: Path, artifact_hash: str,
             run_id: str | None, periods: list[str], rows: int, data_hash: str, hyperparams: dict, metrics: dict,
             parent: str | None = None, feedback_count: int = 0, promote: bool = False) -> None:
    if promote:
        conn.execute("UPDATE model_registry SET is_active = FALSE, superseded_by = ? WHERE model_name = ? AND is_active = TRUE", [version, name])
    libs = json.loads((path.parent / "meta.json").read_text(encoding="utf-8")).get("library_versions", {})
    conn.execute(
        """INSERT INTO model_registry (model_name, version, path, artifact_hash, is_active, trained_at, trained_by_run_id, training_periods,
           training_rows, training_data_hash, feature_version, feature_list_hash, hyperparams_json, library_versions_json, metrics_json,
           parent_version, trained_on_feedback_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [name, version, str(path), artifact_hash, promote, datetime.now(), run_id, periods, rows, data_hash, FEATURE_VERSION,
         feature_list_hash(), to_json(hyperparams), to_json(libs), to_json(metrics), parent, feedback_count],
    )
    write_registry_mirror(conn, settings)


def write_registry_mirror(conn: duckdb.DuckDBPyConnection, settings: Settings) -> None:
    df = fetch_df(conn, "SELECT model_name, version, path, artifact_hash, is_active, trained_at, training_rows, feature_list_hash, metrics_json FROM model_registry ORDER BY model_name, trained_at")
    out = settings.resolve(settings.paths.models_dir) / "registry.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(json.loads(df.to_json(orient="records", date_format="iso")), indent=2), encoding="utf-8")


def active_versions(conn: duckdb.DuckDBPyConnection) -> dict[str, dict[str, Any]]:
    df = fetch_df(conn, "SELECT model_name, version, path, artifact_hash, feature_list_hash, feature_version FROM model_registry WHERE is_active = TRUE")
    return {r.model_name: r._asdict() for r in df.itertuples(index=False)}


def load_active_bundle(conn: duckdb.DuckDBPyConnection, settings: Settings, strict: bool = True) -> ModelBundle:
    """Load active models. Refuses (strict) to use models trained on a different feature list."""
    active = active_versions(conn)
    bundle = ModelBundle(versions={k: v["version"] for k, v in active.items()}, meta=active)
    if ENTITY_ENSEMBLE not in active:
        return bundle
    ens = active[ENTITY_ENSEMBLE]
    if ens.get("feature_list_hash") != feature_list_hash() or ens.get("feature_version") != FEATURE_VERSION:
        msg = f"active {ENTITY_ENSEMBLE} {ens['version']} was trained on a different feature list; retrain with `satsa train --promote`"
        if strict:
            raise RuntimeError(msg)
        return bundle
    bundle.ensemble = load_artifact(ens["path"], ens["artifact_hash"])
    if CALIBRATOR_A in active:
        bundle.calibrator_a = load_artifact(active[CALIBRATOR_A]["path"], active[CALIBRATOR_A]["artifact_hash"])
    if ALERT_IF in active:
        bundle.alert_if = load_artifact(active[ALERT_IF]["path"], active[ALERT_IF]["artifact_hash"])
    if CALIBRATOR_ALERT in active:
        bundle.calibrator_alert = load_artifact(active[CALIBRATOR_ALERT]["path"], active[CALIBRATOR_ALERT]["artifact_hash"])
    return bundle
