"""Escalation discipline: ratios, latency, and whether escalations leave a record."""

from __future__ import annotations

from satsa.features.base import EntityContext, FeatureMeta, FeatureValue, fv, minutes_between, rate

NON_INCIDENT_CLOSURES = {"FALSE_POSITIVE", "DUPLICATE"}

META: list[FeatureMeta] = [
    FeatureMeta("escalation_ratio", "Escalation ratio", "escalation", "n(escalated) / n", 20, False, headline=True),
    FeatureMeta("escalation_ratio_critical", "Critical escalation ratio", "escalation", "n(escalated | CRITICAL) / n(CRITICAL)", 8, False, headline=True),
    FeatureMeta("critical_closed_no_escalation_rate", "Critical closed without escalation", "escalation", "n(CRITICAL closed, not escalated, reason not in {FP, DUP}) / n(CRITICAL closed)", 8, True, headline=True),
    FeatureMeta("escalation_latency_median", "Median escalation latency", "escalation", "median(escalated_at - ts)", 5, True, "min"),
    FeatureMeta("escalation_without_record_rate", "Escalations without record", "escalation", "n(escalated with no escalation row) / n(escalated)", 5, True),
    FeatureMeta("incident_link_rate", "Critical escalations linked to incident", "escalation", "n(CRITICAL escalated with incident_id) / n(CRITICAL escalated)", 5, False),
]


def compute(ctx: EntityContext) -> dict[str, FeatureValue]:
    a = ctx.alerts
    n = len(a)
    esc_flag = a["escalation_flag"].fillna(False).astype(bool)
    esc = a[esc_flag]
    crit = a[a["severity"] == "CRITICAL"]
    crit_esc = crit[crit["escalation_flag"].fillna(False).astype(bool)]
    crit_closed = crit[crit["closed_at"].notna()]
    no_esc = crit_closed[
        ~crit_closed["escalation_flag"].fillna(False).astype(bool)
        & ~crit_closed["closure_reason"].isin(NON_INCIDENT_CLOSURES)
    ]

    out = {
        "escalation_ratio": fv(rate(len(esc), n), n, 20),
        "escalation_ratio_critical": fv(rate(len(crit_esc), len(crit)), len(crit), 8),
        "critical_closed_no_escalation_rate": fv(rate(len(no_esc), len(crit_closed)), len(crit_closed), 8),
    }

    with_time = esc[esc["escalated_at"].notna()]
    lat = minutes_between(with_time["escalated_at"], with_time["ts"])
    out["escalation_latency_median"] = fv(lat.median() if len(lat) else None, len(lat), 5)

    recorded = set(ctx.escalations["alert_id"].astype(str)) if len(ctx.escalations) else set()
    missing = (~esc["alert_id"].astype(str).isin(recorded)).sum() if len(esc) else 0
    out["escalation_without_record_rate"] = fv(rate(missing, len(esc)), len(esc), 5)

    if len(ctx.escalations):
        linked = ctx.escalations[ctx.escalations["incident_id"].notna()]["alert_id"].astype(str)
        n_linked = crit_esc["alert_id"].astype(str).isin(set(linked)).sum()
    else:
        n_linked = 0
    out["incident_link_rate"] = fv(rate(n_linked, len(crit_esc)), len(crit_esc), 5)

    ctx.extras["critical_no_escalation_alert_ids"] = no_esc["alert_id"].astype(str).head(200).tolist()
    ctx.extras["escalated_without_record_alert_ids"] = (
        esc[~esc["alert_id"].astype(str).isin(recorded)]["alert_id"].astype(str).head(200).tolist() if len(esc) else []
    )
    return out
