"""Ingest one submission (or a directory of them) into DuckDB.

File naming convention when entity/period are not given explicitly:
    <entity_id>_<YYYY-MM>[_alerts|_assets|_entities|_escalations|_incidents].<csv|json|sqlite>
e.g. E03_2026-04_alerts.csv, E03_2026-04_assets.csv, E05_2026-04.json, E07_2026-04.sqlite
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from satsa.audit.audit_log import record_event
from satsa.audit.hashing import hash_file, new_id
from satsa.config import Settings
from satsa.db.connection import Database
from satsa.db.repo import insert_df, to_json
from satsa.ingest.base import BaseAdapter
from satsa.ingest.csv_adapter import CsvAdapter
from satsa.ingest.dedupe import existing_submission_for_hash, supersede_previous
from satsa.ingest.json_adapter import JsonAdapter
from satsa.ingest.mapping import load_mapping, map_alerts, map_assets, map_entities, map_generic
from satsa.ingest.sqlite_adapter import SqliteAdapter
from satsa.schema.validation import ValidationReport, parse_datetime, validate_alerts

ADAPTERS: list[type[BaseAdapter]] = [CsvAdapter, JsonAdapter, SqliteAdapter]
FILENAME_RE = re.compile(r"^(?P<entity>[A-Za-z0-9\-]+)_(?P<period>\d{4}-\d{2})(?:_(?P<table>alerts|assets|entities|escalations|incidents))?$")

ALERT_DB_COLUMNS = [
    "alert_id", "entity_id", "submission_period", "submission_id", "raw_row_index", "ts", "severity", "category",
    "asset_id", "source_system", "analyst_id", "analyst_action", "acknowledged_at", "investigated_at", "closed_at",
    "time_to_close_min", "escalation_flag", "escalated_at", "closure_reason", "investigation_notes",
    "root_cause_flag", "remediation_ticket_id", "rule_name", "validation_flags",
]


@dataclass
class IngestResult:
    submission_id: str
    entity_id: str
    submission_period: str
    file_name: str
    file_hash: str
    status: str  # INGESTED | ALREADY_INGESTED | FATAL
    tables: dict[str, int] = field(default_factory=dict)
    superseded: list[str] = field(default_factory=list)
    validation: ValidationReport | None = None

    def summary(self) -> str:
        v = self.validation
        vtxt = "" if v is None else f" accepted={v.n_accepted} rejected={v.n_rejected} err={v.level_counts['ERROR']} warn={v.level_counts['WARN']}"
        return f"{self.status:<17} {self.entity_id} {self.submission_period} {self.file_name} tables={self.tables}{vtxt}"


def pick_adapter(path: Path) -> BaseAdapter:
    for cls in ADAPTERS:
        if cls.detect(path):
            return cls()
    raise ValueError(f"no adapter for {path.suffix!r} ({path.name})")


def parse_filename(path: Path) -> tuple[str | None, str | None, str | None]:
    m = FILENAME_RE.match(path.stem)
    if not m:
        return None, None, None
    return m.group("entity"), m.group("period"), m.group("table")


def _enum_values(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        if c in df.columns:
            df[c] = df[c].map(lambda v: v.value if hasattr(v, "value") else v).astype(object)
    return df


def ingest_submission(
    path: Path | str,
    *,
    settings: Settings,
    db: Database,
    entity_id: str | None = None,
    submission_period: str | None = None,
    mapping_name: str = "generic_csv",
    run_id: str | None = None,
    extra_files: list[Path] | None = None,
    triggered_by: str = "cli",
    trigger_source: str = "cli",
) -> IngestResult:
    """Ingest a submission file plus optional companion files (e.g. an assets CSV)."""
    path = Path(path)
    ent, per, _ = parse_filename(path)
    entity_id = entity_id or ent
    submission_period = submission_period or per
    if not entity_id or not submission_period:
        raise ValueError(f"{path.name}: entity_id/submission_period not given and not parseable from the file name")

    # The submission hash covers the main file and every companion file so a changed
    # assets file also counts as a resubmission.
    file_hash = hash_file(path)
    for extra in extra_files or []:
        file_hash = _combine(file_hash, hash_file(extra))
    submission_id = f"{entity_id}_{submission_period}_{file_hash[:12]}"
    run_id = run_id or new_id("ing_")

    with db.read() as conn:
        if existing_submission_for_hash(conn, file_hash):
            return IngestResult(submission_id, entity_id, submission_period, path.name, file_hash, "ALREADY_INGESTED")

    # Read every file into raw string frames keyed by table.
    raw: dict[str, pd.DataFrame] = {}
    adapter = pick_adapter(path)
    raw.update(adapter.read(path))
    for extra in extra_files or []:
        raw.update(pick_adapter(extra).read(extra))

    mapping = load_mapping(settings.config_dir, mapping_name)
    report = ValidationReport(submission_id=submission_id)
    frames: dict[str, pd.DataFrame] = {}

    # entities
    if "entities" in raw and not raw["entities"].empty:
        ent_df, unmapped = map_entities(raw["entities"], mapping)
        report.unmapped_columns += [f"entities.{c}" for c in unmapped]
        if "entity_id" in ent_df.columns:
            ent_df["entity_id"] = ent_df["entity_id"].where(ent_df["entity_id"].notna(), entity_id)
        else:
            ent_df["entity_id"] = entity_id
        frames["entities"] = _enum_values(ent_df, ["sector", "size_band"])

    # assets
    known_assets: set[str] | None = None
    if "assets" in raw and not raw["assets"].empty:
        asset_df, unmapped = map_assets(raw["assets"], mapping, settings)
        report.unmapped_columns += [f"assets.{c}" for c in unmapped]
        asset_df["entity_id"] = entity_id
        asset_df["first_seen_period"] = asset_df.get("first_seen_period", submission_period)
        frames["assets"] = _enum_values(asset_df, ["criticality_tier", "asset_class"])
        known_assets = set(asset_df["asset_id"].dropna().astype(str))
    else:
        with db.read() as conn:
            rows = conn.execute("SELECT asset_id FROM assets WHERE entity_id = ?", [entity_id]).fetchall()
        known_assets = {r[0] for r in rows} if rows else None

    # alerts
    alerts_raw = raw.get("alerts", pd.DataFrame())
    alerts_df, unmapped = map_alerts(alerts_raw, mapping)
    report.unmapped_columns += [f"alerts.{c}" for c in unmapped if not c.startswith("_raw_")]
    accepted, report = validate_alerts(
        alerts_df, entity_id=entity_id, submission_period=submission_period, known_asset_ids=known_assets, report=report
    )
    if not report.fatal:
        accepted = accepted.rename(columns={"timestamp": "ts"})
        accepted["entity_id"] = entity_id
        accepted["submission_period"] = submission_period
        accepted["submission_id"] = submission_id
        accepted = _enum_values(accepted, ["severity", "category", "analyst_action", "closure_reason"])
        for col in ALERT_DB_COLUMNS:
            if col not in accepted.columns:
                accepted[col] = None
        frames["alerts"] = accepted[ALERT_DB_COLUMNS]

    # escalations / incidents (optional)
    for table in ("escalations", "incidents"):
        if table in raw and not raw[table].empty:
            df, unmapped = map_generic(raw[table], mapping, table)
            report.unmapped_columns += [f"{table}.{c}" for c in unmapped]
            df["entity_id"] = entity_id
            df["submission_period"] = submission_period
            for col in ("raised_at", "acknowledged_by_ir_at", "opened_at", "closed_at"):
                if col in df.columns:
                    df[col] = parse_datetime(df[col])
            if table == "incidents" and "linked_alert_ids" in df.columns:
                df["linked_alert_ids"] = df["linked_alert_ids"].map(
                    lambda v: v if isinstance(v, list) else ([x.strip() for x in str(v).split(",") if x.strip()] if v else [])
                )
            frames[table] = df

    # Persist in one transaction.
    archived = _archive(path, settings, file_hash)
    status = "FATAL" if report.fatal else "INGESTED"
    with db.write() as conn:
        superseded = supersede_previous(conn, entity_id, submission_period, submission_id, list(frames))
        counts: dict[str, int] = {}
        if "entities" in frames:
            ids = list(frames["entities"]["entity_id"].astype(str))
            conn.execute(f"DELETE FROM entities WHERE entity_id IN ({','.join('?' * len(ids))})", ids)
            counts["entities"] = insert_df(conn, "entities", frames["entities"])
        if "assets" in frames:
            conn.execute("DELETE FROM assets WHERE entity_id = ?", [entity_id])
            counts["assets"] = insert_df(conn, "assets", frames["assets"])
        for table in ("alerts", "escalations", "incidents"):
            if table in frames:
                counts[table] = insert_df(conn, table, frames[table])
        conn.execute(
            """
            INSERT INTO raw_submissions (submission_id, entity_id, submission_period, source_format, adapter, mapping_name,
              file_name, file_path, file_hash, file_bytes, received_at, row_count, accepted_rows, rejected_rows,
              validation_json, fatal, superseded, ingest_run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, FALSE, ?)
            """,
            [
                submission_id, entity_id, submission_period, adapter.name, adapter.name, mapping_name,
                path.name, str(archived), file_hash, path.stat().st_size, datetime.now(), report.n_rows,
                report.n_accepted, report.n_rejected, to_json(report.to_dict()), report.fatal, run_id,
            ],
        )
        record_event(
            conn, settings, run_type="INGEST", period=submission_period, triggered_by=triggered_by, trigger_source=trigger_source,
            manifest={"submission_id": submission_id, "entity_id": entity_id, "file_name": path.name, "file_hash": file_hash,
                      "status": status, "tables": counts, "superseded": superseded, "validation": report.level_counts},
            output_hash=file_hash,
        )
    return IngestResult(submission_id, entity_id, submission_period, path.name, file_hash, status, counts, superseded, report)


def ingest_path(path: Path | str, *, settings: Settings, db: Database, mapping_name: str = "generic_csv", triggered_by: str = "cli", trigger_source: str = "cli") -> list[IngestResult]:
    """Ingest a file, or every recognised file in a directory, grouping companion files per (entity, period)."""
    path = Path(path)
    files = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file() and any(a.detect(p) for a in ADAPTERS))
    groups: dict[tuple[str, str], dict[str, Path]] = {}
    loose: list[Path] = []
    for f in files:
        ent, per, table = parse_filename(f)
        if ent and per:
            groups.setdefault((ent, per), {})[table or "main"] = f
        else:
            loose.append(f)

    results: list[IngestResult] = []
    for (ent, per), parts in sorted(groups.items()):
        main = parts.get("main") or parts.get("alerts")
        if main is None:  # e.g. only an assets file this period
            main = next(iter(parts.values()))
        extras = [p for k, p in parts.items() if p != main]
        results.append(ingest_submission(main, settings=settings, db=db, entity_id=ent, submission_period=per, mapping_name=mapping_name, extra_files=extras, triggered_by=triggered_by, trigger_source=trigger_source))
    for f in loose:
        results.append(ingest_submission(f, settings=settings, db=db, mapping_name=mapping_name, triggered_by=triggered_by, trigger_source=trigger_source))
    return results


def _archive(path: Path, settings: Settings, file_hash: str) -> Path:
    dest_dir = settings.resolve(settings.paths.processed_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{file_hash}{path.suffix.lower()}"
    if not dest.exists():
        shutil.copy2(path, dest)
    return dest


def _combine(a: str, b: str) -> str:
    from satsa.audit.hashing import hash_bytes

    return hash_bytes(f"{a}:{b}".encode())


def submission_row(conn: Any, submission_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM raw_submissions WHERE submission_id = ?", [submission_id]).df()
    return None if row.empty else row.iloc[0].to_dict()
