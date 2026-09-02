"""Module B: Negative Space detection. Deterministic detectors expressed as NS rules, plus the
peer context they need (category prevalence, expected-volume model, class monitoring rates)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import HuberRegressor

from satsa.analytics.combine import noisy_or
from satsa.analytics.module_a_execution import rule_finding, severity_for
from satsa.analytics.rules.base import RuleContext, RuleResult
from satsa.analytics.rules.catalogue import build_catalogue, evaluate_all
from satsa.audit.hashing import new_id
from satsa.config import Settings
from satsa.db.repo import to_json
from satsa.features.build import FeatureBuildResult
from satsa.models.train import peer_view

SIZE_ORD = {"S": 1, "M": 2, "L": 3, "XL": 4}


@dataclass
class ModuleBResult:
    p_b: dict[str, float]
    findings: list[dict[str, Any]]
    aux: dict[str, Any]
    rule_results: dict[str, list[RuleResult]] = field(default_factory=dict)


def peer_category_share(fb: FeatureBuildResult) -> dict[str, float]:
    n = len(fb.contexts)
    counts: dict[str, int] = {}
    for ctx in fb.contexts.values():
        for c in ctx.extras.get("observed_categories") or []:
            counts[c] = counts.get(c, 0) + 1
    return {c: k / n for c, k in counts.items()} if n else {}


def peer_class_rates(fb: FeatureBuildResult, min_assets: int = 3) -> dict[str, float]:
    per: dict[str, list[float]] = {}
    for ctx in fb.contexts.values():
        for cls, info in (ctx.extras.get("alerts_per_asset_by_class") or {}).items():
            if info["n_assets"] >= min_assets:
                per.setdefault(cls, []).append(info["alerts_per_asset"])
    return {cls: float(np.median(v)) for cls, v in per.items() if len(v) >= 2}


def expected_volume(fb: FeatureBuildResult) -> dict[str, dict[str, Any]]:
    """Peer model of log(alert volume). Huber regression with >= 10 entities, else a peer-rate median."""
    rows = []
    for eid, ctx in fb.contexts.items():
        prev = ctx.extras.get("prior_period_counts") or {}
        rows.append({
            "entity_id": eid, "actual": len(ctx.alerts), "assets": ctx.entity.get("documented_asset_count") or len(ctx.assets) or 1,
            "n_tier1": int((ctx.assets["criticality_tier"] == "TIER1").sum()) if len(ctx.assets) else 0,
            "size": SIZE_ORD.get(str(ctx.entity.get("size_band")), 2), "prev": list(prev.values())[-1] if prev else np.nan,
        })
    if not rows:
        return {}
    df = pd.DataFrame(rows).set_index("entity_id")
    y = np.log1p(df["actual"].astype(float))
    if len(df) >= 10:
        X = np.column_stack([np.log1p(df["assets"].astype(float)), df["n_tier1"].astype(float), df["size"].astype(float), np.log1p(df["prev"].fillna(df["actual"]).astype(float))])
        pred = HuberRegressor().fit(X, y).predict(X)
        method = "huber_regression"
    else:
        rate = y - np.log1p(df["assets"].astype(float))
        pred = (float(np.median(rate)) + np.log1p(df["assets"].astype(float))).values
        method = "peer_median_rate"
    resid = y.values - pred
    sigma = max(1.4826 * float(np.median(np.abs(resid - np.median(resid)))), 0.25)
    out = {}
    for i, eid in enumerate(df.index):
        prev_v = df.loc[eid, "prev"]
        out[eid] = {"actual": int(df.loc[eid, "actual"]), "predicted": float(np.expm1(pred[i])), "sigma": sigma, "z": float(resid[i] / sigma), "method": method,
                    "inputs": {"documented_assets": int(df.loc[eid, "assets"]), "n_tier1": int(df.loc[eid, "n_tier1"]), "size_band": str(fb.contexts[eid].entity.get("size_band")), "previous_volume": None if pd.isna(prev_v) else int(prev_v)}}
    return out


def run_module_b(fb: FeatureBuildResult, settings: Settings, run_id: str) -> ModuleBResult:
    rules = build_catalogue(settings, "B")
    shared = {"peer_category_share": peer_category_share(fb), "peer_class_rates": peer_class_rates(fb)}
    vol = expected_volume(fb)
    p_b: dict[str, float] = {}
    findings: list[dict[str, Any]] = []
    rule_results: dict[str, list[RuleResult]] = {}
    for eid, ctx in fb.contexts.items():
        rc = RuleContext(ctx, fb.values[eid], peer_view(fb, eid), settings, {**shared, "expected_volume": vol.get(eid, {})})
        results = evaluate_all(rules, rc)
        rule_results[eid] = results
        hits = [r for r in results if r.hit]
        p = noisy_or([r.weighted for r in hits])
        p_b[eid] = p
        for rr in hits:
            findings.append(rule_finding(rr, rc, run_id, "B", "negative_space", rr.weighted))
        if hits:
            findings.append(combined_ns_finding(rc, run_id, p, hits, vol.get(eid, {})))
    return ModuleBResult(p_b, findings, {**shared, "expected_volume": vol}, rule_results)


def combined_ns_finding(rc: RuleContext, run_id: str, p: float, hits: list[RuleResult], vol: dict) -> dict[str, Any]:
    parts = [f"{h.rule_id} {h.name} (score {h.score:.2f})" for h in hits]
    control = max(hits, key=lambda h: h.weighted).control_id
    return {
        "finding_id": new_id("fnd_"), "run_id": run_id, "entity_id": rc.entity.entity_id, "submission_period": rc.entity.period,
        "module": "B", "finding_class": "negative_space", "source": "RULE", "rule_id": None, "rule_version": None, "control_id": control,
        "capability": hits[0].capability, "scope": "entity", "asset_id": None, "severity": severity_for(p), "p_rule": p, "p_ml": None, "p_final": p,
        "calibrated": False, "decision": None, "t_star": None, "band_low": None, "band_high": None, "expected_cost": None, "priority_rank": None,
        "title": "Negative space indicators",
        "rationale": f"Negative-space probability {p:.2f} for {rc.entity.entity_id} in {rc.entity.period}. Detectors fired: {'; '.join(parts)}.",
        "score_components_json": to_json({"p_b": p, "detectors": [{"rule_id": h.rule_id, "score": h.score, "weighted": h.weighted, "control_id": h.control_id} for h in hits], "expected_volume": vol}),
        "shap_json": None,
        "evidence_json": to_json({"alert_ids": [], "asset_ids": (rc.entity.extras.get("newly_silent_tier1_assets") or [])[:50], "rule": {"rules_fired": [h.rule_id for h in hits]}, "feature_snapshot": {}}),
        "n_evidence_alerts": 0,
    }
