"""All rules, instantiated against the active configuration."""

from __future__ import annotations

from satsa.analytics.rules.base import Rule, RuleContext, RuleResult
from satsa.analytics.rules.eg_rules import EG_RULES
from satsa.analytics.rules.ns_rules import NS_RULES
from satsa.config import Settings

ALL_RULE_CLASSES = EG_RULES + NS_RULES


def build_catalogue(settings: Settings, module: str | None = None) -> list[Rule]:
    classes = {"A": EG_RULES, "B": NS_RULES}.get(module, ALL_RULE_CLASSES)
    return [cls(settings) for cls in classes]


def evaluate_all(rules: list[Rule], rc: RuleContext) -> list[RuleResult]:
    out: list[RuleResult] = []
    for rule in rules:
        if not rule.enabled:
            out.append(rule.suppressed(rc, "DISABLED"))
            continue
        out.append(rule.evaluate(rc))
    return out


def rule_index(settings: Settings) -> dict[str, dict]:
    """Static description of the catalogue for the API/UI."""
    return {
        r.id: {"rule_id": r.id, "version": r.version, "name": r.name, "scope": r.scope, "control_id": r.control_id,
               "capability": r.capability, "prior_weight": r.prior_weight, "enabled": r.enabled, "params": r.params}
        for r in build_catalogue(settings)
    }
