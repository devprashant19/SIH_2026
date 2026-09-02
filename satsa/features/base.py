"""Shared types and helpers for feature modules."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from satsa.config import Settings
from satsa.schema.enums import ACTION_RANK, AnalystAction

SEVS = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
INVESTIGATED_RANK = ACTION_RANK[AnalystAction.INVESTIGATED]
OK, LOW_N, DEGENERATE, MISSING = "OK", "LOW_N", "DEGENERATE", "MISSING"


@dataclass(frozen=True)
class FeatureMeta:
    name: str
    label: str
    group: str
    formula: str
    min_n: int = 1
    higher_is_worse: bool = True
    unit: str | None = None
    headline: bool = False  # materialised as a DuckDB column (see schema.sql)


@dataclass
class FeatureValue:
    value: float | None
    n: int
    flag: str = OK

    def as_dict(self) -> dict[str, Any]:
        return {"n": self.n, "flag": self.flag}


def fv(value: Any, n: int, min_n: int = 1) -> FeatureValue:
    if value is None or (isinstance(value, (float, np.floating)) and math.isnan(value)):
        return FeatureValue(None, int(n), MISSING if n == 0 else DEGENERATE)
    return FeatureValue(float(value), int(n), OK if n >= min_n else LOW_N)


def rate(numerator: float, denominator: float) -> float | None:
    return None if denominator == 0 else float(numerator) / float(denominator)


def norm_entropy(counts: pd.Series, k: int) -> float | None:
    """Shannon entropy of a categorical distribution normalised by log2(k) -> [0, 1]."""
    total = counts.sum()
    if total == 0 or k <= 1:
        return None
    p = counts[counts > 0] / total
    h = float(-(p * np.log2(p)).sum())
    return h / math.log2(k)


def action_rank(series: pd.Series) -> pd.Series:
    return series.map(lambda a: ACTION_RANK.get(AnalystAction(a), 0) if a is not None else 0)


def minutes_between(later: pd.Series, earlier: pd.Series) -> pd.Series:
    return (pd.to_datetime(later) - pd.to_datetime(earlier)).dt.total_seconds() / 60.0


@dataclass
class EntityContext:
    """Everything a feature module may look at for one (entity, period)."""

    entity_id: str
    period: str
    entity: dict[str, Any]
    alerts: pd.DataFrame                       # this period only
    history: pd.DataFrame                      # prior periods for this entity (up to 3)
    prior_periods: list[str]                   # ordered oldest -> newest
    assets: pd.DataFrame
    escalations: pd.DataFrame
    incidents: pd.DataFrame
    validation: dict[str, Any]                 # aggregated ValidationReport counts for this entity-period
    global_alerts: pd.DataFrame                # all entities, this period + history (for AACT global rates)
    settings: Settings
    extras: dict[str, Any] = field(default_factory=dict)  # non-scalar evidence (lists, per-category dicts)

    @property
    def closed(self) -> pd.DataFrame:
        a = self.alerts
        return a[a["closed_at"].notna()]

    def history_for(self, period: str) -> pd.DataFrame:
        h = self.history
        return h[h["submission_period"] == period]


def period_bounds(period: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Inclusive [first second, last second] of a 'YYYY-MM' period, via plain datetime arithmetic."""
    start = datetime.strptime(period + "-01", "%Y-%m-%d")
    nxt = datetime(start.year + (start.month == 12), (start.month % 12) + 1, 1)
    return pd.Timestamp(start), pd.Timestamp(nxt - timedelta(seconds=1))
