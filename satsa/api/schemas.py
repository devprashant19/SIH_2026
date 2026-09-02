"""Request bodies and the small set of response models worth validating at the boundary.

Most read endpoints return dicts shaped by satsa/api/queries.py; the field names there are
the contract with dashboard/src/api/types.ts.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class FeedbackRequest(BaseModel):
    target_type: Literal["finding", "alert_flag"]
    target_id: str
    decision: Literal["ACCEPT", "REJECT", "DEFER"]
    reviewer_id: str = Field(min_length=1, max_length=80)
    note: str | None = Field(default=None, max_length=2000)


class BulkFeedbackRequest(BaseModel):
    items: list[FeedbackRequest] = Field(min_length=1, max_length=200)


class RecalibrateRequest(BaseModel):
    promote: bool = False


class PipelineRunRequest(BaseModel):
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    force: bool = False


class TrainRequest(BaseModel):
    periods: list[str] = Field(min_length=1)
    promote: bool = False


class ConfigUpdate(BaseModel):
    sri_weights: dict[str, Any] | None = None   # {dimensions: {name: {weight, subs?}}}
    costs: dict[str, Any] | None = None         # {band_halfwidth, classes: {cls: {C_FP, C_FN, band_halfwidth?}}}
    rules: dict[str, Any] | None = None         # {rule_id: {enabled?, prior_weight?, params?}}
    note: str | None = None
    saved_by: str = "supervisor"


class WhatIfRequest(BaseModel):
    period: str | None = None
    sri_weights: dict[str, float] | None = None  # dimension -> weight
    costs: dict[str, dict[str, float]] | None = None  # class -> {C_FP, C_FN, band_halfwidth?}


class HealthResponse(BaseModel):
    status: str
    app_version: str
    rules_version: str
    feature_version: str
    code_hash: str
    config_hash: str
    db_path: str
    active_models: dict[str, str]
