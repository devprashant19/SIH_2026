"""Configuration loading.

All tunable behaviour lives in YAML files under ``config/`` (weights, costs, rule
thresholds, peer grouping, expected categories). This module merges them into one
``Settings`` object and computes ``config_hash`` so every pipeline run can record
exactly which configuration produced its findings.

Resolution order for the config directory:
  1. explicit ``config_dir`` argument
  2. ``SATSA_CONFIG_DIR`` environment variable
  3. ``<project root>/config``
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_DIR = PROJECT_ROOT / "config"

# Files merged into Settings.raw, keyed by the top-level section they populate.
CONFIG_FILES: dict[str, str] = {
    "default": "default.yaml",
    "sri_weights": "sri_weights.yaml",
    "rules": "rules.yaml",
    "costs": "costs.yaml",
    "peer_groups": "peer_groups.yaml",
    "expected_categories": "expected_categories.yaml",
}


class Paths(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data_dir: str = "data"
    db_path: str = "data/satsa.duckdb"
    incoming_dir: str = "data/incoming"
    processed_dir: str = "data/processed"
    synthetic_dir: str = "data/synthetic"
    ground_truth_dir: str = "data/ground_truth"
    models_dir: str = "models"
    reports_dir: str = "reports"
    logs_dir: str = "logs"
    dashboard_dist: str = "dashboard/dist"


class PipelineSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    explain_timeout_s: int = 120
    review_budget_per_entity: int = 25
    module_a_alpha: float = Field(0.6, ge=0.0, le=1.0)
    ml_weights: dict[str, float] = {"isolation_forest": 0.4, "lof": 0.3, "hdbscan": 0.3}
    min_rows_hdbscan: int = 15
    min_rows_lof: int = 5
    min_rows_alert_if_per_entity: int = 200
    negative_space_weights: dict[str, float] = {
        "volume": 0.5,
        "categories": 0.5,
        "coverage": 0.6,
        "silent_assets": 0.7,
        "records": 0.4,
        "low_activity": 0.5,
    }
    min_labels_for_calibration: int = 20
    min_labels_for_recalibration: int = 30


class FeatureSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fast_close_minutes: dict[str, float] = {"CRITICAL": 15, "HIGH": 10, "MEDIUM": 5}
    ack_stale_hours: float = 72
    batch_window_minutes: int = 10
    template_cosine_threshold: float = 0.92
    dup_cluster_cosine: float = 0.90
    dup_cluster_min_neighbours: int = 5
    min_note_chars: int = 20
    tfidf_global_fit_below_n: int = 200
    max_notes_for_similarity: int = 5000


class ImpactWeights(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default: float = 1.0
    sector: dict[str, float] = {}
    size_band: dict[str, float] = {}

    def weight(self, sector: str | None, size_band: str | None) -> float:
        return self.sector.get(sector or "", self.default) * self.size_band.get(size_band or "", 1.0)


class ApiSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173"]


class AppSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = "SAT-SA"
    seed: int = 42
    environment: str = "dev"


class Settings(BaseModel):
    """Typed view over the merged YAML configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    config_dir: Path
    config_hash: str
    app: AppSettings = AppSettings()
    paths: Paths = Paths()
    pipeline: PipelineSettings = PipelineSettings()
    features: FeatureSettings = FeatureSettings()
    impact_weights: ImpactWeights = ImpactWeights()
    api: ApiSettings = ApiSettings()
    # Loosely-typed sections consumed by the analytics modules; each module validates
    # what it needs at the point of use so a config error is reported with context.
    sri_weights: dict[str, Any] = {}
    rules: dict[str, Any] = {}
    costs: dict[str, Any] = {}
    peer_groups: dict[str, Any] = {}
    expected_categories: dict[str, Any] = {}

    # --- convenience -----------------------------------------------------------

    def resolve(self, relative: str) -> Path:
        """Resolve a path from config relative to the project root unless absolute."""
        p = Path(relative)
        return p if p.is_absolute() else PROJECT_ROOT / p

    @property
    def db_path(self) -> Path:
        return self.resolve(self.paths.db_path)

    def rule(self, rule_id: str) -> dict[str, Any]:
        """Return the config block for one rule, or an empty dict if not configured."""
        return dict((self.rules.get("rules") or {}).get(rule_id) or {})

    def rule_enabled(self, rule_id: str) -> bool:
        return bool(self.rule(rule_id).get("enabled", True))

    def cost(self, finding_class: str) -> tuple[float, float]:
        """(C_FP, C_FN) for a finding class, falling back to the default block."""
        classes = self.costs.get("classes") or {}
        block = classes.get(finding_class) or self.costs.get("default") or {"C_FP": 1.0, "C_FN": 3.0}
        return float(block["C_FP"]), float(block["C_FN"])

    def t_star(self, finding_class: str) -> float:
        """Cost-sensitive decision threshold t* = C_FP / (C_FP + C_FN)."""
        c_fp, c_fn = self.cost(finding_class)
        return c_fp / (c_fp + c_fn)

    def band_halfwidth(self, finding_class: str) -> float:
        classes = self.costs.get("classes") or {}
        block = classes.get(finding_class) or {}
        return float(block.get("band_halfwidth", self.costs.get("band_halfwidth", 0.10)))

    def sri_dimensions(self) -> dict[str, Any]:
        return dict(self.sri_weights.get("dimensions") or {})

    @property
    def weights_hash(self) -> str:
        return _hash_obj(self.sri_weights)


# --- loading ----------------------------------------------------------------------


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping at top level")
    return data


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _hash_obj(obj: Any) -> str:
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_raw_config(config_dir: Path | None = None, overrides: dict[str, Any] | None = None) -> tuple[Path, dict[str, Any]]:
    """Read every YAML in CONFIG_FILES and return (config_dir, merged dict)."""
    cfg_dir = Path(config_dir or os.environ.get("SATSA_CONFIG_DIR") or DEFAULT_CONFIG_DIR).resolve()
    merged: dict[str, Any] = {}
    for section, filename in CONFIG_FILES.items():
        data = _read_yaml(cfg_dir / filename)
        if section == "default":
            merged = _deep_merge(merged, data)
        else:
            merged[section] = data
    if overrides:
        merged = _deep_merge(merged, overrides)
    return cfg_dir, merged


def load_settings(config_dir: Path | None = None, overrides: dict[str, Any] | None = None) -> Settings:
    """Build a frozen Settings object. ``overrides`` is mainly for tests."""
    cfg_dir, raw = load_raw_config(config_dir, overrides)
    return Settings(config_dir=cfg_dir, config_hash=_hash_obj(raw), **raw)


_settings_cache: Settings | None = None


def get_settings() -> Settings:
    """Process-wide cached settings (FastAPI dependency and CLI entry points use this)."""
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = load_settings()
    return _settings_cache


def reset_settings_cache() -> None:
    global _settings_cache
    _settings_cache = None
