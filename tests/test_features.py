"""Feature unit tests on hand-built frames plus an integration check on seeded profiles."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from satsa.config import Settings, load_settings
from satsa.db.connection import Database
from satsa.features import closure, coverage, escalation, notes, peer, repeat, timing
from satsa.features.base import EntityContext
from satsa.features.build import build_features
from satsa.features.registry import FEATURE_NAMES, REGISTRY, feature_list_hash
from satsa.ingest.loader import ingest_path
from simulator.generate import generate_dataset

T0 = datetime(2026, 4, 10, 10, 0, 0)


def _alerts(rows: list[dict]) -> pd.DataFrame:
    base = {
        "alert_id": None, "entity_id": "E1", "submission_period": "2026-04", "ts": T0, "severity": "HIGH", "category": "malware",
        "asset_id": "A1", "source_system": "edr", "analyst_id": "an1", "analyst_action": "CLOSED", "acknowledged_at": T0 + timedelta(minutes=5),
        "investigated_at": T0 + timedelta(minutes=20), "closed_at": T0 + timedelta(minutes=60), "time_to_close_min": 60.0,
        "escalation_flag": False, "escalated_at": None, "closure_reason": "BENIGN", "investigation_notes": "Checked process tree on host; scheduled task matched change CHG-1234.",
        "root_cause_flag": None, "remediation_ticket_id": None, "rule_name": "malware_r1", "validation_flags": [],
    }
    out = []
    for i, r in enumerate(rows):
        d = dict(base, alert_id=f"A{i}")
        d.update(r)
        out.append(d)
    return pd.DataFrame(out)


def _ctx(settings: Settings, alerts: pd.DataFrame, assets: pd.DataFrame | None = None, history: pd.DataFrame | None = None, prior=None, escalations=None) -> EntityContext:
    assets = assets if assets is not None else pd.DataFrame({"asset_id": ["A1"], "entity_id": ["E1"], "criticality_tier": ["TIER1"], "asset_class": ["ENDPOINT"], "expected_telemetry_sources": [["edr", "av"]]})
    return EntityContext(
        entity_id="E1", period="2026-04", entity={"documented_asset_count": 10}, alerts=alerts,
        history=history if history is not None else alerts.iloc[0:0], prior_periods=prior or [], assets=assets,
        escalations=escalations if escalations is not None else pd.DataFrame(columns=["alert_id", "incident_id"]),
        incidents=pd.DataFrame(), validation={"n_rows": len(alerts), "ERROR": 0, "WARN": 2, "V-07": 1, "V-12": 1},
        global_alerts=alerts, settings=settings,
    )


def test_registry_is_consistent() -> None:
    assert len(FEATURE_NAMES) == len(set(FEATURE_NAMES)) > 60
    assert len(feature_list_hash()) == 64
    for m in REGISTRY.values():
        assert m.formula and m.label and m.min_n >= 1


def test_timing_fast_close_and_ack_only(settings: Settings) -> None:
    rows = [{"severity": "CRITICAL", "time_to_close_min": 3.0} for _ in range(5)] + [{"severity": "CRITICAL", "time_to_close_min": 300.0} for _ in range(5)]
    rows += [{"analyst_action": "ACKNOWLEDGED", "closed_at": None, "time_to_close_min": None} for _ in range(2)]
    f = timing.compute(_ctx(settings, _alerts(rows)))
    assert f["fast_close_rate_critical"].value == pytest.approx(0.5)
    assert f["fast_close_rate_critical"].flag == "LOW_N"  # 10 closed < min_n 20
    assert f["ack_only_rate"].value == pytest.approx(2 / 12)
    assert f["ttc_median_critical"].value == pytest.approx(151.5)


def test_escalation_features(settings: Settings) -> None:
    rows = [{"severity": "CRITICAL", "escalation_flag": True, "escalated_at": T0 + timedelta(minutes=30), "closure_reason": "ESCALATED_TO_IR"} for _ in range(3)]
    rows += [{"severity": "CRITICAL", "closure_reason": "BENIGN"} for _ in range(2)]
    rows += [{"severity": "CRITICAL", "closure_reason": "FALSE_POSITIVE"}]
    esc = pd.DataFrame({"alert_id": ["A0", "A1"], "incident_id": ["I1", None]})
    f = escalation.compute(_ctx(settings, _alerts(rows), escalations=esc))
    assert f["escalation_ratio_critical"].value == pytest.approx(0.5)
    assert f["critical_closed_no_escalation_rate"].value == pytest.approx(2 / 6)  # FP excluded
    assert f["escalation_without_record_rate"].value == pytest.approx(1 / 3)
    assert f["incident_link_rate"].value == pytest.approx(1 / 3)
    assert f["escalation_latency_median"].value == pytest.approx(30.0)


def test_closure_entropy_collapse(settings: Settings) -> None:
    diverse = _alerts([{"closure_reason": r} for r in ["FALSE_POSITIVE", "BENIGN", "REMEDIATED", "DUPLICATE", "OTHER", "NO_ACTION_REQUIRED"] * 4])
    collapsed = _alerts([{"closure_reason": "FALSE_POSITIVE"}] * 22 + [{"closure_reason": "BENIGN"}] * 2)
    fd = closure.compute(_ctx(settings, diverse))
    fc = closure.compute(_ctx(settings, collapsed))
    assert fd["closure_reason_entropy"].value > 0.8 > 0.5 > fc["closure_reason_entropy"].value
    assert fc["closure_reason_top_share"].value == pytest.approx(22 / 24)


def test_notes_template_detection(settings: Settings) -> None:
    templ = _alerts([{"investigation_notes": "Reviewed alert. No action required."}] * 30)
    import random

    from simulator.note_corpus import free_text_note

    rnd = random.Random(3)
    varied = _alerts([
        {"investigation_notes": free_text_note(rnd, category=c, asset=f"host-{i}", source="edr", rule=f"{c}_r1", ticket=None)}
        for i, c in enumerate(["malware", "phishing", "recon", "brute_force", "insider", "dos"] * 5)
    ])
    ft = notes.compute(_ctx(settings, templ))
    fvv = notes.compute(_ctx(settings, varied))
    assert ft["note_template_score"].value > 0.95
    assert ft["note_dup_cluster_share"].value == pytest.approx(1.0)
    assert ft["note_distinct_ratio"].value < 0.1
    assert fvv["note_template_score"].value < 0.7 < ft["note_template_score"].value
    assert fvv["note_distinct_ratio"].value > 0.9


def test_repeat_without_remediation(settings: Settings) -> None:
    rows = [{"asset_id": "A1", "category": "malware", "closure_reason": "NO_ACTION_REQUIRED"}] * 4
    rows += [{"asset_id": "A2", "category": "recon", "closure_reason": "REMEDIATED"}] * 3
    rows += [{"asset_id": "A3", "category": "recon"}]
    assets = pd.DataFrame({"asset_id": ["A1", "A2", "A3"], "entity_id": "E1", "criticality_tier": ["TIER1", "TIER3", "TIER3"], "asset_class": "ENDPOINT", "expected_telemetry_sources": [["edr"]] * 3})
    f = repeat.compute(_ctx(settings, _alerts(rows), assets=assets))
    assert f["repeat_no_remediation_rate"].value == pytest.approx(0.5)
    assert f["repeat_no_remediation_critical_assets"].value == 1
    assert f["repeat_alert_rate"].value == pytest.approx(7 / 8)


def test_coverage_and_silent_assets(settings: Settings) -> None:
    assets = pd.DataFrame({
        "asset_id": ["A1", "A2", "A3", "A4"], "entity_id": "E1", "criticality_tier": ["TIER1", "TIER1", "TIER1", "TIER3"],
        "asset_class": ["SCADA", "SCADA", "HMI", "ENDPOINT"], "expected_telemetry_sources": [["ot_ids", "syslog"], ["ot_ids", "syslog"], ["edr", "syslog"], ["edr", "av"]],
    })
    now = _alerts([{"asset_id": "A1", "source_system": "syslog"}, {"asset_id": "A4", "source_system": "edr"}])
    hist_rows = []
    for p in ("2026-01", "2026-02", "2026-03"):
        for aid in ("A1", "A2", "A3"):
            hist_rows.append({"asset_id": aid, "source_system": "ot_ids", "submission_period": p})
    hist = _alerts(hist_rows)
    f = coverage.compute(_ctx(settings, now, assets=assets, history=hist, prior=["2026-01", "2026-02", "2026-03"]))
    assert f["coverage_gap_score"].value == pytest.approx(1 - 2 / 4)  # observed {syslog, edr} of {ot_ids, syslog, edr, av}
    assert f["silent_asset_rate_tier1"].value == pytest.approx(2 / 3)
    assert f["silent_asset_rate_tier1_hist"].value == pytest.approx(2 / 3)
    assert f["source_dropout_count"].value == 1  # ot_ids
    assert f["unknown_asset_alert_rate"].value == pytest.approx(0.5)


def test_robust_z_and_fallback(settings: Settings) -> None:
    vals = pd.Series({"E1": 1.0, "E2": 1.1, "E3": 0.9, "E4": 5.0})
    z, stats, flag = peer.robust_z(vals, settings)
    assert flag == "OK" and z["E4"] == 5.0 and abs(z["E1"]) < 1  # clipped at +5
    const = pd.Series({"E1": 2.0, "E2": 2.0, "E3": 2.0})
    z2, _, flag2 = peer.robust_z(const, settings)
    assert flag2 == "DEGENERATE" and (z2 == 0).all()
    pct = peer.percentile_rank(vals)
    assert pct["E4"] == pytest.approx((4 - 0.5) / 4) and pct["E3"] == pytest.approx(0.5 / 4)


def test_peer_group_fallback(settings: Settings) -> None:
    ents = pd.DataFrame({"entity_id": [f"E{i}" for i in range(6)], "sector": ["power"] * 5 + ["govt"], "size_band": ["L", "L", "L", "L", "XL", "S"]})
    asg = peer.assign_peer_groups(ents, settings)
    assert asg["E0"].peer_level == 1 and len(asg["E0"].members) == 4
    assert asg["E4"].peer_level == 2 and len(asg["E4"].members) == 5  # XL alone -> sector
    assert asg["E5"].peer_level == 3 and len(asg["E5"].members) == 6  # govt alone -> global


@pytest.fixture(scope="module")
def seeded_db(tmp_path_factory: pytest.TempPathFactory) -> tuple[Settings, Database]:
    """E01 (healthy), E03 (execution gap from period 3), E05 (silent assets from period 4), E06 (dirty) over 4 periods."""
    root = tmp_path_factory.mktemp("feat")
    settings = load_settings(Path(__file__).resolve().parent.parent / "config", {"paths": {"db_path": str(root / "db.duckdb"), "processed_dir": str(root / "processed")}})
    generate_dataset(settings, seed=11, out_dir=root / "syn", ground_truth_dir=root / "gt", periods=["2026-01", "2026-02", "2026-03", "2026-04"], entity_ids=["E01", "E03", "E05", "E06"])
    db = Database(settings.db_path)
    from satsa.db.migrate import apply_schema

    with db.write() as conn:
        apply_schema(conn)
    ingest_path(root / "syn", settings=settings, db=db)
    yield settings, db
    db.close()


def test_seeded_profiles_separate(seeded_db: tuple[Settings, Database]) -> None:
    settings, db = seeded_db
    with db.read() as conn:
        res = build_features(conn, settings, "2026-04", "run_test")
    v = res.values
    assert set(v) == {"E01", "E03", "E05", "E06"}
    assert res.seconds < 30
    # Execution gap: E03 templated notes and fast closes, E01 clean.
    assert v["E03"]["note_template_score"].value > 0.8 > 0.7 > v["E01"]["note_template_score"].value
    assert v["E03"]["fast_close_rate_critical"].value > 0.3 > v["E01"]["fast_close_rate_critical"].value
    assert v["E03"]["critical_closed_no_escalation_rate"].value > v["E01"]["critical_closed_no_escalation_rate"].value
    # Negative space: E05 newly silent tier-1 assets, E06 dirty data and low volume.
    assert v["E05"]["silent_asset_rate_tier1_hist"].value > 0.2 and v["E05"]["source_dropout_count"].value >= 1
    assert v["E01"]["silent_asset_rate_tier1_hist"].value == 0
    assert v["E06"]["unknown_asset_alert_rate"].value > 0.1 and v["E06"]["val_warn_rate"].value > v["E01"]["val_warn_rate"].value
    assert "lateral_movement" not in res.contexts["E06"].extras["observed_categories"]
    # Row shape and peer stats.
    assert len(res.rows) == 4 and res.rows["peer_level"].max() == 3
    assert not res.baselines.empty
    z = res.rows.set_index("entity_id")["peer_z_json"]
    import json

    assert json.loads(z["E03"])["note_template_score"] > 0
    assert all(c in res.rows.columns for c in ("features_json", "support_json", "peer_pct_json"))
    assert np.isfinite(res.rows["n_alerts"].astype(float)).all()
