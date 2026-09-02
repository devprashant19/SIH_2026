"""Entity-period feature engineering. Every feature is (value, n, support flag) so downstream
rules, z-scores and models can refuse to act on thin evidence."""

from satsa.features.build import build_features, persist_features
from satsa.features.registry import REGISTRY, FeatureMeta

__all__ = ["REGISTRY", "FeatureMeta", "build_features", "persist_features"]
