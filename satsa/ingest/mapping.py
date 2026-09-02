"""Column mapping and value normalisation from a source export to the canonical schema."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from satsa.config import Settings
from satsa.schema.enums import (
    ACTION_ALIASES,
    CATEGORY_ALIASES,
    CLOSURE_ALIASES,
    SEVERITY_ALIASES,
    AnalystAction,
    AssetClass,
    Category,
    ClosureReason,
    Criticality,
    Sector,
    Severity,
    SizeBand,
    normalise,
)

TRUE_VALUES = {"true", "1", "yes", "y", "t"}
FALSE_VALUES = {"false", "0", "no", "n", "f", ""}


@lru_cache(maxsize=16)
def load_mapping(config_dir: Path, name: str = "generic_csv") -> dict[str, Any]:
    path = Path(config_dir) / "schema_mappings" / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"schema mapping '{name}' not found at {path}")
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _rename(df: pd.DataFrame, columns: dict[str, list[str]]) -> tuple[pd.DataFrame, list[str]]:
    """Rename source columns to canonical names using the alias lists; report the leftovers."""
    lower_to_actual = {c.lower(): c for c in df.columns}
    rename: dict[str, str] = {}
    for canonical, aliases in columns.items():
        candidates = [canonical, *(aliases or [])]
        for cand in candidates:
            actual = lower_to_actual.get(str(cand).lower())
            if actual is not None and actual not in rename:
                rename[actual] = canonical
                break
    out = df.rename(columns=rename)
    unmapped = [c for c in df.columns if c not in rename]
    return out, unmapped


def _to_bool(series: pd.Series, default: bool | None) -> pd.Series:
    def conv(v: Any) -> bool | None:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return default
        s = str(v).strip().lower()
        if s in TRUE_VALUES:
            return True
        if s in FALSE_VALUES:
            return default if s == "" else False
        return default

    return series.map(conv).astype(object)


def _apply_value_map(series: pd.Series, custom: dict[str, str] | None, aliases: dict, default: Any) -> pd.Series:
    custom_lower = {str(k).strip().lower(): v for k, v in (custom or {}).items()}

    def conv(v: Any) -> Any:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return default
        key = str(v).strip().lower()
        if key in custom_lower:
            v = custom_lower[key]
        return normalise(v, aliases, default) if default is not None else _normalise_or_none(v, aliases)

    return series.map(conv).astype(object)


def _normalise_or_none(v: Any, aliases: dict) -> Any:
    key = str(v).strip().lower()
    if key in aliases:
        return aliases[key]
    sample = next(iter(aliases.values()))
    for member in type(sample):
        if key == member.value.lower():
            return member
    return None


def map_alerts(df: pd.DataFrame, mapping: dict[str, Any]) -> tuple[pd.DataFrame, list[str]]:
    table = (mapping.get("tables") or {}).get("alerts") or {}
    out, unmapped = _rename(df, table.get("columns") or {})

    for col in ("severity", "category"):
        if col in out.columns:
            out[f"_raw_{col}"] = out[col]
    if "severity" in out.columns:
        out["severity"] = _apply_value_map(out["severity"], table.get("severity_map"), SEVERITY_ALIASES, None)
    if "category" in out.columns:
        out["category"] = _apply_value_map(out["category"], table.get("category_map"), CATEGORY_ALIASES, Category.UNKNOWN)
    if "analyst_action" in out.columns:
        out["analyst_action"] = _apply_value_map(out["analyst_action"], table.get("action_map"), ACTION_ALIASES, AnalystAction.NONE)
    else:
        out["analyst_action"] = AnalystAction.NONE
    if "closure_reason" in out.columns:
        out["closure_reason"] = _apply_value_map(out["closure_reason"], table.get("closure_map"), CLOSURE_ALIASES, None)
    if "escalation_flag" in out.columns:
        out["escalation_flag"] = _to_bool(out["escalation_flag"], False).map(bool).astype(bool)
    else:
        out["escalation_flag"] = False
    if "root_cause_flag" in out.columns:
        out["root_cause_flag"] = _to_bool(out["root_cause_flag"], None)
    if "time_to_close_min" in out.columns:
        out["time_to_close_min"] = pd.to_numeric(out["time_to_close_min"], errors="coerce")
    return out, unmapped


def map_assets(df: pd.DataFrame, mapping: dict[str, Any], settings: Settings) -> tuple[pd.DataFrame, list[str]]:
    table = (mapping.get("tables") or {}).get("assets") or {}
    out, unmapped = _rename(df, table.get("columns") or {})
    if "criticality_tier" in out.columns:
        out["criticality_tier"] = out["criticality_tier"].map(lambda v: _tier(v))
    else:
        out["criticality_tier"] = Criticality.TIER3
    if "asset_class" in out.columns:
        out["asset_class"] = out["asset_class"].map(lambda v: normalise(v, {}, AssetClass.OTHER))
    else:
        out["asset_class"] = AssetClass.OTHER
    defaults = settings.expected_categories.get("default_telemetry_sources") or {}

    def sources(row: pd.Series) -> list[str]:
        v = row.get("expected_telemetry_sources")
        if isinstance(v, list) and v:
            return [str(x).strip() for x in v if str(x).strip()]
        if isinstance(v, str) and v.strip():
            return [x.strip() for x in v.replace(";", ",").replace("|", ",").split(",") if x.strip()]
        return list(defaults.get(row["asset_class"].value, []))

    out["expected_telemetry_sources"] = out.apply(sources, axis=1)
    return out, unmapped


def map_entities(df: pd.DataFrame, mapping: dict[str, Any]) -> tuple[pd.DataFrame, list[str]]:
    table = (mapping.get("tables") or {}).get("entities") or {}
    out, unmapped = _rename(df, table.get("columns") or {})
    if "sector" in out.columns:
        out["sector"] = out["sector"].map(lambda v: normalise(v, {}, Sector.GOVT))
    if "size_band" in out.columns:
        out["size_band"] = out["size_band"].map(lambda v: normalise(v, {}, SizeBand.M))
    for col in ("documented_soc_tier", "documented_asset_count"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")
    return out, unmapped


def map_generic(df: pd.DataFrame, mapping: dict[str, Any], table_name: str) -> tuple[pd.DataFrame, list[str]]:
    table = (mapping.get("tables") or {}).get(table_name) or {}
    return _rename(df, table.get("columns") or {})


def _tier(v: Any) -> Criticality:
    if v is None:
        return Criticality.TIER3
    s = str(v).strip().upper().replace(" ", "").replace("-", "").replace("_", "")
    if s in {"TIER1", "1", "CRITICAL", "HIGH", "T1"}:
        return Criticality.TIER1
    if s in {"TIER2", "2", "MEDIUM", "IMPORTANT", "T2"}:
        return Criticality.TIER2
    return Criticality.TIER3
