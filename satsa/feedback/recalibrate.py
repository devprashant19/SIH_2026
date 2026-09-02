"""Recalibration from supervisor feedback.

Refits the execution-gap calibrator on (raw ensemble score -> accept/reject) pairs once enough
labels exist, registers it as a new version, and reports per-rule precision with bounded
threshold suggestions. Nothing becomes active unless promote=True.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from satsa.analytics.calibration import Calibrator
from satsa.audit.hashing import hash_obj
from satsa.config import Settings
from satsa.db.connection import Database
from satsa.feedback.store import labelled_findings, rule_precision
from satsa.models import registry as reg
from satsa.models.artifacts import save_artifact, version_for


@dataclass
class RecalibrationResult:
    n_labels: int
    calibrator_version: str | None = None
    calibrated: bool = False
    metrics: dict[str, Any] = field(default_factory=dict)
    rule_suggestions: list[dict[str, Any]] = field(default_factory=list)
    skipped_reason: str | None = None
    promoted: bool = False


def recalibrate(db: Database, settings: Settings, *, promote: bool = False, run_id: str | None = None) -> RecalibrationResult:
    with db.read() as conn:
        pairs = [(fid, s, y) for fid, s, y in labelled_findings(conn) if s is not None]
        suggestions = rule_precision(conn)
        active = reg.active_versions(conn)
    result = RecalibrationResult(n_labels=len(pairs), rule_suggestions=suggestions)
    min_labels = settings.pipeline.min_labels_for_recalibration
    if len(pairs) < min_labels:
        result.skipped_reason = f"INSUFFICIENT_FEEDBACK: {len(pairs)} labelled findings, need {min_labels}"
        return result
    scores = np.array([s for _, s, _ in pairs], dtype=float)
    labels = np.array([y for _, _, y in pairs], dtype=float)
    if len(np.unique(labels)) < 2:
        result.skipped_reason = "SINGLE_CLASS: feedback contains only accepts or only rejects"
        return result
    cal = Calibrator(reg.CALIBRATOR_A, min_labels=min_labels).fit(scores, labels)
    data_hash = hash_obj(sorted(pairs))
    version = version_for(data_hash, settings.config_hash, settings.app.seed)
    parent = (active.get(reg.CALIBRATOR_A) or {}).get("version")
    metrics = {"n_labels": cal.n_labels, "calibrated": cal.calibrated, "ece": cal.ece, "brier": cal.brier, "source": "supervisor_feedback"}
    with db.write() as conn:
        path, digest = save_artifact(settings.resolve(settings.paths.models_dir), reg.CALIBRATOR_A, version, cal, {"metrics": metrics, "reliability": cal.reliability, "training_data_hash": data_hash, "parent_version": parent})
        reg.register(conn, settings, name=reg.CALIBRATOR_A, version=version, path=path, artifact_hash=digest, run_id=run_id, periods=[], rows=cal.n_labels,
                     data_hash=data_hash, hyperparams={"min_labels": min_labels}, metrics=metrics, parent=parent, feedback_count=cal.n_labels, promote=promote)
    result.calibrator_version, result.calibrated, result.metrics, result.promoted = version, cal.calibrated, metrics, promote
    return result
