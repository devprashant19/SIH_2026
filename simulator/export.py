"""Write one entity-period as CSV files, a JSON document, or a SQLite database.

Using three formats exercises every ingestion adapter on every run of the demo.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


def _iso(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.isoformat(timespec="seconds")
    return v


def _frame(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    # pandas turns None in datetime columns into NaT; write those as empty, not the string "NaT".
    df = df.astype(object).where(df.notna(), None)
    for col in df.columns:
        df[col] = df[col].map(_iso)
    return df


def export_csv(out_dir: Path, entity_id: str, period: str, tables: dict[str, list[dict]]) -> list[Path]:
    paths = []
    for table, rows in tables.items():
        if not rows:
            continue
        df = _frame(rows)
        if "expected_telemetry_sources" in df.columns:
            df["expected_telemetry_sources"] = df["expected_telemetry_sources"].map(lambda v: ";".join(v) if isinstance(v, list) else v)
        if "linked_alert_ids" in df.columns:
            df["linked_alert_ids"] = df["linked_alert_ids"].map(lambda v: ",".join(v) if isinstance(v, list) else v)
        path = out_dir / f"{entity_id}_{period}_{table}.csv"
        df.to_csv(path, index=False)
        paths.append(path)
    return paths


def export_json(out_dir: Path, entity_id: str, period: str, tables: dict[str, list[dict]]) -> list[Path]:
    doc: dict[str, Any] = {"entity": None, "submission_period": period}
    for table, rows in tables.items():
        clean = [{k: _iso(v) for k, v in r.items()} for r in rows]
        if table == "entities":
            doc["entity"] = clean[0] if clean else None
        else:
            doc[table] = clean
    path = out_dir / f"{entity_id}_{period}.json"
    path.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return [path]


def export_sqlite(out_dir: Path, entity_id: str, period: str, tables: dict[str, list[dict]]) -> list[Path]:
    path = out_dir / f"{entity_id}_{period}.sqlite"
    if path.exists():
        path.unlink()
    with sqlite3.connect(path) as conn:
        for table, rows in tables.items():
            if not rows:
                continue
            df = _frame(rows)
            for col in df.columns:
                if df[col].map(lambda v: isinstance(v, list)).any():
                    df[col] = df[col].map(lambda v: ";".join(v) if isinstance(v, list) else v)
            df.to_sql(table, conn, index=False)
    return [path]


EXPORTERS = {"csv": export_csv, "json": export_json, "sqlite": export_sqlite}
