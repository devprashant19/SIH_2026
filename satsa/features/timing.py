"""Closure-time distributions, acknowledgement latency, ack-only and batch-closure patterns."""

from __future__ import annotations

import numpy as np
import pandas as pd

from satsa.features.base import SEVS, EntityContext, FeatureMeta, FeatureValue, fv, minutes_between, rate

META: list[FeatureMeta] = [
    FeatureMeta("n_alerts", "Alerts", "timing", "count(alerts)", 1, False, "alerts", headline=True),
    FeatureMeta("n_closed", "Closed alerts", "timing", "count(closed_at not null)", 1, False, "alerts", headline=True),
    FeatureMeta("ack_latency_median", "Median acknowledgement latency", "timing", "median(acknowledged_at - ts)", 10, True, "min"),
    FeatureMeta("ack_only_rate", "Acknowledged-only rate", "timing", "n(action=ACKNOWLEDGED and not closed and not escalated) / n", 20, True, headline=True),
    FeatureMeta("ack_then_close_no_invest_rate", "Closed without substantive note", "timing", "n(closed and note < 20 chars) / n_closed", 20, True, headline=True),
    FeatureMeta("offhours_close_rate", "Off-hours closure share", "timing", "n(closed 00:00-06:00 or weekend) / n_closed", 20, True),
    FeatureMeta("batch_close_score", "Batch-closure score", "timing", "max over 10-min windows of closures / n_closed", 30, True, headline=True),
]
for sev in SEVS:
    s = sev.lower()
    META += [
        FeatureMeta(f"n_alerts_{s}", f"{sev.title()} alerts", "timing", f"count(severity={sev})", 1, False, "alerts", headline=sev in ("CRITICAL", "HIGH")),
        FeatureMeta(f"ttc_median_{s}", f"Median time to close ({sev.title()})", "timing", f"median(ttc | {sev}, closed)", 10, True, "min", headline=sev in ("CRITICAL", "HIGH")),
        FeatureMeta(f"ttc_p10_{s}", f"P10 time to close ({sev.title()})", "timing", "p10(ttc)", 10, False, "min"),
        FeatureMeta(f"ttc_p90_{s}", f"P90 time to close ({sev.title()})", "timing", "p90(ttc)", 10, True, "min"),
        FeatureMeta(f"ttc_cv_{s}", f"Closure-time variability ({sev.title()})", "timing", "std(ttc)/mean(ttc)", 15, False, headline=sev == "CRITICAL"),
        FeatureMeta(f"unclosed_rate_{s}", f"Unclosed rate ({sev.title()})", "timing", f"n(closed_at null | {sev}) / n", 10, True),
    ]
    if sev in ("CRITICAL", "HIGH", "MEDIUM"):
        META.append(FeatureMeta(f"fast_close_rate_{s}", f"Fast-closure rate ({sev.title()})", "timing", "n(ttc < tau_fast) / n_closed", 20, True, headline=sev != "MEDIUM"))


def compute(ctx: EntityContext) -> dict[str, FeatureValue]:
    a = ctx.alerts
    closed = ctx.closed
    n = len(a)
    out: dict[str, FeatureValue] = {"n_alerts": fv(n, n), "n_closed": fv(len(closed), len(closed))}
    taus = ctx.settings.features.fast_close_minutes

    for sev in SEVS:
        s = sev.lower()
        sub = a[a["severity"] == sev]
        subc = closed[(closed["severity"] == sev) & closed["time_to_close_min"].notna()]
        ttc = subc["time_to_close_min"].astype(float)
        m = len(ttc)
        out[f"n_alerts_{s}"] = fv(len(sub), len(sub))
        out[f"ttc_median_{s}"] = fv(ttc.median() if m else None, m, 10)
        out[f"ttc_p10_{s}"] = fv(ttc.quantile(0.10) if m else None, m, 10)
        out[f"ttc_p90_{s}"] = fv(ttc.quantile(0.90) if m else None, m, 10)
        out[f"ttc_cv_{s}"] = fv((ttc.std(ddof=0) / ttc.mean()) if m >= 2 and ttc.mean() > 0 else None, m, 15)
        out[f"unclosed_rate_{s}"] = fv(rate(sub["closed_at"].isna().sum(), len(sub)), len(sub), 10)
        if sev in taus:
            out[f"fast_close_rate_{s}"] = fv(rate((ttc < taus[sev]).sum(), m), m, 20)

    acked = a[a["acknowledged_at"].notna()]
    lat = minutes_between(acked["acknowledged_at"], acked["ts"])
    out["ack_latency_median"] = fv(lat.median() if len(lat) else None, len(lat), 10)

    ack_only = (a["analyst_action"] == "ACKNOWLEDGED") & a["closed_at"].isna() & ~a["escalation_flag"].fillna(False).astype(bool)
    out["ack_only_rate"] = fv(rate(ack_only.sum(), n), n, 20)

    notes = closed["investigation_notes"].fillna("").astype(str).str.strip()
    short = notes.str.len() < ctx.settings.features.min_note_chars
    out["ack_then_close_no_invest_rate"] = fv(rate(short.sum(), len(closed)), len(closed), 20)

    if len(closed):
        ct = pd.to_datetime(closed["closed_at"])
        off = (ct.dt.hour < 6) | (ct.dt.weekday >= 5)
        out["offhours_close_rate"] = fv(rate(off.sum(), len(closed)), len(closed), 20)
        window = ctx.settings.features.batch_window_minutes
        bins = ct.dt.floor(f"{window}min")
        out["batch_close_score"] = fv(rate(bins.value_counts().max(), len(closed)), len(closed), 30)
    else:
        out["offhours_close_rate"] = fv(None, 0)
        out["batch_close_score"] = fv(None, 0)
    return out


def ttc_histogram(ctx: EntityContext, sev: str, bins: list[float] | None = None) -> dict[str, list]:
    """Evidence helper for the UI: closure-time histogram for one severity."""
    bins = bins or [0, 5, 15, 30, 60, 120, 240, 480, 1440, 4320, float("inf")]
    sub = ctx.closed[(ctx.closed["severity"] == sev) & ctx.closed["time_to_close_min"].notna()]
    counts, _ = np.histogram(sub["time_to_close_min"].astype(float), bins=bins)
    return {"bins": bins[:-1], "counts": counts.tolist()}
