"""Simulator -> adapters -> validation -> DuckDB, across all three export formats."""

from __future__ import annotations

from pathlib import Path

import pytest

from satsa.config import Settings
from satsa.db.connection import Database
from satsa.ingest.loader import ingest_path, ingest_submission, parse_filename
from simulator.generate import generate_dataset


@pytest.fixture(scope="module")
def dataset(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """Two periods, one entity per export format, kept small for speed."""
    from satsa.config import load_settings

    root = tmp_path_factory.mktemp("sim")
    settings = load_settings(Path(__file__).resolve().parent.parent / "config")
    summary = generate_dataset(
        settings, seed=7, out_dir=root / "synthetic", ground_truth_dir=root / "gt",
        periods=["2026-01", "2026-02"], entity_ids=["E02", "E06", "E08"],
    )
    assert summary.total_alerts > 300
    return root / "synthetic", root / "gt"


def test_filename_convention() -> None:
    assert parse_filename(Path("E03_2026-04_alerts.csv")) == ("E03", "2026-04", "alerts")
    assert parse_filename(Path("E05_2026-04.json")) == ("E05", "2026-04", None)
    assert parse_filename(Path("random.csv")) == (None, None, None)


def test_ground_truth_files_written(dataset: tuple[Path, Path]) -> None:
    _, gt = dataset
    labels = (gt / "entity_period_labels.csv").read_text().splitlines()
    assert labels[0].startswith("entity_id,submission_period,profile")
    assert any(line.startswith("E06,2026-01,NEG_SPACE,0,1") for line in labels)
    assert (gt / "alert_labels.csv").exists() and (gt / "expected_findings.csv").exists()


def test_ingest_all_formats(dataset: tuple[Path, Path], settings: Settings, db: Database) -> None:
    synthetic, _ = dataset
    results = ingest_path(synthetic, settings=settings, db=db)
    assert len(results) == 6  # 3 entities x 2 periods
    assert all(r.status == "INGESTED" for r in results), [r.summary() for r in results]
    formats = {r.file_name.rsplit(".", 1)[1] for r in results}
    assert formats == {"csv", "json", "sqlite"}

    with db.read() as conn:
        n_alerts = conn.execute("SELECT count(*) FROM alerts").fetchone()[0]
        n_sub = conn.execute("SELECT count(*) FROM raw_submissions").fetchone()[0]
        entities = {r[0] for r in conn.execute("SELECT entity_id FROM entities").fetchall()}
        n_assets = conn.execute("SELECT count(*) FROM assets").fetchone()[0]
        n_esc = conn.execute("SELECT count(*) FROM escalations").fetchone()[0]
    assert n_alerts == sum(r.tables["alerts"] for r in results)
    assert n_sub == 6 and entities == {"E02", "E06", "E08"} and n_assets > 0 and n_esc > 0


def test_dirty_entity_is_flagged_in_validation(dataset: tuple[Path, Path], settings: Settings, db: Database) -> None:
    synthetic, _ = dataset
    results = ingest_path(synthetic, settings=settings, db=db)
    e06 = [r for r in results if r.entity_id == "E06"][0]
    e02 = [r for r in results if r.entity_id == "E02"][0]
    assert e06.validation.counts.get("V-07", 0) > 0, "unknown assets should be counted"
    assert e06.validation.counts.get("V-12", 0) > 0, "missing notes should be counted"
    assert e06.validation.counts.get("V-09", 0) > 0, "duplicate ids should be counted"
    assert e06.validation.rate("WARN") > e02.validation.rate("WARN")
    with db.read() as conn:
        flagged = conn.execute(
            "SELECT count(*) FROM alerts WHERE entity_id = 'E06' AND len(validation_flags) > 0"
        ).fetchone()[0]
    assert flagged > 0


def test_reingest_is_noop_and_modified_file_supersedes(dataset: tuple[Path, Path], settings: Settings, db: Database, tmp_path: Path) -> None:
    synthetic, _ = dataset
    first = ingest_path(synthetic, settings=settings, db=db)
    again = ingest_path(synthetic, settings=settings, db=db)
    assert all(r.status == "ALREADY_INGESTED" for r in again)

    # Modify E06's January file: drop the last 5 alerts, re-ingest -> supersedes.
    src = synthetic / "E06_2026-01.json"
    import json

    doc = json.loads(src.read_text(encoding="utf-8"))
    doc["alerts"] = doc["alerts"][:-5]
    mod = tmp_path / "E06_2026-01.json"
    mod.write_text(json.dumps(doc), encoding="utf-8")
    res = ingest_submission(mod, settings=settings, db=db)
    assert res.status == "INGESTED" and len(res.superseded) == 1
    original = [r for r in first if r.entity_id == "E06" and r.submission_period == "2026-01"][0]
    with db.read() as conn:
        n_alerts = conn.execute("SELECT count(*) FROM alerts WHERE entity_id='E06' AND submission_period='2026-01'").fetchone()[0]
        sup = conn.execute("SELECT superseded, superseded_by FROM raw_submissions WHERE submission_id = ?", [original.submission_id]).fetchone()
        active = conn.execute("SELECT count(*) FROM raw_submissions WHERE entity_id='E06' AND submission_period='2026-01' AND superseded = FALSE").fetchone()[0]
    assert n_alerts == res.tables["alerts"]
    assert sup == (True, res.submission_id) and active == 1
