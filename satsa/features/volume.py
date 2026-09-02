"""Alert volume relative to asset criticality and to the entity's own history."""

from __future__ import annotations

import numpy as np

from satsa.features.base import SEVS, EntityContext, FeatureMeta, FeatureValue, fv, norm_entropy, rate
from satsa.schema.enums import Category

META: list[FeatureMeta] = [
    FeatureMeta("alerts_per_asset_tier1", "Alerts per Tier-1 asset", "volume", "n(alerts on TIER1) / n(TIER1 assets)", 3, False, "alerts/asset"),
    FeatureMeta("alerts_per_asset_tier2", "Alerts per Tier-2 asset", "volume", "n(alerts on TIER2) / n(TIER2 assets)", 3, False, "alerts/asset"),
    FeatureMeta("alerts_per_asset_tier3", "Alerts per Tier-3 asset", "volume", "n(alerts on TIER3) / n(TIER3 assets)", 3, False, "alerts/asset"),
    FeatureMeta("criticality_volume_ratio", "Tier-1 vs Tier-3 monitoring ratio", "volume", "alerts_per_asset_tier1 / alerts_per_asset_tier3", 3, False, headline=True),
    FeatureMeta("alerts_per_documented_asset", "Alerts per documented asset", "volume", "n / documented_asset_count", 1, False, "alerts/asset"),
    FeatureMeta("volume_delta_pct", "Volume change vs previous period", "volume", "(n - n_prev) / n_prev", 1, False, headline=True),
    FeatureMeta("volume_z_vs_self", "Volume z-score vs own history", "volume", "(n - mean(prev 3)) / std(prev 3)", 3, False),
    FeatureMeta("category_count", "Distinct categories", "volume", "count(distinct category)", 1, False, "categories"),
    FeatureMeta("category_entropy", "Category diversity", "volume", "normalised entropy of category distribution", 20, False),
] + [FeatureMeta(f"severity_dist_{s.lower()}", f"{s.title()} share", "volume", f"n({s}) / n", 20, s == "CRITICAL") for s in SEVS]


def compute(ctx: EntityContext) -> dict[str, FeatureValue]:
    a = ctx.alerts
    n = len(a)
    out: dict[str, FeatureValue] = {}
    per_tier: dict[str, float | None] = {}
    if len(ctx.assets):
        counts = a.groupby("asset_id").size()
        for tier in ("TIER1", "TIER2", "TIER3"):
            ids = ctx.assets[ctx.assets["criticality_tier"] == tier]["asset_id"].astype(str)
            val = float(counts.reindex(ids).fillna(0).mean()) if len(ids) else None
            per_tier[tier] = val
            out[f"alerts_per_asset_{tier.lower()}"] = fv(val, len(ids), 3)
    else:
        for tier in ("TIER1", "TIER2", "TIER3"):
            out[f"alerts_per_asset_{tier.lower()}"] = fv(None, 0)
    t1, t3 = per_tier.get("TIER1"), per_tier.get("TIER3")
    ratio = None if t1 is None or t3 is None else t1 / max(t3, 0.05)
    out["criticality_volume_ratio"] = fv(ratio, int(out["alerts_per_asset_tier1"].n), 3)

    documented = ctx.entity.get("documented_asset_count")
    out["alerts_per_documented_asset"] = fv(rate(n, documented) if documented else None, n)

    prior_counts = [len(ctx.history_for(p)) for p in ctx.prior_periods]
    if prior_counts:
        prev = prior_counts[-1]
        out["volume_delta_pct"] = fv(rate(n - prev, prev) if prev else None, prev)
    else:
        out["volume_delta_pct"] = fv(None, 0)
    if len(prior_counts) >= 3:
        arr = np.array(prior_counts[-3:], dtype=float)
        sd = arr.std(ddof=0)
        out["volume_z_vs_self"] = fv((n - arr.mean()) / sd if sd > 0 else None, 3, 3)
    else:
        out["volume_z_vs_self"] = fv(None, len(prior_counts))

    cats = a["category"].dropna()
    out["category_count"] = fv(cats.nunique(), n)
    out["category_entropy"] = fv(norm_entropy(cats.value_counts(), len(Category) - 1) if n else None, n, 20)
    for s in SEVS:
        out[f"severity_dist_{s.lower()}"] = fv(rate((a["severity"] == s).sum(), n), n, 20)
    ctx.extras["prior_period_counts"] = dict(zip(ctx.prior_periods, prior_counts))
    return out
