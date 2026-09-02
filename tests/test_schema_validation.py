"""Hand-built rows for each validation check."""

from __future__ import annotations

import pandas as pd

from satsa.schema.enums import AnalystAction, Category, Severity
from satsa.schema.validation import validate_alerts


def _base(n: int = 1) -> pd.DataFrame:
    rows = []
    for i in range(n):
        rows.append(
            {
                "alert_id": f"A{i}",
                "timestamp": f"2026-04-1{i % 9}T10:00:00",
                "severity": Severity.HIGH,
                "category": Category.MALWARE,
                "_raw_severity": "high",
                "_raw_category": "malware",
                "asset_id": "AS1",
                "source_system": "edr",
                "analyst_action": AnalystAction.CLOSED,
                "acknowledged_at": f"2026-04-1{i % 9}T10:05:00",
                "investigated_at": None,
                "closed_at": f"2026-04-1{i % 9}T12:00:00",
                "time_to_close_min": None,
                "escalation_flag": False,
                "escalated_at": None,
                "closure_reason": None,
                "investigation_notes": "Investigated thoroughly; benign scheduled task.",
                "root_cause_flag": None,
            }
        )
    return pd.DataFrame(rows)


def _run(df: pd.DataFrame, **kw):
    return validate_alerts(df, entity_id="E1", submission_period="2026-04", known_asset_ids={"AS1"}, **kw)


def test_clean_row_has_no_flags_and_derived_ttc() -> None:
    accepted, rep = _run(_base())
    assert rep.counts == {}
    assert accepted.loc[0, "validation_flags"] == []
    assert accepted.loc[0, "time_to_close_min"] == 120.0


def test_v01_missing_required_column_is_fatal() -> None:
    df = _base().drop(columns=["severity"])
    accepted, rep = _run(df)
    assert rep.fatal and accepted.empty and rep.counts["V-01"] == 1


def test_v02_bad_timestamp_rejected() -> None:
    df = _base(2)
    df.loc[1, "timestamp"] = "not a date"
    accepted, rep = _run(df)
    assert rep.counts["V-02"] == 1 and rep.n_rejected == 1 and len(accepted) == 1


def test_v03_v04_time_order() -> None:
    df = _base()
    df.loc[0, "closed_at"] = "2026-04-10T09:00:00"
    df.loc[0, "acknowledged_at"] = "2026-04-10T09:30:00"
    accepted, rep = _run(df)
    assert rep.counts["V-03"] == 1 and rep.counts["V-04"] == 1
    assert pd.isna(accepted.loc[0, "time_to_close_min"])  # TTC voided
    assert {"V-03", "V-04"} <= set(accepted.loc[0, "validation_flags"])


def test_v05_v06_missing_workflow_timestamps() -> None:
    df = _base()
    df.loc[0, "closed_at"] = None
    df.loc[0, "escalation_flag"] = True
    _, rep = _run(df)
    assert rep.counts["V-05"] == 1 and rep.counts["V-06"] == 1


def test_v07_unknown_asset() -> None:
    df = _base()
    df.loc[0, "asset_id"] = "GHOST"
    _, rep = _run(df)
    assert rep.counts["V-07"] == 1


def test_v08_unmapped_values_default_and_flag() -> None:
    df = _base()
    df.loc[0, "severity"] = None
    df.loc[0, "_raw_severity"] = "banana"
    df.loc[0, "category"] = Category.UNKNOWN
    df.loc[0, "_raw_category"] = "weird"
    accepted, rep = _run(df)
    assert rep.counts["V-08"] == 2
    assert accepted.loc[0, "severity"] == Severity.INFO


def test_v09_duplicates_keep_first() -> None:
    df = _base(2)
    df.loc[1, "alert_id"] = "A0"
    accepted, rep = _run(df)
    assert rep.counts["V-09"] == 1 and len(accepted) == 1


def test_v10_outside_period() -> None:
    df = _base()
    df.loc[0, "timestamp"] = "2026-06-20T10:00:00"
    _, rep = _run(df)
    assert rep.counts["V-10"] == 1


def test_v11_empty_submission() -> None:
    df = _base().iloc[0:0]
    accepted, rep = _run(df)
    assert rep.counts["V-11"] == 1 and accepted.empty and not rep.fatal


def test_v12_v13_missing_notes_and_source() -> None:
    df = _base()
    df.loc[0, "investigation_notes"] = "  "
    df.loc[0, "source_system"] = None
    accepted, rep = _run(df)
    assert rep.counts["V-12"] == 1 and rep.counts["V-13"] == 1
    assert accepted.loc[0, "investigated_at"] == pd.Timestamp("2026-04-10T12:00:00")  # derived from closed_at


def test_rates_and_levels() -> None:
    df = _base(4)
    df.loc[0, "source_system"] = None  # WARN
    df.loc[1, "timestamp"] = "??"  # ERROR
    _, rep = _run(df)
    assert rep.level_counts["ERROR"] == 1 and rep.level_counts["WARN"] == 1
    assert rep.rate("ERROR") == 0.25
    d = rep.to_dict()
    assert d["n_rows"] == 4 and d["n_accepted"] == 3
