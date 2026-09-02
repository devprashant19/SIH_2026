"""Resubmission handling: identical files are no-ops, changed files supersede prior rows."""

from __future__ import annotations

import duckdb


def existing_submission_for_hash(conn: duckdb.DuckDBPyConnection, file_hash: str) -> str | None:
    row = conn.execute("SELECT submission_id FROM raw_submissions WHERE file_hash = ? LIMIT 1", [file_hash]).fetchone()
    return row[0] if row else None


def supersede_previous(conn: duckdb.DuckDBPyConnection, entity_id: str, period: str, new_submission_id: str, tables: list[str]) -> list[str]:
    """Mark earlier submissions for (entity, period) superseded and remove their analytic input rows.

    Raw files stay archived under data/processed so earlier findings remain reproducible.
    Returns the superseded submission ids.
    """
    prior = [
        r[0]
        for r in conn.execute(
            "SELECT submission_id FROM raw_submissions WHERE entity_id = ? AND submission_period = ? AND superseded = FALSE AND submission_id <> ?",
            [entity_id, period, new_submission_id],
        ).fetchall()
    ]
    if not prior:
        return []
    conn.execute(
        "UPDATE raw_submissions SET superseded = TRUE, superseded_by = ? WHERE entity_id = ? AND submission_period = ? AND submission_id <> ?",
        [new_submission_id, entity_id, period, new_submission_id],
    )
    for table in tables:
        if table == "alerts":
            conn.execute("DELETE FROM alerts WHERE entity_id = ? AND submission_period = ?", [entity_id, period])
        elif table in ("escalations", "incidents"):
            conn.execute(f"DELETE FROM {table} WHERE entity_id = ? AND submission_period = ?", [entity_id, period])
    return prior
