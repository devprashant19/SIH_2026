"""Score combination: noisy-OR within/across controls and the rule-vs-ML geometric blend."""

from __future__ import annotations

import math
from collections import defaultdict

from satsa.analytics.rules.base import RuleResult


def noisy_or(values: list[float]) -> float:
    prod = 1.0
    for v in values:
        prod *= 1.0 - max(0.0, min(1.0, v))
    return 1.0 - prod


def rule_composite(results: list[RuleResult]) -> tuple[float, dict[str, float]]:
    """Weighted rule score: max within a control (correlated rules), noisy-OR across controls.

    Returns (score, per-control contribution) so the rationale can show which controls drove it.
    """
    by_control: dict[str, list[float]] = defaultdict(list)
    for r in results:
        if r.hit:
            by_control[r.control_id].append(r.weighted)
    per_control = {c: max(v) for c, v in by_control.items()}
    return noisy_or(list(per_control.values())), per_control


def combine_rule_ml(p_rule: float, p_ml: float | None, alpha: float) -> float:
    """Geometric noisy-OR: 1 - (1-p_rule)^alpha * (1-p_ml)^(1-alpha). Monotone; both 1 -> 1.

    With no ML score the rule probability is returned unchanged.
    """
    if p_ml is None or (isinstance(p_ml, float) and math.isnan(p_ml)):
        return p_rule
    p_rule, p_ml = max(0.0, min(1.0, p_rule)), max(0.0, min(1.0, p_ml))
    return 1.0 - ((1.0 - p_rule) ** alpha) * ((1.0 - p_ml) ** (1.0 - alpha))
