"""Module A: Execution Gap detection = rules + unsupervised ensemble + calibration + combination."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from satsa.analytics.anomaly import alert_feature_frame
from satsa.analytics.combine import combine_rule_ml, noisy_or, rule_composite
from satsa.analytics.rules.base import RuleContext, RuleResult
from satsa.analytics.rules.catalogue import build_catalogue, evaluate_all
from satsa.audit.hashing import new_id
from satsa.config import Settings
from satsa.db.repo import to_json
from satsa.features.build import FeatureBuildResult
from satsa.features.notes import per_alert_template_similarity
from satsa.features.registry import REGISTRY
from satsa.models.registry import ModelBundle
from satsa.models.train import ensemble_frame, peer_view

MAX_EVIDENCE_IDS = 200


def severity_for(p: float) -> str:
    return "CRITICAL" if p >= 0.75 else "HIGH" if p >= 0.5 else "ELEVATED" if p >= 0.25 else "LOW"


@dataclass
class EntityScore:
    entity_id: str
    p_rule: float
    p_ml: float | None
    p_final: float
    calibrated: bool
    ml: dict[str, Any] | None = None
    per_control: dict[str, float] = field(default_factory=dict)
    rule_results: list[RuleResult] = field(default_factory=list)


@dataclass
class ModuleAResult:
    scores: dict[str, EntityScore]
    findings: list[dict[str, Any]]
    alert_flags: list[dict[str, Any]]
    ml_used: bool
    detectors: list[str]


def feature_snapshot(rc: RuleContext, names: list[str]) -> dict[str, dict]:
    out = {}
    for n in names:
        v = rc.f(n)
        if v is None:
            continue
        meta = REGISTRY.get(n)
        out[n] = {"value": v.value, "n": v.n, "flag": v.flag, "label": meta.label if meta else n, "higher_is_worse": meta.higher_is_worse if meta else True,
                  "peer_median": rc.peer_median(n), "p10": rc.peer_stat(n, "p10"), "p90": rc.peer_stat(n, "p90"), "z": rc.z(n), "pct": rc.peer_stat(n, "pct")}
    return out


def rule_finding(rr: RuleResult, rc: RuleContext, run_id: str, module: str, finding_class: str, p: float) -> dict[str, Any]:
    ids = [h.alert_id for h in rr.alert_hits][:MAX_EVIDENCE_IDS]
    features = rr.evidence.get("features") or {}
    for name, block in features.items():
        meta = REGISTRY.get(name)
        block.setdefault("label", meta.label if meta else name)
        block.setdefault("higher_is_worse", meta.higher_is_worse if meta else True)
    assets = sorted({str(h.detail.get("asset_id")) for h in rr.alert_hits if h.detail.get("asset_id")})[:50]
    return {
        "finding_id": new_id("fnd_"), "run_id": run_id, "entity_id": rc.entity.entity_id, "submission_period": rc.entity.period,
        "module": module, "finding_class": finding_class, "source": "RULE", "rule_id": rr.rule_id, "rule_version": rr.rule_version,
        "control_id": rr.control_id, "capability": rr.capability, "scope": rr.scope, "asset_id": None, "severity": severity_for(p),
        "p_rule": p, "p_ml": None, "p_final": p, "calibrated": False, "decision": None, "t_star": None, "band_low": None, "band_high": None,
        "expected_cost": None, "priority_rank": None, "title": rr.name, "rationale": rr.rationale,
        "score_components_json": to_json({"rule_score": rr.score, "prior_weight": rr.prior_weight, "weighted": rr.weighted}),
        "shap_json": None,
        "evidence_json": to_json({"alert_ids": ids, "n_alert_hits": len(rr.alert_hits), "asset_ids": assets,
                                  "rule": {k: v for k, v in rr.evidence.items() if k != "features"}, "feature_snapshot": features}),
        "n_evidence_alerts": len(ids),
    }


def run_module_a(fb: FeatureBuildResult, settings: Settings, bundle: ModelBundle | None, run_id: str) -> ModuleAResult:
    rules = build_catalogue(settings, "A")
    alpha = settings.pipeline.module_a_alpha
    scores: dict[str, EntityScore] = {}
    findings: list[dict[str, Any]] = []
    alert_flags: list[dict[str, Any]] = []

    ml_scores: dict[str, dict[str, Any]] = {}
    ml_used, detectors, calibrated = False, [], False
    if bundle is not None and bundle.available and len(fb.values) >= 2:
        ef = ensemble_frame(fb)
        es = bundle.ensemble.score(ef)
        p_ml_arr = bundle.calibrator_a.predict(es.s_ml) if bundle.calibrator_a is not None else es.s_ml
        calibrated = bool(bundle.calibrator_a is not None and bundle.calibrator_a.calibrated)
        for i, eid in enumerate(ef.index):
            ml_scores[eid] = {"s_if": float(es.s_if[i]), "s_lof": None if np.isnan(es.s_lof[i]) else float(es.s_lof[i]),
                              "s_hdb": None if np.isnan(es.s_hdb[i]) else float(es.s_hdb[i]), "s_ml": float(es.s_ml[i]), "p_ml": float(p_ml_arr[i]), "calibrated": calibrated}
        ml_used, detectors = True, es.detectors_used

    for eid, ctx in fb.contexts.items():
        rc = RuleContext(ctx, fb.values[eid], peer_view(fb, eid), settings)
        results = evaluate_all(rules, rc)
        p_rule, per_control = rule_composite(results)
        ml = ml_scores.get(eid)
        p_ml = ml["p_ml"] if ml else None
        p_final = combine_rule_ml(p_rule, p_ml, alpha)
        scores[eid] = EntityScore(eid, p_rule, p_ml, p_final, calibrated, ml, per_control, results)

        hits = [r for r in results if r.hit]
        for rr in hits:
            findings.append(rule_finding(rr, rc, run_id, "A", "execution_gap", rr.weighted))
        if hits or (p_ml is not None and p_ml >= settings.t_star("execution_gap")):
            findings.append(combined_finding(rc, run_id, scores[eid], hits))
        alert_flags += alert_level_flags(rc, results, bundle, run_id)

    return ModuleAResult(scores, findings, alert_flags, ml_used, detectors)


def combined_finding(rc: RuleContext, run_id: str, es: EntityScore, hits: list[RuleResult]) -> dict[str, Any]:
    signed = []
    for name in rc.features:
        z = rc.z(name)
        if z is None or name not in REGISTRY:
            continue
        s = z if REGISTRY[name].higher_is_worse else -z
        if s > 0:
            signed.append((name, s))
    top = sorted(signed, key=lambda kv: -kv[1])[:8]
    ids: list[str] = []
    for h in hits:
        ids += [a.alert_id for a in h.alert_hits]
    ids = list(dict.fromkeys(ids))[:MAX_EVIDENCE_IDS]
    parts = [f"{h.rule_id} {h.name} (score {h.score:.2f})" for h in hits]
    if es.p_ml is None:
        ml_text = "Machine-learning scoring was not available for this run."
    else:
        ml_text = f"The unsupervised ensemble scored this entity-period at {es.p_ml:.2f} ({'calibrated' if es.calibrated else 'uncalibrated'})."
    rationale = (f"Execution-gap probability {es.p_final:.2f} for {rc.entity.entity_id} in {rc.entity.period}. "
                 + (f"Rules fired: {'; '.join(parts)}. " if parts else "No deterministic rule fired. ") + ml_text)
    control = max(es.per_control, key=es.per_control.get) if es.per_control else "CTRL-INV"
    return {
        "finding_id": new_id("fnd_"), "run_id": run_id, "entity_id": rc.entity.entity_id, "submission_period": rc.entity.period,
        "module": "A", "finding_class": "execution_gap", "source": "COMBINED" if es.p_ml is not None else "RULE", "rule_id": None, "rule_version": None,
        "control_id": control, "capability": hits[0].capability if hits else "Investigation", "scope": "entity", "asset_id": None,
        "severity": severity_for(es.p_final), "p_rule": es.p_rule, "p_ml": es.p_ml, "p_final": es.p_final, "calibrated": es.calibrated,
        "decision": None, "t_star": None, "band_low": None, "band_high": None, "expected_cost": None, "priority_rank": None,
        "title": "Execution gap indicators", "rationale": rationale,
        "score_components_json": to_json({"p_rule": es.p_rule, "p_ml": es.p_ml, "p_final": es.p_final, "alpha": rc.settings.pipeline.module_a_alpha,
                                          "per_control": es.per_control, "rules": [{"rule_id": h.rule_id, "score": h.score, "weighted": h.weighted, "control_id": h.control_id} for h in hits],
                                          "ml": es.ml, "top_feature_deviations": [{"feature": n, "z": z} for n, z in top]}),
        "shap_json": None,
        "evidence_json": to_json({"alert_ids": ids, "asset_ids": [], "rule": {"rules_fired": [h.rule_id for h in hits]}, "feature_snapshot": feature_snapshot(rc, [n for n, _ in top])}),
        "n_evidence_alerts": len(ids),
    }


def alert_level_flags(rc: RuleContext, results: list[RuleResult], bundle: ModelBundle | None, run_id: str) -> list[dict[str, Any]]:
    """One row per alert with at least one rule hit or a top-3% ML anomaly score."""
    per_alert: dict[str, dict[str, Any]] = {}
    for rr in results:
        if not rr.hit:
            continue
        for h in rr.alert_hits:
            entry = per_alert.setdefault(h.alert_id, {"rule_ids": [], "weights": [], "details": {}})
            entry["rule_ids"].append(rr.rule_id)
            entry["weights"].append(rr.prior_weight)
            entry["details"][rr.rule_id] = h.detail

    ml: dict[str, float] = {}
    a = rc.entity.alerts
    if bundle is not None and bundle.alert_if is not None and len(a):
        f = alert_feature_frame(a, per_alert_template_similarity(a))
        s = bundle.alert_if.score(f)
        p = bundle.calibrator_alert.predict(s) if bundle.calibrator_alert is not None else s
        ml = dict(zip(a["alert_id"].astype(str), map(float, p)))
        cutoff = float(np.quantile(list(ml.values()), 0.97)) if len(ml) > 30 else 1.0
        for aid, v in ml.items():
            if v >= cutoff and aid not in per_alert:
                per_alert[aid] = {"rule_ids": [], "weights": [], "details": {"ml": {"score": round(v, 3)}}}

    rows = []
    for aid, e in per_alert.items():
        p_rules = noisy_or(e["weights"])
        p_ml = ml.get(aid)
        p_alert = 1 - (1 - p_rules) * (1 - 0.5 * p_ml) if p_ml is not None else p_rules
        source = "BOTH" if e["rule_ids"] and p_ml is not None and p_ml > 0.5 else ("RULE" if e["rule_ids"] else "ML")
        rationale = ("Flagged by " + ", ".join(e["rule_ids"]) if e["rule_ids"] else "Flagged by the alert-level anomaly model")
        if p_ml is not None:
            rationale += f"; anomaly score {p_ml:.2f}"
        rows.append({
            "flag_id": new_id("flg_"), "run_id": run_id, "entity_id": rc.entity.entity_id, "submission_period": rc.entity.period, "alert_id": aid,
            "rule_ids": e["rule_ids"], "flag_source": source, "p_alert": float(p_alert), "decision": None, "queue_rank": None, "queue_reason": None,
            "rationale": rationale + ".", "shap_json": None, "evidence_json": to_json({"details": e["details"], "p_rules": p_rules, "p_ml": p_ml}), "finding_id": None,
        })
    return rows
