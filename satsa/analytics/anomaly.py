"""Unsupervised anomaly ensemble over entity-period feature vectors.

IsolationForest + LocalOutlierFactor (+ HDBSCAN/GLOSH when the optional package is present),
each producing a [0, 1] score, averaged with configurable weights over the detectors that
could run. Everything is CPU-only and trains in seconds at this data scale.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.neighbors import LocalOutlierFactor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import QuantileTransformer

try:  # optional, needs a C compiler to install
    import hdbscan as _hdbscan  # type: ignore

    HDBSCAN_AVAILABLE = True
except Exception:  # pragma: no cover
    _hdbscan = None
    HDBSCAN_AVAILABLE = False

# Entity-period features the execution-gap ensemble looks at (raw values; peer-z columns are appended).
MODULE_A_FEATURES = [
    "ttc_median_critical", "ttc_median_high", "ttc_cv_critical", "fast_close_rate_critical", "fast_close_rate_high",
    "ack_only_rate", "ack_then_close_no_invest_rate", "escalation_ratio_critical", "critical_closed_no_escalation_rate",
    "closure_reason_entropy", "closure_reason_top_share", "fp_rate_critical", "note_missing_rate", "note_template_score",
    "note_dup_cluster_share", "note_distinct_ratio", "note_len_median", "note_len_ttc_corr", "repeat_no_remediation_rate",
    "cross_period_repeat_rate", "aact_inv_gap_30_wmean", "aact_inv_rate_slope_30", "batch_close_score", "offhours_close_rate",
    "root_cause_rate",
]


@dataclass
class EnsembleScores:
    s_if: np.ndarray
    s_lof: np.ndarray
    s_hdb: np.ndarray  # NaN when HDBSCAN unavailable / skipped
    s_ml: np.ndarray
    detectors_used: list[str]


@dataclass
class EntityAnomalyEnsemble:
    feature_names: list[str]
    weights: dict[str, float] = field(default_factory=lambda: {"isolation_forest": 0.4, "lof": 0.3, "hdbscan": 0.3})
    min_rows_lof: int = 5
    min_rows_hdbscan: int = 15
    seed: int = 42
    preprocessor: Pipeline | None = None
    iforest: IsolationForest | None = None
    lof: LocalOutlierFactor | None = None
    hdb: Any = None
    if_min: float = 0.0
    if_max: float = 1.0
    n_train: int = 0

    def _X(self, frame: pd.DataFrame) -> np.ndarray:
        return frame.reindex(columns=self.feature_names).astype(float).values

    def fit(self, frame: pd.DataFrame, clean_mask: np.ndarray | None = None) -> "EntityAnomalyEnsemble":
        X = self._X(frame)
        n = len(X)
        self.n_train = n
        self.preprocessor = Pipeline([
            ("impute", SimpleImputer(strategy="median")),
            ("quantile", QuantileTransformer(output_distribution="normal", n_quantiles=max(2, min(n, 50)), random_state=self.seed)),
        ])
        Z = self.preprocessor.fit_transform(X)
        self.iforest = IsolationForest(n_estimators=300, contamination="auto", max_samples=min(256, n), random_state=self.seed).fit(Z)
        raw = -self.iforest.decision_function(Z)
        self.if_min, self.if_max = float(raw.min()), float(raw.max())
        if n >= self.min_rows_lof:
            self.lof = LocalOutlierFactor(n_neighbors=min(10, n - 1), novelty=True, contamination=0.1).fit(Z)
        if HDBSCAN_AVAILABLE and n >= self.min_rows_hdbscan:
            base = Z[clean_mask] if clean_mask is not None and clean_mask.sum() >= 10 else Z
            self.hdb = _hdbscan.HDBSCAN(min_cluster_size=max(3, len(base) // 8), min_samples=2, prediction_data=True).fit(base)
            if self.hdb.labels_.max() < 0:  # everything is noise -> useless
                self.hdb = None
        return self

    def score(self, frame: pd.DataFrame) -> EnsembleScores:
        assert self.preprocessor is not None and self.iforest is not None, "ensemble not fitted"
        Z = self.preprocessor.transform(self._X(frame))
        raw = -self.iforest.decision_function(Z)
        span = (self.if_max - self.if_min) or 1.0
        s_if = np.clip((raw - self.if_min) / span, 0, 1)
        used = ["isolation_forest"]
        if self.lof is not None:
            s_lof = np.clip((-self.lof.score_samples(Z) - 1.0) / 2.0, 0, 1)
            used.append("lof")
        else:
            s_lof = np.full(len(Z), np.nan)
        if self.hdb is not None:
            _, strengths = _hdbscan.approximate_predict(self.hdb, Z)
            s_hdb = np.clip(1.0 - strengths, 0, 1)
            used.append("hdbscan")
        else:
            s_hdb = np.full(len(Z), np.nan)
        parts = {"isolation_forest": s_if, "lof": s_lof, "hdbscan": s_hdb}
        w = np.array([self.weights.get(k, 0.0) for k in used])
        stack = np.vstack([parts[k] for k in used])
        s_ml = (stack * w[:, None]).sum(axis=0) / w.sum()
        return EnsembleScores(s_if, s_lof, s_hdb, s_ml, used)


ALERT_FEATURES = ["log_ttc", "note_len", "severity_ord", "escalated", "hour", "closure_ord", "log_ack_latency", "template_sim", "weekend"]
SEV_ORD = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}
CLOSURE_ORD = {"REMEDIATED": 0, "ESCALATED_TO_IR": 1, "DUPLICATE": 2, "BENIGN": 3, "FALSE_POSITIVE": 4, "NO_ACTION_REQUIRED": 5, "OTHER": 6, "UNKNOWN": 7}


def alert_feature_frame(alerts: pd.DataFrame, template_sim: pd.Series | None = None) -> pd.DataFrame:
    """Per-alert numeric features for the alert-level IsolationForest."""
    ts = pd.to_datetime(alerts["ts"])
    ack = (pd.to_datetime(alerts["acknowledged_at"]) - ts).dt.total_seconds() / 60
    f = pd.DataFrame(index=alerts.index)
    f["log_ttc"] = np.log1p(alerts["time_to_close_min"].astype(float).clip(lower=0))
    f["note_len"] = alerts["investigation_notes"].fillna("").astype(str).str.len().astype(float)
    f["severity_ord"] = alerts["severity"].map(SEV_ORD).astype(float)
    f["escalated"] = alerts["escalation_flag"].map(lambda v: 1.0 if v is True or v == 1 else 0.0).astype(float)
    f["hour"] = ts.dt.hour.astype(float)
    f["closure_ord"] = alerts["closure_reason"].map(CLOSURE_ORD).astype(float)
    f["log_ack_latency"] = np.log1p(ack.clip(lower=0))
    f["template_sim"] = template_sim.reindex(alerts.index).astype(float) if template_sim is not None else np.nan
    f["weekend"] = (ts.dt.weekday >= 5).astype(float)
    return f


@dataclass
class AlertAnomalyModel:
    seed: int = 42
    preprocessor: Pipeline | None = None
    iforest: IsolationForest | None = None
    lo: float = 0.0
    hi: float = 1.0
    n_train: int = 0

    def fit(self, f: pd.DataFrame, max_rows: int = 50_000) -> "AlertAnomalyModel":
        if len(f) > max_rows:
            f = f.sample(n=max_rows, random_state=self.seed)
        self.preprocessor = Pipeline([("impute", SimpleImputer(strategy="median")), ("quantile", QuantileTransformer(output_distribution="normal", n_quantiles=min(len(f), 200), random_state=self.seed))])
        Z = self.preprocessor.fit_transform(f[ALERT_FEATURES].values)
        self.iforest = IsolationForest(n_estimators=200, contamination="auto", random_state=self.seed).fit(Z)
        raw = -self.iforest.decision_function(Z)
        self.lo, self.hi = float(np.percentile(raw, 1)), float(np.percentile(raw, 99))
        self.n_train = len(f)
        return self

    def score(self, f: pd.DataFrame) -> np.ndarray:
        Z = self.preprocessor.transform(f[ALERT_FEATURES].values)
        raw = -self.iforest.decision_function(Z)
        return np.clip((raw - self.lo) / ((self.hi - self.lo) or 1.0), 0, 1)
