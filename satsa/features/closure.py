"""Closure-reason distribution: entropy collapse and false-positive dominance signal rubber-stamping."""

from __future__ import annotations

import pandas as pd

from satsa.features.base import EntityContext, FeatureMeta, FeatureValue, fv, norm_entropy, rate
from satsa.schema.enums import ClosureReason

K_REASONS = len(ClosureReason)

META: list[FeatureMeta] = [
    FeatureMeta("closure_reason_entropy", "Closure-reason diversity", "closure", "-sum(p log2 p) / log2(k) over closure_reason", 20, False, headline=True),
    FeatureMeta("closure_reason_top_share", "Dominant closure reason share", "closure", "max(p_reason)", 20, True, headline=True),
    FeatureMeta("fp_rate", "False-positive closure rate", "closure", "p(FALSE_POSITIVE)", 20, True),
    FeatureMeta("fp_rate_critical", "False-positive rate on critical", "closure", "p(FALSE_POSITIVE | CRITICAL closed)", 8, True, headline=True),
    FeatureMeta("unknown_closure_rate", "Unknown/other closure rate", "closure", "p(UNKNOWN or OTHER or null)", 20, True),
    FeatureMeta("root_cause_rate", "Root cause recorded on remediated", "closure", "n(root_cause_flag | REMEDIATED) / n(REMEDIATED)", 5, False),
]


def compute(ctx: EntityContext) -> dict[str, FeatureValue]:
    closed = ctx.closed
    n = len(closed)
    reasons = closed["closure_reason"].fillna("UNKNOWN")
    counts = reasons.value_counts()
    out = {
        "closure_reason_entropy": fv(norm_entropy(counts, K_REASONS) if n else None, n, 20),
        "closure_reason_top_share": fv(rate(counts.max() if n else 0, n), n, 20),
        "fp_rate": fv(rate((reasons == "FALSE_POSITIVE").sum(), n), n, 20),
        "unknown_closure_rate": fv(rate(reasons.isin(["UNKNOWN", "OTHER"]).sum(), n), n, 20),
    }
    crit = closed[closed["severity"] == "CRITICAL"]
    out["fp_rate_critical"] = fv(rate((crit["closure_reason"] == "FALSE_POSITIVE").sum(), len(crit)), len(crit), 8)
    rem = closed[closed["closure_reason"] == "REMEDIATED"]
    out["root_cause_rate"] = fv(rate(rem["root_cause_flag"].map(lambda v: False if pd.isna(v) else bool(v)).sum(), len(rem)), len(rem), 5)

    ctx.extras["closure_reason_distribution"] = {str(k): int(v) for k, v in counts.items()}
    ctx.extras["closure_reason_top"] = str(counts.idxmax()) if n else None
    return out
