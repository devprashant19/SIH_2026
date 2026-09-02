"""Submission validation: checks V-01..V-13.

Philosophy: a CSE's inability to submit clean data is itself supervisory evidence, so
checks *record* problems rather than silently dropping rows. Only rows that cannot be
keyed at all are rejected (missing/unparseable timestamp, duplicate alert_id).

Input DataFrames come from ingest/mapping.py with canonical column names; enum columns are
already normalised and raw values are kept in ``_raw_<col>`` columns for V-08.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import pandas as pd

from satsa.schema.canonical import ALERT_REQUIRED_COLUMNS
from satsa.schema.enums import ACTION_RANK, AnalystAction, Category, Severity

FATAL, ERROR, WARN = "FATAL", "ERROR", "WARN"

CHECKS: dict[str, tuple[str, str]] = {
    "V-01": (FATAL, "required column missing"),
    "V-02": (ERROR, "unparseable timestamp"),
    "V-03": (ERROR, "closed_at earlier than timestamp"),
    "V-04": (WARN, "acknowledged_at earlier than timestamp"),
    "V-05": (WARN, "analyst_action=CLOSED but closed_at missing"),
    "V-06": (WARN, "escalation_flag set but escalated_at missing"),
    "V-07": (WARN, "asset_id not in entity asset inventory"),
    "V-08": (WARN, "severity/category value not recognised"),
    "V-09": (ERROR, "duplicate alert_id within submission"),
    "V-10": (WARN, "timestamp outside submission period (+/- 3 days)"),
    "V-11": (WARN, "no alert rows for entity in period"),
    "V-12": (WARN, "investigation_notes missing for investigated/escalated/closed alert"),
    "V-13": (WARN, "source_system missing"),
}

DATETIME_COLUMNS = ("timestamp", "acknowledged_at", "investigated_at", "closed_at", "escalated_at")
SAMPLE_LIMIT = 20
PERIOD_TOLERANCE = timedelta(days=3)


@dataclass
class ValidationReport:
    submission_id: str | None = None
    fatal: bool = False
    n_rows: int = 0
    n_accepted: int = 0
    n_rejected: int = 0
    counts: dict[str, int] = field(default_factory=dict)
    samples: dict[str, list[int]] = field(default_factory=dict)
    unmapped_columns: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)

    def add(self, check_id: str, row_indices: list[int] | pd.Index) -> None:
        idx = [int(i) for i in row_indices]
        if not idx:
            return
        self.counts[check_id] = self.counts.get(check_id, 0) + len(idx)
        self.samples.setdefault(check_id, [])
        room = SAMPLE_LIMIT - len(self.samples[check_id])
        if room > 0:
            self.samples[check_id].extend(idx[:room])

    def flag_submission(self, check_id: str, message: str) -> None:
        self.counts[check_id] = self.counts.get(check_id, 0) + 1
        self.messages.append(f"{check_id}: {message}")

    @property
    def level_counts(self) -> dict[str, int]:
        out = {FATAL: 0, ERROR: 0, WARN: 0}
        for cid, n in self.counts.items():
            out[CHECKS[cid][0]] += n
        return out

    def rate(self, level: str) -> float:
        return self.level_counts[level] / self.n_rows if self.n_rows else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "submission_id": self.submission_id,
            "fatal": self.fatal,
            "n_rows": self.n_rows,
            "n_accepted": self.n_accepted,
            "n_rejected": self.n_rejected,
            "counts": dict(sorted(self.counts.items())),
            "samples": self.samples,
            "unmapped_columns": self.unmapped_columns,
            "messages": self.messages,
            "level_counts": self.level_counts,
        }


def _period_bounds(period: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    from satsa.features.base import period_bounds

    return period_bounds(period)


def parse_datetime(series: pd.Series) -> pd.Series:
    """Parse mixed ISO / common formats to naive UTC timestamps; unparseable -> NaT."""
    s = series.where(series.notna(), None)
    s = s.astype("string").str.strip()
    s = s.mask(s == "", None)
    parsed = pd.to_datetime(s, errors="coerce", utc=True, format="mixed")
    return parsed.dt.tz_localize(None)


def validate_alerts(
    df: pd.DataFrame,
    *,
    entity_id: str,
    submission_period: str,
    known_asset_ids: set[str] | None = None,
    report: ValidationReport | None = None,
) -> tuple[pd.DataFrame, ValidationReport]:
    """Run V-01..V-13. Returns (accepted rows with validation_flags, report)."""
    rep = report or ValidationReport()
    rep.n_rows = int(len(df))
    df = df.copy().reset_index(drop=True)
    if "raw_row_index" not in df.columns:
        df["raw_row_index"] = range(len(df))
    flags: list[list[str]] = [[] for _ in range(len(df))]

    def mark(check_id: str, mask: pd.Series) -> pd.Index:
        idx = df.index[mask.fillna(False).astype(bool)]
        for i in idx:
            flags[i].append(check_id)
        rep.add(check_id, idx)
        return idx

    # V-01 required columns
    missing = [c for c in ALERT_REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        rep.fatal = True
        rep.flag_submission("V-01", f"missing required columns {missing}")
        rep.n_rejected = rep.n_rows
        return df.iloc[0:0], rep

    # V-11 empty submission
    if len(df) == 0:
        rep.flag_submission("V-11", f"no alert rows for {entity_id} in {submission_period}")
        df["validation_flags"] = pd.Series([[] for _ in range(0)], dtype=object)
        return df, rep

    # Parse datetimes; remember what was non-empty before parsing for V-02
    raw_nonempty = {}
    for col in DATETIME_COLUMNS:
        if col in df.columns:
            raw = df[col].astype("string").str.strip()
            raw_nonempty[col] = raw.notna() & (raw != "")
            df[col] = parse_datetime(df[col])
        else:
            df[col] = pd.NaT
            raw_nonempty[col] = pd.Series(False, index=df.index)

    rejected = pd.Series(False, index=df.index)

    # V-02 unparseable timestamps (primary timestamp -> reject; others -> flag only)
    bad_primary = df["timestamp"].isna()
    mark("V-02", bad_primary)
    rejected |= bad_primary
    for col in DATETIME_COLUMNS[1:]:
        mark("V-02", raw_nonempty[col] & df[col].isna())

    # V-09 duplicate alert_id (first kept)
    dup = df["alert_id"].astype("string").duplicated(keep="first")
    mark("V-09", dup)
    rejected |= dup

    # V-03 closed before opened (retained, but derived TTC is voided)
    v03 = df["closed_at"].notna() & df["timestamp"].notna() & (df["closed_at"] < df["timestamp"])
    mark("V-03", v03)

    # V-04 ack before opened
    mark("V-04", df["acknowledged_at"].notna() & df["timestamp"].notna() & (df["acknowledged_at"] < df["timestamp"]))

    # V-05 closed without closed_at
    action = df["analyst_action"] if "analyst_action" in df.columns else pd.Series(AnalystAction.NONE, index=df.index)
    action_rank = action.map(lambda a: ACTION_RANK.get(a, 0) if a is not None else 0)
    mark("V-05", (action == AnalystAction.CLOSED) & df["closed_at"].isna())

    # V-06 escalated without escalated_at
    esc = df["escalation_flag"].fillna(False).astype(bool) if "escalation_flag" in df.columns else pd.Series(False, index=df.index)
    mark("V-06", esc & df["escalated_at"].isna())

    # V-07 unknown asset
    if known_asset_ids is not None and "asset_id" in df.columns:
        has_asset = df["asset_id"].notna() & (df["asset_id"].astype("string") != "")
        mark("V-07", has_asset & ~df["asset_id"].isin(known_asset_ids))

    # V-08 unmapped severity/category (mapping keeps raw values in _raw_* columns)
    if "_raw_severity" in df.columns:
        raw_sev = df["_raw_severity"].astype("string").str.strip()
        mark("V-08", raw_sev.notna() & (raw_sev != "") & df["severity"].isna())
    if "_raw_category" in df.columns:
        raw_cat = df["_raw_category"].astype("string").str.strip()
        mark("V-08", raw_cat.notna() & (raw_cat != "") & (df["category"] == Category.UNKNOWN))
    df["severity"] = df["severity"].map(lambda v: v if isinstance(v, Severity) else Severity.INFO).astype(object)

    # V-10 outside period
    start, end = _period_bounds(submission_period)
    ts = df["timestamp"]
    mark("V-10", ts.notna() & ((ts < start - PERIOD_TOLERANCE) | (ts > end + PERIOD_TOLERANCE)))

    # V-12 notes missing on investigated+ alerts
    notes = df["investigation_notes"].astype("string").str.strip() if "investigation_notes" in df.columns else pd.Series(pd.NA, index=df.index, dtype="string")
    notes_missing = notes.isna() | (notes == "")
    mark("V-12", (action_rank >= ACTION_RANK[AnalystAction.INVESTIGATED]) & notes_missing)

    # V-13 source_system missing
    src = df["source_system"].astype("string").str.strip() if "source_system" in df.columns else pd.Series(pd.NA, index=df.index, dtype="string")
    mark("V-13", src.isna() | (src == ""))

    # Derived fields
    if "time_to_close_min" not in df.columns:
        df["time_to_close_min"] = pd.NA
    ttc = pd.to_numeric(df["time_to_close_min"], errors="coerce")
    derived = (df["closed_at"] - df["timestamp"]).dt.total_seconds() / 60.0
    ttc = ttc.where(ttc.notna(), derived)
    ttc = ttc.mask(v03)  # closed-before-opened has no meaningful TTC
    df["time_to_close_min"] = ttc.astype("float64")

    inv_needed = df["investigated_at"].isna() & (action_rank >= ACTION_RANK[AnalystAction.INVESTIGATED])
    fallback = df["escalated_at"].where(df["escalated_at"].notna(), df["closed_at"])
    df.loc[inv_needed, "investigated_at"] = fallback[inv_needed]

    df["validation_flags"] = pd.Series(flags, index=df.index, dtype=object)
    accepted = df.loc[~rejected].copy()
    rep.n_rejected = int(rejected.sum())
    rep.n_accepted = int(len(accepted))
    return accepted, rep
