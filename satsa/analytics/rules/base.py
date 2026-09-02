"""Rule engine primitives.

A Rule reads an entity's features, peer statistics and raw alerts, and returns a RuleResult
with a hit flag, a bounded score (how far past the threshold), structured evidence, optional
alert-level hits, and a rendered plain-language rationale.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from satsa.analytics.rules.templates import render
from satsa.config import Settings
from satsa.features.base import OK, EntityContext, FeatureValue


@dataclass
class AlertHit:
    alert_id: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleContext:
    entity: EntityContext
    features: dict[str, FeatureValue]
    peer: dict[str, dict[str, float | None]]  # feature -> {z, pct, median, p10, p90, n}
    settings: Settings
    aux: dict[str, Any] = field(default_factory=dict)  # module-provided context (peer categories, expected volume ...)

    def f(self, name: str) -> FeatureValue | None:
        return self.features.get(name)

    def val(self, name: str) -> float | None:
        v = self.features.get(name)
        return None if v is None or v.value is None else v.value

    def ok(self, name: str) -> bool:
        v = self.features.get(name)
        return v is not None and v.value is not None and v.flag == OK

    def n(self, name: str) -> int:
        v = self.features.get(name)
        return 0 if v is None else v.n

    def peer_stat(self, name: str, key: str) -> float | None:
        return (self.peer.get(name) or {}).get(key)

    def peer_median(self, name: str) -> float | None:
        return self.peer_stat(name, "median")

    def z(self, name: str) -> float | None:
        return self.peer_stat(name, "z")


@dataclass
class RuleResult:
    rule_id: str
    rule_version: str
    name: str
    control_id: str
    capability: str
    scope: str
    hit: bool
    score: float
    prior_weight: float
    evidence: dict[str, Any] = field(default_factory=dict)
    alert_hits: list[AlertHit] = field(default_factory=list)
    rationale: str = ""
    suppressed: str | None = None  # e.g. LOW_N, DISABLED, MISSING

    @property
    def weighted(self) -> float:
        return self.prior_weight * self.score if self.hit else 0.0


def score_past(value: float | None, threshold: float, higher_is_worse: bool = True) -> float:
    """0.5 at the threshold, 1.0 at twice the distance from zero; 0 when not past it."""
    if value is None or threshold == 0:
        return 0.0
    excess = (value - threshold) / abs(threshold) if higher_is_worse else (threshold - value) / abs(threshold)
    if excess < 0:
        return 0.0
    return float(min(1.0, 0.5 + 0.5 * excess))


class Rule:
    id: str = ""
    version: str = "1"
    scope: str = "entity"  # entity | alert | asset
    name: str = ""

    def __init__(self, settings: Settings) -> None:
        cfg = settings.rule(self.id)
        self.params: dict[str, Any] = dict(cfg.get("params") or {})
        self.control_id: str = cfg.get("control_id", "CTRL-INV")
        self.capability: str = cfg.get("capability", "Investigation")
        self.prior_weight: float = float(cfg.get("prior_weight", 0.5))
        self.enabled: bool = bool(cfg.get("enabled", True))
        self.name = cfg.get("name", self.name or self.id)

    def p(self, key: str, default: Any = None) -> Any:
        return self.params.get(key, default)

    def evaluate(self, rc: RuleContext) -> RuleResult:  # pragma: no cover - abstract
        raise NotImplementedError

    def result(
        self,
        rc: RuleContext,
        hit: bool,
        score: float,
        evidence: dict[str, Any],
        alert_hits: list[AlertHit] | None = None,
        suppressed: str | None = None,
    ) -> RuleResult:
        ev = {"entity_id": rc.entity.entity_id, "period": rc.entity.period, **evidence}
        return RuleResult(
            rule_id=self.id, rule_version=self.version, name=self.name, control_id=self.control_id,
            capability=self.capability, scope=self.scope, hit=hit, score=float(max(0.0, min(1.0, score))),
            prior_weight=self.prior_weight, evidence=ev, alert_hits=alert_hits or [],
            rationale=render(self.id, ev) if hit else "", suppressed=suppressed,
        )

    def suppressed(self, rc: RuleContext, reason: str, evidence: dict[str, Any] | None = None) -> RuleResult:
        return self.result(rc, False, 0.0, evidence or {}, suppressed=reason)

    @staticmethod
    def peer_block(rc: RuleContext, *names: str) -> dict[str, Any]:
        """Evidence snippet: value vs peer median / p10 / p90 / z for the named features."""
        out = {}
        for n in names:
            v = rc.f(n)
            out[n] = {
                "value": None if v is None else v.value, "n": 0 if v is None else v.n, "flag": None if v is None else v.flag,
                "peer_median": rc.peer_median(n), "p10": rc.peer_stat(n, "p10"), "p90": rc.peer_stat(n, "p90"),
                "z": rc.z(n), "pct": rc.peer_stat(n, "pct"),
            }
        return out
