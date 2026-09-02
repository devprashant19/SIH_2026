"""SQLite adapter for database exports. Reads any of the canonical tables that exist."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

from satsa.ingest.base import TABLES, BaseAdapter, blank_to_none

TABLE_ALIASES = {
    "alerts": ("alerts", "alert", "security_alerts", "offenses", "notable_events"),
    "assets": ("assets", "asset", "asset_inventory", "cmdb"),
    "entities": ("entities", "entity", "organisation", "organization"),
    "escalations": ("escalations", "escalation"),
    "incidents": ("incidents", "incident", "cases"),
}


class SqliteAdapter(BaseAdapter):
    name = "sqlite"
    extensions = (".sqlite", ".sqlite3", ".db")

    def read(self, path: Path) -> dict[str, pd.DataFrame]:
        out: dict[str, pd.DataFrame] = {}
        uri = f"file:{path.as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as conn:
            names = {r[0].lower(): r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in TABLES:
                for alias in TABLE_ALIASES[table]:
                    if alias in names:
                        df = pd.read_sql_query(f'SELECT * FROM "{names[alias]}"', conn)
                        df = df.astype(object).where(df.notna(), "").astype(str)
                        out[table] = blank_to_none(df)
                        break
        if not out:
            raise ValueError(f"{path}: no recognised tables (found {sorted(names)})")
        return out
