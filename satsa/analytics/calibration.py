"""Probability calibration with an explicit 'uncalibrated' fallback.

Raw anomaly scores are not probabilities. When enough labelled examples exist (synthetic
ground truth at bootstrap, supervisor feedback thereafter) an isotonic map turns scores into
calibrated P(weakness). Otherwise the identity map is used and every output is marked
calibrated=False so the dashboard can say so.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.isotonic import IsotonicRegression


@dataclass
class Calibrator:
    name: str
    min_labels: int = 20
    model: IsotonicRegression | None = None
    n_labels: int = 0
    calibrated: bool = False
    ece: float | None = None
    brier: float | None = None
    reliability: list[dict] = field(default_factory=list)

    def fit(self, scores: np.ndarray, labels: np.ndarray) -> "Calibrator":
        scores, labels = np.asarray(scores, dtype=float), np.asarray(labels, dtype=float)
        mask = ~np.isnan(scores)
        scores, labels = scores[mask], labels[mask]
        self.n_labels = int(len(scores))
        if self.n_labels < self.min_labels or len(np.unique(labels)) < 2:
            self.model, self.calibrated = None, False
            return self
        self.model = IsotonicRegression(out_of_bounds="clip", y_min=0.01, y_max=0.99).fit(scores, labels)
        self.calibrated = True
        p = self.predict(scores)
        self.brier = float(np.mean((p - labels) ** 2))
        self.ece, self.reliability = reliability_curve(p, labels)
        return self

    def predict(self, scores: np.ndarray) -> np.ndarray:
        s = np.clip(np.asarray(scores, dtype=float), 0, 1)
        if self.model is None:
            return s
        return np.asarray(self.model.predict(s), dtype=float)


def reliability_curve(p: np.ndarray, y: np.ndarray, bins: int = 10) -> tuple[float, list[dict]]:
    edges = np.quantile(p, np.linspace(0, 1, bins + 1)) if len(np.unique(p)) > bins else np.linspace(0, 1, bins + 1)
    edges[0], edges[-1] = -1e-9, 1 + 1e-9
    ece, rows = 0.0, []
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (p > lo) & (p <= hi)
        if m.sum() == 0:
            continue
        conf, acc = float(p[m].mean()), float(y[m].mean())
        ece += m.mean() * abs(acc - conf)
        rows.append({"bin_low": float(max(lo, 0)), "bin_high": float(min(hi, 1)), "n": int(m.sum()), "confidence": conf, "accuracy": acc})
    return float(ece), rows
