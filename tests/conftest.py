"""Shared pytest fixtures.

- ``no_network`` (autouse): any attempt to open an outbound socket fails the test. This
  enforces the air-gap requirement from PS 26157 §5 across the whole suite.
- ``settings``: Settings pointing the DuckDB file at a temp directory.
- ``db``: an initialised Database with the full schema applied.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator
from pathlib import Path

import pytest

from satsa.config import Settings, load_settings
from satsa.db.connection import Database
from satsa.db.migrate import apply_schema

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class NetworkAccessAttempted(RuntimeError):
    pass


LOOPBACK = {"127.0.0.1", "::1", "localhost"}


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Block every non-loopback connection. Loopback stays open because asyncio on Windows
    wakes its event loop through an internal socket pair, which the API test client needs."""
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def _guard(real):  # noqa: ANN001
        def wrapper(self, address, *args, **kwargs):  # noqa: ANN001
            host = address[0] if isinstance(address, tuple) else address
            if isinstance(host, str) and host in LOOPBACK:
                return real(self, address, *args, **kwargs)
            raise NetworkAccessAttempted(f"outbound network access is forbidden in SAT-SA tests: {address!r}")

        return wrapper

    monkeypatch.setattr(socket.socket, "connect", _guard(real_connect))
    monkeypatch.setattr(socket.socket, "connect_ex", _guard(real_connect_ex))


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    overrides = {
        "paths": {
            "db_path": str(tmp_path / "satsa.duckdb"),
            "data_dir": str(tmp_path / "data"),
            "incoming_dir": str(tmp_path / "data" / "incoming"),
            "processed_dir": str(tmp_path / "data" / "processed"),
            "synthetic_dir": str(tmp_path / "data" / "synthetic"),
            "ground_truth_dir": str(tmp_path / "data" / "ground_truth"),
            "models_dir": str(tmp_path / "models"),
            "reports_dir": str(tmp_path / "reports"),
            "logs_dir": str(tmp_path / "logs"),
        }
    }
    return load_settings(PROJECT_ROOT / "config", overrides)


@pytest.fixture()
def db(settings: Settings) -> Iterator[Database]:
    database = Database(settings.db_path)
    with database.write() as conn:
        apply_schema(conn)
    try:
        yield database
    finally:
        database.close()


@pytest.fixture(scope="session")
def scored_db(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[Settings, Database]]:
    """A fully scored database: 4 entities x 4 periods, models trained on the first 3, every period run.

    Config lives in a copy so tests that write configuration do not touch the repo files.
    """
    import shutil

    from satsa.ingest.loader import ingest_path
    from satsa.models.train import train_models
    from satsa.pipeline.run import run_pipeline
    from simulator.generate import generate_dataset

    root = tmp_path_factory.mktemp("scored")
    cfg_dir = root / "config"
    shutil.copytree(PROJECT_ROOT / "config", cfg_dir)
    settings = load_settings(cfg_dir, {"paths": {
        "db_path": str(root / "db.duckdb"), "processed_dir": str(root / "processed"), "models_dir": str(root / "models"),
        "ground_truth_dir": str(root / "gt"), "logs_dir": str(root / "logs"), "reports_dir": str(root / "reports"), "incoming_dir": str(root / "incoming"),
    }, "pipeline": {"min_labels_for_calibration": 10}})
    periods = ["2026-01", "2026-02", "2026-03", "2026-04"]
    generate_dataset(settings, seed=11, out_dir=root / "syn", ground_truth_dir=root / "gt", periods=periods, entity_ids=["E01", "E03", "E05", "E06"])
    database = Database(settings.db_path)
    with database.write() as conn:
        apply_schema(conn)
    ingest_path(root / "syn", settings=settings, db=database)
    train_models(database, settings, periods[:3], promote=True)
    for p in periods:
        res = run_pipeline(p, settings=settings, db=database, triggered_by="test", trigger_source="test")
        assert res.status == "SUCCESS", res.error
    try:
        yield settings, database
    finally:
        database.close()
