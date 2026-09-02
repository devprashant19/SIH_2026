"""Peer grouping, robust z-scores and percentile ranks for every registered feature."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from satsa.config import Settings
from satsa.features.base import DEGENERATE, OK


@dataclass
class PeerAssignment:
    entity_id: str
    peer_group_id: str
    peer_level: int
    members: list[str]


def assign_peer_groups(entities: pd.DataFrame, settings: Settings) -> dict[str, PeerAssignment]:
    """Level 1 = sector+size, 2 = sector, 3 = global; fall back while the group is too small."""
    cfg = settings.peer_groups
    min_size = int(cfg.get("min_group_size", 4))
    levels = cfg.get("levels") or [{"id": 1, "group_by": ["sector", "size_band"]}, {"id": 2, "group_by": ["sector"]}, {"id": 3, "group_by": []}]
    out: dict[str, PeerAssignment] = {}
    for row in entities.itertuples():
        for level in levels:
            keys = level.get("group_by") or []
            if keys:
                mask = np.ones(len(entities), dtype=bool)
                for k in keys:
                    mask &= (entities[k] == getattr(row, k)).values
                members = entities.loc[mask, "entity_id"].astype(str).tolist()
                gid = "|".join([f"{k}={getattr(row, k)}" for k in keys])
            else:
                members = entities["entity_id"].astype(str).tolist()
                gid = "global"
            if len(members) >= min_size or level is levels[-1]:
                out[str(row.entity_id)] = PeerAssignment(str(row.entity_id), gid, int(level["id"]), members)
                break
    return out


def robust_z(values: pd.Series, settings: Settings) -> tuple[pd.Series, dict[str, float], str]:
    """Return (z per value, group stats, flag). Uses MAD, then IQR, else DEGENERATE (z=0)."""
    rz = settings.peer_groups.get("robust_z") or {}
    clip = float(rz.get("clip", 5.0))
    v = values.astype(float)
    ok = v.dropna()
    stats = {
        "n": int(len(ok)), "median": float(ok.median()) if len(ok) else None, "mean": float(ok.mean()) if len(ok) else None,
        "std": float(ok.std(ddof=0)) if len(ok) > 1 else None,
        "mad": float((ok - ok.median()).abs().median()) if len(ok) else None,
        "p10": float(ok.quantile(0.10)) if len(ok) else None, "p25": float(ok.quantile(0.25)) if len(ok) else None,
        "p75": float(ok.quantile(0.75)) if len(ok) else None, "p90": float(ok.quantile(0.90)) if len(ok) else None,
    }
    if len(ok) < 2:
        return pd.Series(np.nan, index=values.index), stats, DEGENERATE
    scale = float(rz.get("mad_scale", 1.4826)) * stats["mad"]
    flag = OK
    if scale == 0:
        iqr = stats["p75"] - stats["p25"]
        scale = iqr / float(rz.get("iqr_scale", 1.349))
    if scale == 0:
        return pd.Series(np.where(v.notna(), 0.0, np.nan), index=values.index), stats, DEGENERATE
    z = ((v - stats["median"]) / scale).clip(-clip, clip)
    return z, stats, flag


def percentile_rank(values: pd.Series) -> pd.Series:
    """(rank - 0.5) / n within the non-null values; ties share the average rank."""
    ok = values.dropna().astype(float)
    if ok.empty:
        return pd.Series(np.nan, index=values.index)
    ranks = ok.rank(method="average")
    pct = (ranks - 0.5) / len(ok)
    return pct.reindex(values.index)


def compute_peer_stats(
    feature_table: pd.DataFrame,
    support: dict[str, dict[str, str]],
    assignments: dict[str, PeerAssignment],
    feature_names: list[str],
    settings: Settings,
) -> tuple[dict[str, dict[str, float | None]], dict[str, dict[str, float | None]], dict[str, dict[str, str]], list[dict]]:
    """feature_table: index entity_id, columns = features (NaN where missing).
    support: entity -> feature -> flag; only OK values enter the group statistics.
    Returns (z per entity, percentile per entity, flags per entity, baseline rows)."""
    z_out: dict[str, dict[str, float | None]] = {e: {} for e in feature_table.index}
    p_out: dict[str, dict[str, float | None]] = {e: {} for e in feature_table.index}
    f_out: dict[str, dict[str, str]] = {e: {} for e in feature_table.index}
    baselines: list[dict] = []
    groups: dict[str, list[str]] = {}
    for e, asg in assignments.items():
        groups.setdefault(asg.peer_group_id, []).append(e)

    for gid, members in groups.items():
        members = [m for m in members if m in feature_table.index]
        level = assignments[members[0]].peer_level if members else None
        for feat in feature_names:
            if feat not in feature_table.columns:
                continue
            col = feature_table.loc[members, feat].copy()
            for m in members:
                if support.get(m, {}).get(feat, OK) != OK:
                    col[m] = np.nan
            z, stats, flag = robust_z(col, settings)
            pct = percentile_rank(col)
            for m in members:
                z_out[m][feat] = None if pd.isna(z[m]) else float(z[m])
                p_out[m][feat] = None if pd.isna(pct[m]) else float(pct[m])
                f_out[m][feat] = flag if support.get(m, {}).get(feat, OK) == OK else support[m][feat]
            baselines.append({"peer_group_id": gid, "peer_level": level, "feature": feat, "member_entity_ids": members, **stats})
    return z_out, p_out, f_out, baselines
