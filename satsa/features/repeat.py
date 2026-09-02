"""Repeated alerts on the same asset that were neither dismissed nor fixed.

A repeat group is (asset, category) with k >= threshold alerts in the period. It is
"unaddressed" when no alert was REMEDIATED or ticketed *and* fewer than a quarter of its closures
dismissed the alert as FALSE_POSITIVE / BENIGN / DUPLICATE — i.e. the SOC kept closing the
same thing as "no action" without either tuning it out or fixing it.
"""

from __future__ import annotations

import pandas as pd

from satsa.features.base import EntityContext, FeatureMeta, FeatureValue, fv, rate

META: list[FeatureMeta] = [
    FeatureMeta("repeat_alert_rate", "Repeat-alert share", "repeat", "sum_{(asset,cat): k>=3} k / n", 20, True),
    FeatureMeta("repeat_no_remediation_rate", "Unaddressed repeat groups", "repeat", "n(repeat groups with no REMEDIATED/ticket and < 25% dismissed closures) / n(repeat groups)", 3, True, headline=True),
    FeatureMeta("repeat_no_remediation_critical_assets", "Tier-1 assets with unremediated repeats", "repeat", "count(TIER1 assets in unremediated repeat groups)", 1, True, "assets"),
    FeatureMeta("cross_period_repeat_rate", "Cross-period repeat share", "repeat", "n(groups present in >= 3 consecutive periods without REMEDIATED) / n(groups)", 3, True, headline=True),
]


DISMISSED = {"FALSE_POSITIVE", "BENIGN", "DUPLICATE"}


def _groups(df: pd.DataFrame) -> pd.DataFrame:
    d = df[df["asset_id"].notna()]
    if d.empty:
        return pd.DataFrame(columns=["asset_id", "category", "k", "remediated", "dismissed_share", "addressed"])
    g = d.groupby(["asset_id", "category"]).agg(
        k=("alert_id", "size"),
        remediated=("closure_reason", lambda s: (s == "REMEDIATED").any()),
        ticketed=("remediation_ticket_id", lambda s: s.notna().any()),
        dismissed_share=("closure_reason", lambda s: float(s.isin(DISMISSED).mean()) if len(s) else 0.0),
    ).reset_index()
    g["remediated"] = g["remediated"] | g["ticketed"]
    g["addressed"] = g["remediated"] | (g["dismissed_share"] >= 0.25)
    return g


def compute(ctx: EntityContext) -> dict[str, FeatureValue]:
    a = ctx.alerts
    n = len(a)
    params = ctx.settings.rule("EG-07").get("params", {})
    k_min = int(params.get("repeat_k", 3))
    k_min_t1 = int(params.get("repeat_k_tier1", 2))
    tier1 = set(ctx.assets[ctx.assets["criticality_tier"] == "TIER1"]["asset_id"].astype(str)) if len(ctx.assets) else set()

    g = _groups(a)
    g["threshold"] = g["asset_id"].astype(str).map(lambda x: k_min_t1 if x in tier1 else k_min)
    rep = g[g["k"] >= g["threshold"]]
    unrem = rep[~rep["addressed"]]

    out = {
        "repeat_alert_rate": fv(rate(rep["k"].sum(), n), n, 20),
        "repeat_no_remediation_rate": fv(rate(len(unrem), len(rep)), len(rep), 3),
        "repeat_no_remediation_critical_assets": fv(unrem["asset_id"].astype(str).isin(tier1).sum(), len(unrem)),
    }

    # Cross-period: same (asset, category) in this and the two prior periods, never remediated.
    prev = ctx.prior_periods[-2:]
    if len(prev) == 2 and len(g):
        keys_now = set(zip(g["asset_id"].astype(str), g["category"]))
        persist = keys_now
        for p in prev:
            hp = _groups(ctx.history_for(p))
            persist &= set(zip(hp["asset_id"].astype(str), hp["category"]))
        all_hist = pd.concat([ctx.alerts] + [ctx.history_for(p) for p in prev])
        rem_keys = set(zip(
            all_hist[all_hist["closure_reason"] == "REMEDIATED"]["asset_id"].astype(str),
            all_hist[all_hist["closure_reason"] == "REMEDIATED"]["category"],
        ))
        chronic = persist - rem_keys
        out["cross_period_repeat_rate"] = fv(rate(len(chronic), len(keys_now)), len(keys_now), 3)
        ctx.extras["chronic_repeat_groups"] = [{"asset_id": k[0], "category": k[1]} for k in sorted(chronic)][:50]
    else:
        out["cross_period_repeat_rate"] = fv(None, 0)

    ctx.extras["repeat_groups"] = [
        {"asset_id": str(r.asset_id), "category": r.category, "k": int(r.k), "remediated": bool(r.remediated), "dismissed_share": round(float(r.dismissed_share), 2), "addressed": bool(r.addressed), "tier1": str(r.asset_id) in tier1}
        for r in rep.sort_values("k", ascending=False).head(50).itertuples()
    ]
    return out
