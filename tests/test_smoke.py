"""Smoke tests: configuration loads, hashes are stable, schema applies."""

from __future__ import annotations

import re

import pytest

from satsa.config import Settings, load_settings
from satsa.db.connection import Database
from satsa.db.migrate import SCHEMA_VERSION, list_tables
from satsa.version import get_code_hash

HEX64 = re.compile(r"^[0-9a-f]{64}$")

EXPECTED_TABLES = {
    "schema_version",
    "raw_submissions",
    "entities",
    "assets",
    "alerts",
    "escalations",
    "incidents",
    "features_entity_period",
    "peer_baselines",
    "findings",
    "alert_sample_flags",
    "sri_scores",
    "trend_entity",
    "audit_runs",
    "feedback",
    "model_registry",
    "config_history",
}


def test_settings_load_and_hash(settings: Settings) -> None:
    assert HEX64.match(settings.config_hash)
    assert HEX64.match(settings.weights_hash)
    assert settings.app.seed == 42


def test_config_hash_changes_with_overrides(settings: Settings) -> None:
    other = load_settings(settings.config_dir, {"app": {"seed": 7}})
    assert other.config_hash != settings.config_hash


def test_sri_weights_sum_to_one(settings: Settings) -> None:
    dims = settings.sri_dimensions()
    assert abs(sum(d["weight"] for d in dims.values()) - 1.0) < 1e-9
    for name, dim in dims.items():
        subs = dim.get("subs")
        if subs:
            assert abs(sum(subs.values()) - 1.0) < 1e-9, name


def test_t_star_formula(settings: Settings) -> None:
    assert settings.t_star("execution_gap") == pytest.approx(1 / (1 + 4))
    assert settings.t_star("negative_space") == pytest.approx(0.25)
    assert settings.t_star("alert_sample") == pytest.approx(1 / 3)
    assert settings.band_halfwidth("alert_sample") == pytest.approx(0.08)
    assert settings.band_halfwidth("execution_gap") == pytest.approx(0.10)


def test_every_rule_has_required_keys(settings: Settings) -> None:
    rules = settings.rules["rules"]
    assert len(rules) == 19
    for rule_id, block in rules.items():
        assert rule_id.startswith(("EG-", "NS-"))
        for key in ("name", "enabled", "prior_weight", "control_id", "capability", "params"):
            assert key in block, f"{rule_id} missing {key}"
        assert block["control_id"] in settings.rules["controls"]


def test_code_hash_is_stable() -> None:
    assert HEX64.match(get_code_hash())
    assert get_code_hash() == get_code_hash()


def test_schema_applies_and_is_idempotent(db: Database) -> None:
    with db.read() as conn:
        assert set(list_tables(conn)) == EXPECTED_TABLES
        assert conn.execute("SELECT max(version) FROM schema_version").fetchone()[0] == SCHEMA_VERSION
    from satsa.db.migrate import apply_schema

    with db.write() as conn:
        apply_schema(conn)  # second application must not fail or duplicate versions
    with db.read() as conn:
        assert conn.execute("SELECT count(*) FROM schema_version").fetchone()[0] == 1


def test_write_transaction_rolls_back_on_error(db: Database) -> None:
    with pytest.raises(ValueError):
        with db.write() as conn:
            conn.execute("INSERT INTO entities (entity_id, name) VALUES ('X', 'x')")
            raise ValueError("boom")
    with db.read() as conn:
        assert conn.execute("SELECT count(*) FROM entities").fetchone()[0] == 0
