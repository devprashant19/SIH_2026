"""AACT-style rolling investigated-rates per category, entity versus global.

For each category the trailing-window rate is
    inv_rate_w = n(action >= INVESTIGATED and ts in [d - w, d]) / n(ts in [d - w, d])
computed for the entity and pooled over all entities. A positive gap (global - entity)
means the entity investigates that category less than everyone else.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from datetime import timedelta

from satsa.features.base import INVESTIGATED_RANK, EntityContext, FeatureMeta, FeatureValue, action_rank, fv, period_bounds

META: list[FeatureMeta] = [
    FeatureMeta("aact_inv_gap_30_max", "Largest investigated-rate deficit (30d)", "aact", "max_cat (global_rate_30 - entity_rate_30), n_cat >= 10", 10, True, headline=True),
    FeatureMeta("aact_inv_gap_30_wmean", "Volume-weighted investigated-rate deficit (30d)", "aact", "sum_cat n_cat * gap_cat / sum n_cat", 20, True, headline=True),
    FeatureMeta("aact_inv_rate_7_gap", "Investigated-rate deficit (7d)", "aact", "global_rate_7 - entity_rate_7 over all categories", 10, True),
    FeatureMeta("aact_inv_rate_slope_30", "Investigated-rate trend (30d)", "aact", "slope per day of the daily rolling-30 investigated rate", 15, False, headline=True),
]


def _rate(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> tuple[float | None, int]:
    w = frame[(frame["ts"] >= start) & (frame["ts"] <= end)]
    n = len(w)
    if n == 0:
        return None, 0
    return float(w["_inv"].mean()), n


def compute(ctx: EntityContext) -> dict[str, FeatureValue]:
    ent = _prep(pd.concat([ctx.alerts, ctx.history]) if len(ctx.history) else ctx.alerts)
    glob = _prep(ctx.global_alerts)
    period_start, period_end = period_bounds(ctx.period)
    out: dict[str, FeatureValue] = {}

    gaps: dict[str, dict] = {}
    for cat in sorted(ent["category"].dropna().unique()):
        e_rate, e_n = _rate(ent[ent["category"] == cat], period_end - timedelta(days=30), period_end)
        g_rate, g_n = _rate(glob[glob["category"] == cat], period_end - timedelta(days=30), period_end)
        if e_rate is not None and g_rate is not None:
            gaps[str(cat)] = {"entity_rate": e_rate, "global_rate": g_rate, "gap": g_rate - e_rate, "n": e_n, "global_n": g_n}
    eligible = {c: g for c, g in gaps.items() if g["n"] >= 10}
    if eligible:
        worst = max(eligible.items(), key=lambda kv: kv[1]["gap"])
        total = sum(g["n"] for g in eligible.values())
        out["aact_inv_gap_30_max"] = fv(worst[1]["gap"], worst[1]["n"], 10)
        out["aact_inv_gap_30_wmean"] = fv(sum(g["n"] * g["gap"] for g in eligible.values()) / total, total, 20)
        ctx.extras["aact_worst_category"] = worst[0]
    else:
        out["aact_inv_gap_30_max"] = fv(None, 0)
        out["aact_inv_gap_30_wmean"] = fv(None, 0)

    e7, n7 = _rate(ent, period_end - timedelta(days=7), period_end)
    g7, _ = _rate(glob, period_end - timedelta(days=7), period_end)
    out["aact_inv_rate_7_gap"] = fv(None if e7 is None or g7 is None else g7 - e7, n7, 10)

    # Daily rolling-30 series across the period -> slope per day.
    days = pd.date_range(period_start, period_end.normalize(), freq="D")
    series = []
    for d in days:
        r, n = _rate(ent, d - timedelta(days=30), d + timedelta(days=1, seconds=-1))
        series.append(np.nan if r is None or n < 15 else r)
    s = np.array(series, dtype=float)
    valid = ~np.isnan(s)
    if valid.sum() >= 15:
        x = np.arange(len(s))[valid]
        slope = float(np.polyfit(x, s[valid], 1)[0])
        out["aact_inv_rate_slope_30"] = fv(slope, int(valid.sum()), 15)
    else:
        out["aact_inv_rate_slope_30"] = fv(None, int(valid.sum()))

    ctx.extras["aact_category_gaps"] = gaps
    ctx.extras["aact_never_investigated_cats"] = [c for c, g in gaps.items() if g["n"] >= 5 and g["entity_rate"] == 0.0]
    ctx.extras["aact_daily_rate_30"] = [None if np.isnan(v) else round(float(v), 4) for v in s]
    return out


def _prep(frame: pd.DataFrame) -> pd.DataFrame:
    f = frame[["ts", "category", "analyst_action"]].copy()
    f["ts"] = pd.to_datetime(f["ts"])
    f["_inv"] = (action_rank(f["analyst_action"]) >= INVESTIGATED_RANK).astype(float)
    return f
