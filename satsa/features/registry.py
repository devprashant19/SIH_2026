"""The feature registry: every feature's metadata (label, formula, min_n, direction) in one place.

Rules, the SRI scorecard, the peer-benchmark API and the dashboard all read this so that a
feature's meaning and risky direction are defined exactly once.
"""

from __future__ import annotations

import hashlib

from satsa.features import aact, closure, coverage, escalation, notes, repeat, timing, volume
from satsa.features.base import FeatureMeta

MODULES = [timing, escalation, closure, notes, repeat, coverage, volume, aact]

REGISTRY: dict[str, FeatureMeta] = {}
for _mod in MODULES:
    for _meta in _mod.META:
        if _meta.name in REGISTRY:
            raise RuntimeError(f"duplicate feature name {_meta.name}")
        REGISTRY[_meta.name] = _meta

FEATURE_NAMES: list[str] = list(REGISTRY)
HEADLINE_FEATURES: list[str] = [m.name for m in REGISTRY.values() if m.headline]


def feature_list_hash() -> str:
    """Changes whenever a feature is added, removed or renamed; pinned into trained models."""
    return hashlib.sha256("|".join(FEATURE_NAMES).encode()).hexdigest()


def meta(name: str) -> FeatureMeta:
    return REGISTRY[name]


def higher_is_worse(name: str) -> bool:
    return REGISTRY[name].higher_is_worse if name in REGISTRY else True
