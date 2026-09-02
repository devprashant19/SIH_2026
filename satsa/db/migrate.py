"""Apply schema.sql to a database. Idempotent: every statement is CREATE ... IF NOT EXISTS."""

from __future__ import annotations

from pathlib import Path

import duckdb

SCHEMA_VERSION = 1
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def _statements(sql: str) -> list[str]:
    """Strip '--' comments first (they may contain semicolons), then split on semicolons."""
    stripped_lines = []
    for line in sql.splitlines():
        code = line.split("--", 1)[0].rstrip()
        if code.strip():
            stripped_lines.append(code)
    return [chunk.strip() for chunk in "\n".join(stripped_lines).split(";") if chunk.strip()]


def apply_schema(conn: duckdb.DuckDBPyConnection) -> int:
    """Create all tables/indexes if missing and record the schema version. Returns the version."""
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    for stmt in _statements(sql):
        conn.execute(stmt)
    current = conn.execute("SELECT max(version) FROM schema_version").fetchone()[0]
    if current is None or current < SCHEMA_VERSION:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", [SCHEMA_VERSION])
    return SCHEMA_VERSION


def list_tables(conn: duckdb.DuckDBPyConnection) -> list[str]:
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main' ORDER BY table_name"
    ).fetchall()
    return [r[0] for r in rows]
