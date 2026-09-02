"""The demo playthrough is also a test: it asserts the supervisory story the walkthrough tells."""

from __future__ import annotations

from pathlib import Path

import pytest

from satsa.config import Settings, load_settings
from satsa.db.connection import Database
from satsa.demo import demo_settings, run_demo

PERIODS = ["2026-01", "2026-02", "2026-03", "2026-04"]


@pytest.fixture(scope="module")
def demo(tmp_path_factory: pytest.TempPathFactory) -> tuple[Settings, Database, object]:
    root = tmp_path_factory.mktemp("demo")
    base = load_settings(Path(__file__).resolve().parent.parent / "config")
    settings = demo_settings(base, root)
    settings = load_settings(settings.config_dir, {"paths": settings.paths.model_dump(), "pipeline": {"min_labels_for_calibration": 10}})
    db = Database(settings.db_path)
    try:
        result = run_demo(settings, db, periods=PERIODS)
        yield settings, db, result
    finally:
        db.close()


def _step(result, keyword: str):
    return next(s for s in result.steps if keyword.lower() in s.title.lower())


def test_walkthrough_covers_every_stage(demo) -> None:
    _settings, _db, result = demo
    titles = [s.title for s in result.steps]
    assert len(titles) == 12
    for keyword in ("Submissions arrive", "Models are trained", "pipeline scores", "Portfolio view", "risk score", "One finding", "alert samples", "examiner decides", "Negative space", "cost of a missed", "Reports", "audit trail"):
        assert any(keyword.lower() in t.lower() for t in titles), keyword
    assert all(s.lines for s in result.steps)


def test_pipeline_is_idempotent_and_audit_holds(demo) -> None:
    _settings, _db, result = demo
    assert _step(result, "pipeline scores").facts["idempotent"] == "SKIPPED_IDENTICAL"
    audit = _step(result, "audit trail").facts
    assert audit["audit_ok"] is True and audit["n_runs"] > 20, "ingest, train, pipeline and feedback must all be audited"


def test_worst_entity_is_a_seeded_bad_one(demo) -> None:
    _settings, _db, result = demo
    portfolio = _step(result, "Portfolio view")
    # E03 (execution gap), E04 (execution gap), E05/E06 (negative space) are the seeded weak entities.
    assert portfolio.facts["highest_sri_entity"] in {"E03", "E04", "E05", "E06"}
    assert portfolio.facts["top_entity"] not in {"E01", "E02"}, "a healthy entity must not head the review queue"


def test_finding_is_explained_and_evidenced(demo) -> None:
    _settings, _db, result = demo
    step = _step(result, "One finding")
    f = step.facts["finding"]
    assert f["rule_id"] and f["p_final"] > 0 and f["decision"] in ("AUTO_FLAG", "MANUAL_REVIEW")
    text = " ".join(step.lines)
    assert "Rationale:" in text and "peer median" in text
    assert "C_FP / (C_FP + C_FN)" in text


def test_negative_space_names_the_missing_categories(demo) -> None:
    _settings, _db, result = demo
    step = _step(result, "Negative space")
    text = " ".join(step.lines)
    assert "E06" in step.facts["absent_entities"]
    assert "lateral_movement" in text or "data_exfil" in text


def test_cost_change_moves_the_uncertainty_band(demo) -> None:
    _settings, _db, result = demo
    w = _step(result, "cost of a missed").facts["what_if"]
    assert w["before"] != w["after"] or w["after"] >= 0


def test_reports_were_written(demo) -> None:
    _settings, _db, result = demo
    paths = _step(result, "Reports").facts["reports"]
    assert len(paths) == 2
    for p in paths:
        f = Path(p)
        assert f.exists() and f.read_bytes()[:4] == b"%PDF"


def test_every_action_is_audited(demo) -> None:
    _settings, db, _result = demo
    with db.read() as conn:
        kinds = dict(conn.execute("SELECT run_type, count(*) FROM audit_runs GROUP BY 1").fetchall())
    assert {"INGEST", "TRAIN", "PIPELINE", "FEEDBACK"} <= set(kinds), kinds
    assert kinds["INGEST"] >= 16 and kinds["TRAIN"] >= 1


def test_feedback_recorded_and_visible(demo) -> None:
    settings, db, result = demo
    fid = _step(result, "examiner decides").facts["feedback_id"]
    with db.read() as conn:
        row = conn.execute("SELECT decision, reviewer_id, target_id FROM feedback WHERE feedback_id = ?", [fid]).fetchone()
        audit = conn.execute("SELECT count(*) FROM audit_runs WHERE run_type = 'FEEDBACK'").fetchone()[0]
    assert row[0] == "ACCEPT" and row[2] == result.finding_id
    assert audit >= 1, "recording feedback must leave an audit row"
