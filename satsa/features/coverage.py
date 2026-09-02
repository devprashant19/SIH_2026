"""Telemetry coverage and silent assets (the raw material of Negative Space)."""

from __future__ import annotations

import numpy as np

from satsa.features.base import EntityContext, FeatureMeta, FeatureValue, fv, rate


def _as_list(v) -> list[str]:
    """DuckDB returns VARCHAR[] as numpy arrays; adapters give lists; nulls give None."""
    if v is None:
        return []
    if isinstance(v, (list, tuple, np.ndarray)):
        return [str(x) for x in v]
    return [str(v)]

META: list[FeatureMeta] = [
    FeatureMeta("coverage_gap_score", "Telemetry coverage gap", "coverage", "1 - |observed ∩ expected sources| / |expected|", 1, True, headline=True),
    FeatureMeta("coverage_gap_score_tier1", "Tier-1 telemetry coverage gap", "coverage", "same, restricted to Tier-1 assets' expected sources", 1, True, headline=True),
    FeatureMeta("silent_asset_rate_tier1", "Silent Tier-1 assets", "coverage", "n(TIER1 assets with 0 alerts) / n(TIER1)", 3, True, headline=True),
    FeatureMeta("silent_asset_rate_tier1_hist", "Previously active, now silent Tier-1 assets", "coverage", "n(TIER1 with 0 alerts now and >=1 alert in >=2 of the prior 5 periods) / n(TIER1)", 3, True, headline=True),
    FeatureMeta("source_dropout_count", "Telemetry sources dropped", "coverage", "count(expected sources seen in any prior period, absent now)", 1, True, "sources"),
    FeatureMeta("unknown_asset_alert_rate", "Alerts on unknown assets", "coverage", "n(V-07) / n_rows", 1, True, headline=True),
    FeatureMeta("val_err_rate", "Validation error rate", "data_quality", "n(ERROR flags) / n_rows", 1, True, headline=True),
    FeatureMeta("val_warn_rate", "Validation warning rate", "data_quality", "n(WARN flags) / n_rows", 1, True, headline=True),
    FeatureMeta("val_missing_notes_rate", "Missing-notes warning rate", "data_quality", "n(V-12) / n_rows", 1, True),
]


def compute(ctx: EntityContext) -> dict[str, FeatureValue]:
    a = ctx.alerts
    assets = ctx.assets
    out: dict[str, FeatureValue] = {}

    def sources_of(frame) -> set[str]:
        s: set[str] = set()
        for v in frame["expected_telemetry_sources"]:
            s.update(_as_list(v))
        return s

    expected = sources_of(assets) if len(assets) else set()
    tier1_assets = assets[assets["criticality_tier"] == "TIER1"] if len(assets) else assets
    expected_t1 = sources_of(tier1_assets) if len(tier1_assets) else set()
    observed = set(a["source_system"].dropna().astype(str))

    out["coverage_gap_score"] = fv(1 - rate(len(observed & expected), len(expected)) if expected else None, len(expected))
    out["coverage_gap_score_tier1"] = fv(1 - rate(len(observed & expected_t1), len(expected_t1)) if expected_t1 else None, len(expected_t1))

    active = set(a["asset_id"].dropna().astype(str))
    t1_ids = set(tier1_assets["asset_id"].astype(str)) if len(tier1_assets) else set()
    silent = {x for x in t1_ids if x not in active}
    out["silent_asset_rate_tier1"] = fv(rate(len(silent), len(t1_ids)), len(t1_ids), 3)

    prior = ctx.prior_periods[-5:]
    newly_silent: set[str] = set()
    if prior:
        seen_counts = {x: 0 for x in silent}
        for p in prior:
            hp = set(ctx.history_for(p)["asset_id"].dropna().astype(str))
            for x in silent:
                if x in hp:
                    seen_counts[x] += 1
        newly_silent = {x for x, c in seen_counts.items() if c >= 2}
        out["silent_asset_rate_tier1_hist"] = fv(rate(len(newly_silent), len(t1_ids)), len(t1_ids), 3)
        seen_before = set(ctx.history["source_system"].dropna().astype(str))
        dropped = sorted((seen_before - observed) & expected)  # only sources assets actually declare
        out["source_dropout_count"] = fv(len(dropped), len(seen_before & expected))
    else:
        out["silent_asset_rate_tier1_hist"] = fv(None, 0)
        out["source_dropout_count"] = fv(None, 0)
        dropped = []

    v = ctx.validation
    n_rows = int(v.get("n_rows", 0))
    out["unknown_asset_alert_rate"] = fv(rate(v.get("V-07", 0), n_rows) if n_rows else 0.0, n_rows)
    out["val_err_rate"] = fv(rate(v.get("ERROR", 0), n_rows) if n_rows else 0.0, n_rows)
    out["val_warn_rate"] = fv(rate(v.get("WARN", 0), n_rows) if n_rows else 0.0, n_rows)
    out["val_missing_notes_rate"] = fv(rate(v.get("V-12", 0), n_rows) if n_rows else 0.0, n_rows)

    missing_sources = sorted(expected - observed)
    declaring = {}
    if len(assets):
        for r in assets.itertuples():
            for s in _as_list(r.expected_telemetry_sources):
                if s in missing_sources:
                    declaring.setdefault(s, []).append(str(r.asset_id))
    dropped_declaring = {}
    if len(assets):
        for r in assets.itertuples():
            for src in _as_list(r.expected_telemetry_sources):
                if src in dropped:
                    dropped_declaring.setdefault(src, []).append(str(r.asset_id))
    # How many alerts a dropped source "should" have produced: alerts on its declaring assets
    # divided by the mean number of sources those assets declare. Zero observed against a
    # large expectation is strong evidence; against a small one it is noise.
    dropped_expected: dict[str, float] = {}
    if dropped_declaring and len(a):
        per_asset = a.groupby("asset_id").size()
        n_sources = {str(r.asset_id): max(1, len(_as_list(r.expected_telemetry_sources))) for r in assets.itertuples()}
        for src, ids in dropped_declaring.items():
            dropped_expected[src] = float(sum(per_asset.get(i, 0) / n_sources[i] for i in ids))
    ctx.extras.update({
        "dropped_source_assets": {k: v[:20] for k, v in dropped_declaring.items()},
        "dropped_source_asset_counts": {k: len(v) for k, v in dropped_declaring.items()},
        "dropped_source_expected_alerts": {k: round(v, 1) for k, v in dropped_expected.items()},
        "expected_sources": sorted(expected),
        "observed_sources": sorted(observed),
        "missing_sources": missing_sources,
        "missing_source_assets": {s: ids[:20] for s, ids in declaring.items()},
        "dropped_sources": dropped,
        "silent_tier1_assets": sorted(silent)[:50],
        "newly_silent_tier1_assets": sorted(newly_silent)[:50],
        "category_counts": {str(k): int(n) for k, n in a["category"].value_counts().items()},
        "observed_categories": sorted(a["category"].dropna().astype(str).unique().tolist()),
    })
    if len(assets):
        per_class = {}
        counts = a.groupby("asset_id").size()
        for cls, grp in assets.groupby("asset_class"):
            ids = grp["asset_id"].astype(str)
            per_class[str(cls)] = {"n_assets": int(len(ids)), "alerts_per_asset": float(counts.reindex(ids).fillna(0).mean())}
        ctx.extras["alerts_per_asset_by_class"] = per_class
    return out
