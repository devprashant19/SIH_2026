"""Canonical pydantic models. Every adapter emits these; every downstream module consumes them.

Cross-field consistency checks deliberately live in validation.py rather than here, so a
bad row is *recorded* (it is supervisory evidence) instead of silently rejected.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from satsa.schema.enums import (
    AnalystAction,
    AssetClass,
    Category,
    ClosureReason,
    Criticality,
    Sector,
    Severity,
    SizeBand,
)

PERIOD_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"

_strict = ConfigDict(extra="forbid", str_strip_whitespace=True, use_enum_values=False)


class Alert(BaseModel):
    model_config = _strict

    alert_id: str
    entity_id: str
    submission_period: str = Field(pattern=PERIOD_PATTERN)
    timestamp: datetime
    severity: Severity
    category: Category
    asset_id: str | None = None
    source_system: str | None = None
    analyst_id: str | None = None
    analyst_action: AnalystAction = AnalystAction.NONE
    acknowledged_at: datetime | None = None
    investigated_at: datetime | None = None
    closed_at: datetime | None = None
    time_to_close_min: float | None = None
    escalation_flag: bool = False
    escalated_at: datetime | None = None
    closure_reason: ClosureReason | None = None
    investigation_notes: str | None = None
    root_cause_flag: bool | None = None
    remediation_ticket_id: str | None = None
    rule_name: str | None = None


class Entity(BaseModel):
    model_config = _strict

    entity_id: str
    name: str
    sector: Sector
    size_band: SizeBand
    documented_soc_tier: int | None = Field(default=None, ge=1, le=3)
    documented_asset_count: int | None = Field(default=None, ge=0)


class Asset(BaseModel):
    model_config = _strict

    asset_id: str
    entity_id: str
    criticality_tier: Criticality
    asset_class: AssetClass
    expected_telemetry_sources: list[str] = Field(default_factory=list)
    hostname: str | None = None
    first_seen_period: str | None = Field(default=None, pattern=PERIOD_PATTERN)


class Escalation(BaseModel):
    model_config = _strict

    escalation_id: str
    entity_id: str
    alert_id: str
    submission_period: str = Field(pattern=PERIOD_PATTERN)
    raised_at: datetime
    acknowledged_by_ir_at: datetime | None = None
    incident_id: str | None = None
    outcome: str | None = None


class Incident(BaseModel):
    model_config = _strict

    incident_id: str
    entity_id: str
    submission_period: str = Field(pattern=PERIOD_PATTERN)
    opened_at: datetime
    closed_at: datetime | None = None
    severity: Severity
    root_cause: str | None = None
    linked_alert_ids: list[str] = Field(default_factory=list)


# Column sets used by adapters and validation.
ALERT_REQUIRED_COLUMNS = ("alert_id", "timestamp", "severity", "category")
ALERT_COLUMNS = tuple(Alert.model_fields.keys())
ASSET_COLUMNS = tuple(Asset.model_fields.keys())
ENTITY_COLUMNS = tuple(Entity.model_fields.keys())
