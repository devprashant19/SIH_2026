"""Peer benchmarking, negative-space coverage and trend endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from satsa.api import queries as q
from satsa.api.deps import get_reader, get_settings_dep
from satsa.config import Settings
from satsa.features.registry import REGISTRY

router = APIRouter()


@router.get("/benchmark/metrics")
def benchmark_metrics() -> list[dict]:
    return [{"key": m.name, "label": m.label, "unit": m.unit, "higher_is_worse": m.higher_is_worse, "group": m.group, "formula": m.formula, "headline": m.headline} for m in REGISTRY.values()]


@router.get("/benchmark/rank")
def benchmark_rank(period: str | None = None, sector: str | None = None, features: str | None = None, conn=Depends(get_reader)) -> dict:
    feats = [f.strip() for f in features.split(",")] if features else None
    return q.benchmark_rank(conn, period, sector, feats)


@router.get("/benchmark")
def benchmark(feature: str, period: str | None = None, entity_id: str | None = None, peer_group: str | None = None, conn=Depends(get_reader)) -> dict:
    d = q.benchmark(conn, feature, period, entity_id, peer_group)
    if d is None:
        raise HTTPException(404, "unknown feature or no scored run")
    return d


@router.get("/coverage")
def coverage(period: str | None = None, sector: str | None = None, dimension: str = "category", conn=Depends(get_reader), settings: Settings = Depends(get_settings_dep)) -> dict:
    if dimension not in ("category", "asset_class", "source"):
        raise HTTPException(400, "dimension must be category, asset_class or source")
    return q.coverage_matrix(conn, settings, period, dimension, sector)


@router.get("/coverage/{entity_id}/{column}")
def coverage_cell(entity_id: str, column: str, period: str | None = None, dimension: str = "category", conn=Depends(get_reader), settings: Settings = Depends(get_settings_dep)) -> dict:
    return q.coverage_cell(conn, settings, entity_id, column, period, dimension)


@router.get("/trends/entities/{entity_id}")
def trends_entity(entity_id: str, start: str | None = None, end: str | None = None, conn=Depends(get_reader)) -> dict:
    return q.trend_entity(conn, entity_id, start, end)


@router.get("/trends/sector")
def trends_sector(sector: str | None = None, start: str | None = None, end: str | None = None, conn=Depends(get_reader)) -> dict:
    return q.trend_sector(conn, sector, start, end)


@router.get("/trends/controls")
def trends_controls(start: str | None = None, end: str | None = None, conn=Depends(get_reader), settings: Settings = Depends(get_settings_dep)) -> dict:
    return q.trend_controls(conn, settings, start, end)
