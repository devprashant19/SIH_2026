"""End-to-end: seed -> ingest -> train -> run, asserting the acceptance criteria on seeded profiles."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from satsa.audit.verify import verify_chain
from satsa.config import Settings, load_settings
from satsa.db.connection import Database
from satsa.db.migrate import apply_schema
from satsa.ingest.loader import ingest_path
from satsa.models.registry import load_active_bundle
from satsa.models.train import train_models
from satsa.pipeline.run import run_pipeline
from simulator.generate import generate_dataset

PERIODS = ["2026-01", "2026-02", "2026-03", "2026-04"]
ENTITIES = ["E01", "E02", "E03", "E05", "E06", "E07"]


@pytest.fixture(scope="module")
def pipeline_db(tmp_path_factory: pytest.TempPathFactory) -> tuple[Settings, Database]:
    root = tmp_path_factory.mktemp("pipe")
    settings = load_settings(Path(__file__).resolve().parent.parent / "config", {"paths": {
        "db_path": str(root / "db.duckdb"), "processed_dir": str(root / "processed"), "models_dir": str(root / "models"),
        "ground_truth_dir": str(root / "gt"), "logs_dir": str(root / "logs"),
    }, "pipeline": {"min_labels_for_calibration": 12}})
    generate_dataset(settings, seed=5, out_dir=root / "syn", ground_truth_dir=root / "gt", periods=PERIODS, entity_ids=ENTITIES)
    db = Database(settings.db_path)
    with db.write() as conn:
        apply_schema(conn)
    ingest_path(root / "syn", settings=settings, db=db)
    train_models(db, settings, PERIODS[:3], promote=True)
    yield settings, db
    db.close()


def _current(db: Database, period: str):
    with db.read() as conn:
        run_id = conn.execute("SELECT run_id FROM audit_runs WHERE run_type='PIPELINE' AND status='SUCCESS' AND submission_period=? ORDER BY finished_at DESC LIMIT 1", [period]).fetchone()[0]
        findings = conn.execute("SELECT entity_id, rule_id, decision, p_final, rationale, evidence_json, shap_json FROM findings WHERE run_id = ?", [run_id]).df()
        sri = conn.execute("SELECT entity_id, sri, band, priority_rank, confidence FROM sri_scores WHERE run_id = ? ORDER BY priority_rank", [run_id]).df()
        flags = conn.execute("SELECT entity_id, alert_id, rule_ids, decision, queue_rank FROM alert_sample_flags WHERE run_id = ?", [run_id]).df()
    return run_id, findings, sri, flags


def test_models_trained_and_active(pipeline_db: tuple[Settings, Database]) -> None:
    settings, db = pipeline_db
    with db.read() as conn:
        bundle = load_active_bundle(conn, settings)
    assert bundle.available and bundle.alert_if is not None
    assert bundle.calibrator_a is not None and bundle.calibrator_a.calibrated


def test_run_april_matches_ground_truth(pipeline_db: tuple[Settings, Database]) -> None:
    settings, db = pipeline_db
    for p in PERIODS:
        res = run_pipeline(p, settings=settings, db=db, triggered_by="test", trigger_source="test")
        assert res.status == "SUCCESS", res.error
    run_id, findings, sri, flags = _current(db, "2026-04")
    rules = findings.dropna(subset=["rule_id"]).groupby("entity_id")["rule_id"].apply(set).to_dict()
    assert {"EG-02", "EG-03", "EG-05"} <= rules.get("E03", set())
    assert {"NS-01", "NS-02"} <= rules.get("E05", set())
    assert {"NS-03", "NS-04", "NS-06"} <= rules.get("E06", set())
    auto = findings[findings["decision"] == "AUTO_FLAG"]
    assert not set(auto["entity_id"]) & {"E01", "E02", "E07"}, auto[["entity_id", "rule_id"]].to_string()
    order = list(sri["entity_id"])
    assert order.index("E03") < min(order.index(e) for e in ("E01", "E02", "E07"))
    e03_sri = float(sri[sri["entity_id"] == "E03"]["sri"].iloc[0])
    healthy = sri[sri["entity_id"].isin(["E01", "E02", "E07"])]
    assert sri[sri["entity_id"] == "E03"]["band"].iloc[0] in ("ELEVATED", "HIGH", "CRITICAL")
    assert e03_sri > float(healthy["sri"].max()) + 10
    assert set(healthy["band"]) <= {"LOW", "ELEVATED"}
    # explainability: every finding has a rationale and resolvable evidence; combined findings carry attributions
    assert findings["rationale"].str.len().gt(20).all()
    for ev in findings["evidence_json"]:
        json.loads(ev)
    combined = findings[findings["rule_id"].isna() & (findings["entity_id"] == "E03")]
    assert not combined.empty and combined["shap_json"].notna().all()
    payload = json.loads(combined["shap_json"].iloc[0])
    assert payload["method"] in ("shap_tree_isolation_forest", "zscore_attribution") and payload["contributions"]
    # review queue: budgeted per entity, ranks contiguous, covers more than one rule for E03
    q = flags.dropna(subset=["queue_rank"])
    assert q.groupby("entity_id")["queue_rank"].max().le(settings.pipeline.review_budget_per_entity).all()
    e03 = q[q["entity_id"] == "E03"]
    assert sorted(e03["queue_rank"]) == list(range(1, len(e03) + 1))
    assert len({r[0] for r in e03["rule_ids"] if len(r)}) >= 2


def test_idempotent_rerun_and_force(pipeline_db: tuple[Settings, Database]) -> None:
    settings, db = pipeline_db
    again = run_pipeline("2026-04", settings=settings, db=db, triggered_by="test", trigger_source="test")
    assert again.status == "SKIPPED_IDENTICAL"
    forced = run_pipeline("2026-04", settings=settings, db=db, force=True, triggered_by="test", trigger_source="test")
    assert forced.status == "SUCCESS"
    with db.read() as conn:
        hashes = conn.execute("SELECT output_hash FROM audit_runs WHERE run_type='PIPELINE' AND status='SUCCESS' AND submission_period='2026-04' ORDER BY finished_at DESC LIMIT 2").fetchall()
    assert hashes[0][0] == hashes[1][0], "forced rerun must reproduce the same outputs"


def test_audit_chain_verifies_and_detects_tampering(pipeline_db: tuple[Settings, Database]) -> None:
    settings, db = pipeline_db
    with db.read() as conn:
        assert verify_chain(conn).ok
    with db.write() as conn:
        rid = conn.execute("SELECT run_id FROM audit_runs WHERE status='SUCCESS' ORDER BY finished_at LIMIT 1").fetchone()[0]
        conn.execute("UPDATE audit_runs SET config_hash = 'tampered' WHERE run_id = ?", [rid])
    with db.read() as conn:
        v = verify_chain(conn)
    assert not v.ok and v.first_broken_run_id == rid
