"""Rule engine tests: scoring helper, templates, and a positive/negative case per rule family."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest

from satsa.analytics.combine import combine_rule_ml, noisy_or, rule_composite
from satsa.analytics.module_d_prioritise import AUTO_CLEAR, AUTO_FLAG, MANUAL_REVIEW, apply_decisions, build_review_queue, decide
from satsa.analytics.rules.base import RuleContext, score_past
from satsa.analytics.rules.catalogue import build_catalogue, evaluate_all, rule_index
from satsa.analytics.rules.eg_rules import EG02FastClosure, EG03CriticalNoEscalation, EG08ClosureCollapse
from satsa.analytics.rules.ns_rules import NS01SilentCriticalAssets, NS03ExpectedCategoryAbsent, NS06BrokenSubmission
from satsa.analytics.rules.templates import TEMPLATES, render
from satsa.config import Settings
from satsa.features import registry
from satsa.features.base import EntityContext, FeatureValue

T0 = datetime(2026, 4, 10, 10, 0, 0)


def _alerts(rows: list[dict]) -> pd.DataFrame:
    base = {
        "alert_id": None, "entity_id": "E1", "submission_period": "2026-04", "ts": T0, "severity": "HIGH", "category": "malware",
        "asset_id": "A1", "source_system": "edr", "analyst_id": "an1", "analyst_action": "CLOSED", "acknowledged_at": T0 + timedelta(minutes=5),
        "investigated_at": T0 + timedelta(minutes=20), "closed_at": T0 + timedelta(minutes=60), "time_to_close_min": 60.0,
        "escalation_flag": False, "escalated_at": None, "closure_reason": "BENIGN", "investigation_notes": "Checked the host; benign scheduled task.",
        "root_cause_flag": None, "remediation_ticket_id": None, "rule_name": "malware_r1", "validation_flags": [],
    }
    return pd.DataFrame([dict(base, alert_id=f"A{i}", **r) for i, r in enumerate(rows)])


def _rc(settings: Settings, alerts: pd.DataFrame, features: dict[str, tuple[float | None, int, str]], extras: dict | None = None, aux: dict | None = None, assets: pd.DataFrame | None = None) -> RuleContext:
    ctx = EntityContext(
        entity_id="E1", period="2026-04", entity={"sector": "power", "size_band": "L", "documented_asset_count": 20}, alerts=alerts, history=alerts.iloc[0:0],
        prior_periods=[], assets=assets if assets is not None else pd.DataFrame({"asset_id": ["A1"], "entity_id": ["E1"], "criticality_tier": ["TIER1"], "asset_class": ["SCADA"], "expected_telemetry_sources": [["ot_ids"]]}),
        escalations=pd.DataFrame(columns=["alert_id", "incident_id"]), incidents=pd.DataFrame(), validation={"n_rows": len(alerts)}, global_alerts=alerts, settings=settings, extras=extras or {},
    )
    fv = {k: FeatureValue(v[0], v[1], v[2]) for k, v in features.items()}
    peer = {k: {"median": 0.1, "p10": 0.0, "p90": 0.3, "z": 1.0, "pct": 0.9} for k in features}
    return RuleContext(ctx, fv, peer, settings, aux or {})


def test_score_past_shape() -> None:
    assert score_past(0.1, 0.2) == 0.0
    assert score_past(0.2, 0.2) == pytest.approx(0.5)
    assert score_past(0.4, 0.2) == pytest.approx(1.0)
    assert score_past(0.1, 0.2, higher_is_worse=False) == pytest.approx(0.75)


def test_every_rule_has_template_and_config(settings: Settings) -> None:
    idx = rule_index(settings)
    assert len(idx) == 19
    for rid in idx:
        assert rid in TEMPLATES
    text = render("EG-03", {"n_hit": 4, "n": 10, "rate": 0.4, "top_reason": "BENIGN", "esc_ratio": 0.2, "peer_esc": 0.7, "sample_ids": ["A1", "A2"]})
    assert "4 of 10 closed critical alerts (40%)" in text and "70%" in text


def test_eg02_fast_closure_positive_and_negative(settings: Settings) -> None:
    fast = _alerts([{"severity": "CRITICAL", "time_to_close_min": 3.0}] * 12 + [{"severity": "CRITICAL", "time_to_close_min": 300.0}] * 10)
    rc = _rc(settings, fast, {"fast_close_rate_critical": (12 / 22, 22, "OK"), "fast_close_rate_high": (0.0, 30, "OK"), "ttc_median_critical": (150, 22, "OK"), "ttc_median_high": (150, 30, "OK")})
    r = EG02FastClosure(settings).evaluate(rc)
    assert r.hit and r.score > 0.5 and len(r.alert_hits) == 12 and "critical alerts were closed within 15 minutes" in r.rationale
    slow = _rc(settings, fast, {"fast_close_rate_critical": (0.05, 22, "OK"), "fast_close_rate_high": (0.02, 30, "OK")})
    assert not EG02FastClosure(settings).evaluate(slow).hit
    thin = _rc(settings, fast, {"fast_close_rate_critical": (0.9, 5, "LOW_N")})
    assert EG02FastClosure(settings).evaluate(thin).suppressed == "LOW_N"


def test_eg03_alert_hits_exclude_false_positives(settings: Settings) -> None:
    a = _alerts([{"severity": "CRITICAL", "closure_reason": "BENIGN"}] * 3 + [{"severity": "CRITICAL", "closure_reason": "FALSE_POSITIVE"}] * 2 + [{"severity": "CRITICAL", "escalation_flag": True, "closure_reason": "ESCALATED_TO_IR"}])
    rc = _rc(settings, a, {"critical_closed_no_escalation_rate": (0.5, 6, "OK"), "escalation_ratio_critical": (0.17, 6, "OK")})
    r = EG03CriticalNoEscalation(settings).evaluate(rc)
    assert r.hit and len(r.alert_hits) == 3 and all(h.detail["closure_reason"] == "BENIGN" for h in r.alert_hits)


def test_eg08_closure_collapse(settings: Settings) -> None:
    rc = _rc(settings, _alerts([{}] * 50), {"closure_reason_entropy": (0.2, 50, "OK"), "closure_reason_top_share": (0.9, 50, "OK"), "fp_rate_critical": (0.3, 12, "OK")}, extras={"closure_reason_top": "FALSE_POSITIVE"})
    r = EG08ClosureCollapse(settings).evaluate(rc)
    assert r.hit and "90% of closures use the single reason" in r.rationale
    healthy = _rc(settings, _alerts([{}] * 50), {"closure_reason_entropy": (0.8, 50, "OK"), "closure_reason_top_share": (0.4, 50, "OK"), "fp_rate_critical": (0.3, 12, "OK")})
    assert not EG08ClosureCollapse(settings).evaluate(healthy).hit


def test_ns01_silent_assets(settings: Settings) -> None:
    rc = _rc(settings, _alerts([{}]), {"silent_asset_rate_tier1": (0.3, 10, "OK"), "silent_asset_rate_tier1_hist": (0.3, 10, "OK")}, extras={"silent_tier1_assets": ["A1", "A2", "A3"], "newly_silent_tier1_assets": ["A1", "A2", "A3"]})
    r = NS01SilentCriticalAssets(settings).evaluate(rc)
    assert r.hit and "3 of 10 Tier-1 assets produced no alerts" in r.rationale
    quiet_ok = _rc(settings, _alerts([{}]), {"silent_asset_rate_tier1": (0.1, 10, "OK"), "silent_asset_rate_tier1_hist": (0.0, 10, "OK")}, extras={"silent_tier1_assets": ["A1"], "newly_silent_tier1_assets": []})
    assert not NS01SilentCriticalAssets(settings).evaluate(quiet_ok).hit


def test_ns03_missing_categories_uses_sector_and_peers(settings: Settings) -> None:
    observed = ["malware", "brute_force", "phishing", "recon", "config_change", "ot_anomaly", "privilege_escalation"]
    rc = _rc(settings, _alerts([{}] * 5), {"n_alerts": (5, 5, "OK")}, extras={"observed_categories": observed}, aux={"peer_category_share": {"lateral_movement": 0.9, "data_exfil": 0.8}})
    r = NS03ExpectedCategoryAbsent(settings).evaluate(rc)
    assert r.hit and set(r.evidence["missing"]) >= {"lateral_movement", "data_exfil"}
    full = _rc(settings, _alerts([{}] * 5), {"n_alerts": (5, 5, "OK")}, extras={"observed_categories": observed + ["lateral_movement", "data_exfil"]}, aux={"peer_category_share": {}})
    assert not NS03ExpectedCategoryAbsent(settings).evaluate(full).hit


def test_ns06_broken_submission(settings: Settings) -> None:
    rc = _rc(settings, _alerts([{}] * 10), {"n_alerts": (10, 10, "OK"), "val_err_rate": (0.2, 10, "OK"), "val_missing_notes_rate": (0.0, 10, "OK"), "unknown_asset_alert_rate": (0.0, 10, "OK")})
    r = NS06BrokenSubmission(settings).evaluate(rc)
    assert r.hit and "20% of rows with validation errors" in r.rationale
    empty = _rc(settings, _alerts([{}] * 0), {"n_alerts": (0, 0, "MISSING")})
    assert NS06BrokenSubmission(settings).evaluate(empty).score == 1.0


def test_catalogue_evaluates_all_with_disabled(settings: Settings) -> None:
    from satsa.config import load_settings

    s2 = load_settings(settings.config_dir, {"rules": {"rules": {"EG-04": {"enabled": False}}}})
    rc = _rc(s2, _alerts([{}] * 3), {})
    results = evaluate_all(build_catalogue(s2), rc)
    assert len(results) == 19
    assert next(r for r in results if r.rule_id == "EG-04").suppressed == "DISABLED"


def test_combination_math() -> None:
    assert noisy_or([0.5, 0.5]) == pytest.approx(0.75)
    assert combine_rule_ml(0.0, None, 0.6) == 0.0
    assert combine_rule_ml(1.0, 0.0, 0.6) == pytest.approx(1.0)
    assert 0.0 < combine_rule_ml(0.3, 0.3, 0.6) < 0.6
    assert combine_rule_ml(0.5, 0.5, 0.6) == pytest.approx(0.5)
    assert combine_rule_ml(0.8, 0.2, 0.6) > combine_rule_ml(0.2, 0.8, 0.6)  # rules weigh more than ML


def test_decisions_and_queue(settings: Settings) -> None:
    t = settings.t_star("execution_gap")
    assert decide(t + 0.2, t, 0.1) == AUTO_FLAG and decide(t - 0.2, t, 0.1) == AUTO_CLEAR and decide(t, t, 0.1) == MANUAL_REVIEW
    findings = [{"finding_class": "execution_gap", "p_final": p, "entity_id": "E1"} for p in (0.9, 0.22, 0.05)]
    apply_decisions(findings, settings)
    assert [f["decision"] for f in findings] == [AUTO_FLAG, MANUAL_REVIEW, AUTO_CLEAR]
    assert findings[1]["priority_rank"] == 1  # uncertain first
    flags = [{"entity_id": "E1", "rule_ids": [r], "p_alert": 0.9, "alert_id": f"a{i}"} for i, r in enumerate(["EG-02", "EG-02", "EG-05", "EG-05", "EG-05", "EG-03"])]
    build_review_queue(flags, settings)
    ranked = sorted((f for f in flags if f.get("queue_rank")), key=lambda f: f["queue_rank"])
    assert [f["rule_ids"][0] for f in ranked[:3]] == ["EG-02", "EG-03", "EG-05"]  # round-robin across rules


def test_registry_features_referenced_by_sri_exist(settings: Settings) -> None:
    for dim in settings.sri_dimensions().values():
        for sub in (dim.get("subs") or {}):
            assert sub in registry.REGISTRY, sub
