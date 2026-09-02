"""Offline training: fit the entity ensemble, the alert-level model and their calibrators
on historical periods, save versioned artifacts, and (optionally) promote them to active."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from satsa.analytics.anomaly import MODULE_A_FEATURES, AlertAnomalyModel, EntityAnomalyEnsemble, alert_feature_frame
from satsa.analytics.calibration import Calibrator
from satsa.analytics.rules.base import RuleContext
from satsa.analytics.rules.catalogue import build_catalogue, evaluate_all
from satsa.audit.audit_log import record_event
from satsa.audit.hashing import hash_dataframe
from satsa.config import Settings
from satsa.db.connection import Database
from satsa.features.build import FeatureBuildResult, build_features
from satsa.features.notes import per_alert_template_similarity
from satsa.models import registry as reg
from satsa.models.artifacts import save_artifact, version_for


@dataclass
class TrainResult:
    versions: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, dict] = field(default_factory=dict)
    rows_entity: int = 0
    rows_alert: int = 0
    promoted: bool = False


def ensemble_frame(fb: FeatureBuildResult) -> pd.DataFrame:
    """Raw Module-A features plus their peer z-scores, one row per entity."""
    zmap = {r.entity_id: json.loads(r.peer_z_json) for r in fb.rows.itertuples()}
    rows = {}
    for eid, feats in fb.values.items():
        row = {k: (feats[k].value if k in feats and feats[k].value is not None else np.nan) for k in MODULE_A_FEATURES}
        for k in MODULE_A_FEATURES:
            z = zmap.get(eid, {}).get(k)
            row[f"z_{k}"] = np.nan if z is None else z
        rows[eid] = row
    return pd.DataFrame(rows).T.astype(float)


def peer_view(fb: FeatureBuildResult, eid: str) -> dict[str, dict]:
    """Per-feature peer statistics for one entity: z, percentile, median, p10, p90, n."""
    row = fb.rows[fb.rows["entity_id"] == eid].iloc[0]
    z, pct = json.loads(row["peer_z_json"]), json.loads(row["peer_pct_json"])
    stats = {}
    if len(fb.baselines):
        b = fb.baselines[fb.baselines["peer_group_id"] == fb.assignments[eid].peer_group_id]
        stats = {r.feature: {"median": r.median, "p10": r.p10, "p90": r.p90, "n": r.n} for r in b.itertuples()}
    return {f: {**stats.get(f, {}), "z": z.get(f), "pct": pct.get(f)} for f in set(z) | set(stats)}


def rule_hit_mask(fb: FeatureBuildResult, settings: Settings) -> pd.Series:
    """True for entity rows with zero execution-gap rule hits (the HDBSCAN 'normal' baseline)."""
    rules = build_catalogue(settings, "A")
    clean = {}
    for eid, ctx in fb.contexts.items():
        rc = RuleContext(ctx, fb.values[eid], peer_view(fb, eid), settings)
        clean[eid] = not any(r.hit for r in evaluate_all(rules, rc))
    return pd.Series(clean)


def load_entity_labels(settings: Settings) -> pd.DataFrame | None:
    path = settings.resolve(settings.paths.ground_truth_dir) / "entity_period_labels.csv"
    return pd.read_csv(path, dtype=str) if path.exists() else None


def load_alert_labels(settings: Settings) -> set[str]:
    path = settings.resolve(settings.paths.ground_truth_dir) / "alert_labels.csv"
    if not path.exists():
        return set()
    return set(pd.read_csv(path, dtype=str)["alert_id"])


def train_models(db: Database, settings: Settings, periods: list[str], *, promote: bool = False, run_id: str | None = None, seed: int | None = None, triggered_by: str = "cli", trigger_source: str = "cli") -> TrainResult:
    seed = settings.app.seed if seed is None else seed
    result = TrainResult()
    frames, clean_masks, keys = [], [], []
    alert_frames: list[pd.DataFrame] = []
    with db.read() as conn:
        for period in periods:
            fb = build_features(conn, settings, period, run_id or "train")
            if fb.rows.empty:
                continue
            ef = ensemble_frame(fb)
            frames.append(ef)
            clean_masks.append(rule_hit_mask(fb, settings).reindex(ef.index).fillna(False))
            keys += [(eid, period) for eid in ef.index]
            for ctx in fb.contexts.values():
                a = ctx.alerts
                if len(a):
                    f = alert_feature_frame(a, per_alert_template_similarity(a))
                    f["alert_id"] = a["alert_id"].astype(str).values
                    alert_frames.append(f)
    if not frames:
        raise RuntimeError("no feature rows for the requested periods; ingest data first")

    X = pd.concat(frames, ignore_index=True)
    clean = pd.concat(clean_masks, ignore_index=True).values.astype(bool)
    data_hash = hash_dataframe(X)
    version = version_for(data_hash, settings.config_hash, seed)
    models_dir = settings.resolve(settings.paths.models_dir)
    pcfg = settings.pipeline

    ensemble = EntityAnomalyEnsemble(feature_names=list(X.columns), weights=pcfg.ml_weights, min_rows_lof=pcfg.min_rows_lof, min_rows_hdbscan=pcfg.min_rows_hdbscan, seed=seed).fit(X, clean)
    scores = ensemble.score(X)
    result.rows_entity = len(X)

    labels = load_entity_labels(settings)
    y = np.full(len(X), np.nan)
    if labels is not None:
        lab = {(r.entity_id, r.submission_period): float(r.is_execution_gap) for r in labels.itertuples()}
        y = np.array([lab.get(k, np.nan) for k in keys], dtype=float)
    cal_a = Calibrator(reg.CALIBRATOR_A, min_labels=pcfg.min_labels_for_calibration)
    m = ~np.isnan(y)
    if m.sum():
        cal_a.fit(scores.s_ml[m], y[m])

    alert_if, cal_alert = None, None
    if alert_frames:
        A = pd.concat(alert_frames, ignore_index=True)
        alert_if = AlertAnomalyModel(seed=seed).fit(A)
        result.rows_alert = alert_if.n_train
        flagged = load_alert_labels(settings)
        if flagged:
            sample = A.sample(n=min(len(A), 20_000), random_state=seed)
            ya = sample["alert_id"].isin(flagged).astype(float).values
            cal_alert = Calibrator(reg.CALIBRATOR_ALERT, min_labels=pcfg.min_labels_for_calibration).fit(alert_if.score(sample), ya)

    hyper = {"features": list(X.columns), "ml_weights": pcfg.ml_weights, "seed": seed, "detectors": scores.detectors_used, "periods": periods}
    metrics_e = {"n_rows": len(X), "n_clean": int(clean.sum()), "mean_s_ml": float(np.nanmean(scores.s_ml)), "detectors": scores.detectors_used}
    with db.write() as conn:
        p, h = save_artifact(models_dir, reg.ENTITY_ENSEMBLE, version, ensemble, {"hyperparams": hyper, "metrics": metrics_e, "training_data_hash": data_hash})
        reg.register(conn, settings, name=reg.ENTITY_ENSEMBLE, version=version, path=p, artifact_hash=h, run_id=run_id, periods=periods, rows=len(X), data_hash=data_hash, hyperparams=hyper, metrics=metrics_e, promote=promote)
        metrics_c = {"n_labels": cal_a.n_labels, "calibrated": cal_a.calibrated, "ece": cal_a.ece, "brier": cal_a.brier}
        p, h = save_artifact(models_dir, reg.CALIBRATOR_A, version, cal_a, {"metrics": metrics_c, "reliability": cal_a.reliability, "training_data_hash": data_hash})
        reg.register(conn, settings, name=reg.CALIBRATOR_A, version=version, path=p, artifact_hash=h, run_id=run_id, periods=periods, rows=cal_a.n_labels, data_hash=data_hash, hyperparams={"min_labels": cal_a.min_labels}, metrics=metrics_c, promote=promote)
        result.metrics.update({reg.ENTITY_ENSEMBLE: metrics_e, reg.CALIBRATOR_A: metrics_c})
        if alert_if is not None:
            metrics_a = {"n_rows": alert_if.n_train}
            p, h = save_artifact(models_dir, reg.ALERT_IF, version, alert_if, {"metrics": metrics_a, "training_data_hash": data_hash})
            reg.register(conn, settings, name=reg.ALERT_IF, version=version, path=p, artifact_hash=h, run_id=run_id, periods=periods, rows=alert_if.n_train, data_hash=data_hash, hyperparams={"seed": seed}, metrics=metrics_a, promote=promote)
            result.metrics[reg.ALERT_IF] = metrics_a
        if cal_alert is not None:
            metrics_ca = {"n_labels": cal_alert.n_labels, "calibrated": cal_alert.calibrated, "ece": cal_alert.ece, "brier": cal_alert.brier}
            p, h = save_artifact(models_dir, reg.CALIBRATOR_ALERT, version, cal_alert, {"metrics": metrics_ca, "reliability": cal_alert.reliability, "training_data_hash": data_hash})
            reg.register(conn, settings, name=reg.CALIBRATOR_ALERT, version=version, path=p, artifact_hash=h, run_id=run_id, periods=periods, rows=cal_alert.n_labels, data_hash=data_hash, hyperparams={}, metrics=metrics_ca, promote=promote)
            result.metrics[reg.CALIBRATOR_ALERT] = metrics_ca
    result.versions = {k: version for k in result.metrics}
    result.promoted = promote
    with db.write() as conn:
        record_event(conn, settings, run_type="TRAIN", period=periods[-1], triggered_by=triggered_by, trigger_source=trigger_source,
                     manifest={"periods": periods, "versions": result.versions, "metrics": result.metrics, "promoted": promote,
                               "rows_entity": result.rows_entity, "rows_alert": result.rows_alert, "training_data_hash": data_hash},
                     output_hash=data_hash)
    return result
