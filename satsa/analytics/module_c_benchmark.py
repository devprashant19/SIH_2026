"""Module C: the Supervisory Risk Indicator scorecard (transparent weighted sum) and priority."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from satsa.config import Settings
from satsa.db.repo import to_json
from satsa.features.build import FeatureBuildResult
from satsa.features.registry import REGISTRY

CAPABILITIES = ["Threat Detection", "Investigation", "Escalation", "Incident Response", "Security Operations", "Governance and Oversight", "Operational Discipline", "Cyber Resilience"]


def band_for(sri: float, settings: Settings) -> str:
    bands = settings.sri_weights.get("bands") or {"LOW": [0, 25], "ELEVATED": [25, 50], "HIGH": [50, 75], "CRITICAL": [75, 101]}
    for name, (lo, hi) in bands.items():
        if lo <= sri < hi:
            return name
    return "CRITICAL" if sri >= 75 else "LOW"


@dataclass
class SriRow:
    entity_id: str
    sri: float
    band: str
    confidence: float
    dims: dict[str, float]
    components: list[dict[str, Any]]
    capabilities: dict[str, float | None]
    priority_score: float
    sri_delta_prev: float | None


def _risky_percentile(pct: float, higher_is_worse: bool) -> float:
    return pct if higher_is_worse else 1.0 - pct


def score_entity(eid: str, fb: FeatureBuildResult, settings: Settings, p_a: float, p_b: float, prev_sri: float | None) -> SriRow:
    dims_cfg = settings.sri_dimensions()
    row = fb.rows[fb.rows["entity_id"] == eid].iloc[0]
    pct = json.loads(row["peer_pct_json"])
    support = json.loads(row["support_json"])
    feats = fb.values[eid]
    baselines = fb.baselines[fb.baselines["peer_group_id"] == fb.assignments[eid].peer_group_id] if len(fb.baselines) else fb.baselines
    medians = dict(zip(baselines["feature"], baselines["median"])) if len(baselines) else {}

    components: list[dict[str, Any]] = []
    dims: dict[str, float] = {}
    weak = total_subs = 0
    for name, cfg in dims_cfg.items():
        source = cfg.get("source")
        if source == "module_a_probability":
            dims[name] = 100.0 * p_a
            components.append({"dimension": name, "sub": "P(execution gap)", "raw": p_a, "percentile": None, "higher_is_worse": True, "weight": 1.0, "effective_weight": 1.0, "score": dims[name], "support": "OK", "peer_median": None})
        elif source == "module_b_probability":
            dims[name] = 100.0 * p_b
            components.append({"dimension": name, "sub": "P(negative space)", "raw": p_b, "percentile": None, "higher_is_worse": True, "weight": 1.0, "effective_weight": 1.0, "score": dims[name], "support": "OK", "peer_median": None})
        elif source == "trend_penalty":
            dims[name] = 0.0  # filled once the other dimensions are known
        else:
            subs = cfg.get("subs") or {}
            usable: dict[str, float] = {}
            for sub, w in subs.items():
                total_subs += 1
                flag = (support.get(sub) or {}).get("flag", "MISSING")
                if flag == "OK" and pct.get(sub) is not None:
                    usable[sub] = float(w)
                else:
                    weak += 1
            wsum = sum(usable.values())
            score = 0.0
            for sub, w in subs.items():
                meta = REGISTRY.get(sub)
                hiw = meta.higher_is_worse if meta else True
                p = pct.get(sub)
                eff = (usable[sub] / wsum) if sub in usable and wsum > 0 else 0.0
                s = 100.0 * _risky_percentile(p, hiw) if p is not None else None
                if s is not None and eff > 0:
                    score += eff * s
                components.append({"dimension": name, "sub": sub, "raw": feats[sub].value if sub in feats else None, "percentile": p, "higher_is_worse": hiw, "weight": float(w), "effective_weight": eff, "score": s, "support": (support.get(sub) or {}).get("flag"), "peer_median": medians.get(sub)})
            dims[name] = score

    base = sum(float(dims_cfg[d]["weight"]) * dims[d] for d in dims if dims_cfg[d].get("source") != "trend_penalty")
    delta = None if prev_sri is None else base - prev_sri
    for name, cfg in dims_cfg.items():
        if cfg.get("source") == "trend_penalty":
            dims[name] = 0.0 if delta is None else max(0.0, min(20.0, delta)) * 5.0
            components.append({"dimension": name, "sub": "SRI change vs previous period", "raw": delta, "percentile": None, "higher_is_worse": True, "weight": 1.0, "effective_weight": 1.0, "score": dims[name], "support": "OK" if delta is not None else "MISSING", "peer_median": None})
    sri = sum(float(dims_cfg[d]["weight"]) * dims[d] for d in dims)
    confidence = 1.0 - (weak / total_subs if total_subs else 0.0)

    caps: dict[str, list[float]] = {c: [] for c in CAPABILITIES}
    for name, cfg in dims_cfg.items():
        for c in cfg.get("capabilities") or []:
            caps.setdefault(c, []).append(dims[name])
    capabilities = {c: (sum(v) / len(v) if v else None) for c, v in caps.items()}
    ent = fb.contexts[eid].entity
    impact = settings.impact_weights.weight(str(ent.get("sector")), str(ent.get("size_band")))
    priority = (sri / 100.0) * (0.5 + 0.5 * confidence) * impact
    return SriRow(eid, sri, band_for(sri, settings), confidence, dims, components, capabilities, priority, delta)


def run_module_c(fb: FeatureBuildResult, settings: Settings, p_a: dict[str, float], p_b: dict[str, float], prev_sri: dict[str, float], run_id: str) -> tuple[list[dict[str, Any]], dict[str, SriRow]]:
    sri_rows = {eid: score_entity(eid, fb, settings, p_a.get(eid, 0.0), p_b.get(eid, 0.0), prev_sri.get(eid)) for eid in fb.values}
    rows_out = []
    for rank, r in enumerate(sorted(sri_rows.values(), key=lambda r: -r.priority_score), start=1):
        rows_out.append({
            "entity_id": r.entity_id, "submission_period": fb.period, "run_id": run_id, "sri": r.sri, "band": r.band, "confidence": r.confidence,
            "dim_execution_gap": r.dims.get("execution_gap"), "dim_negative_space": r.dims.get("negative_space"), "dim_escalation_discipline": r.dims.get("escalation_discipline"),
            "dim_investigation_quality": r.dims.get("investigation_quality"), "dim_data_integrity": r.dims.get("data_integrity"), "dim_trend_penalty": r.dims.get("trend_penalty"),
            "weights_hash": settings.weights_hash, "components_json": to_json(r.components), "capability_json": to_json(r.capabilities),
            "priority_score": r.priority_score, "priority_rank": rank, "sri_delta_prev": r.sri_delta_prev,
        })
    return rows_out, sri_rows
