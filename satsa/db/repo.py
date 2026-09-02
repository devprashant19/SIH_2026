"""Thin query helpers shared by every module. Keeps SQL boilerplate out of analytics code."""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from typing import Any

import duckdb
import pandas as pd


def fetch_df(conn: duckdb.DuckDBPyConnection, sql: str, params: Sequence[Any] | None = None) -> pd.DataFrame:
    return conn.execute(sql, list(params or [])).df()


def fetch_one(conn: duckdb.DuckDBPyConnection, sql: str, params: Sequence[Any] | None = None) -> tuple | None:
    return conn.execute(sql, list(params or [])).fetchone()


def fetch_scalar(conn: duckdb.DuckDBPyConnection, sql: str, params: Sequence[Any] | None = None) -> Any:
    row = fetch_one(conn, sql, params)
    return None if row is None else row[0]


def insert_df(conn: duckdb.DuckDBPyConnection, table: str, df: pd.DataFrame) -> int:
    """Append a DataFrame to a table by column name. Columns missing from df are left NULL."""
    if df is None or df.empty:
        return 0
    table_cols = [r[0] for r in conn.execute(f"DESCRIBE {table}").fetchall()]
    cols = [c for c in df.columns if c in table_cols]
    unknown = [c for c in df.columns if c not in table_cols]
    if unknown:
        raise ValueError(f"insert_df({table}): unknown columns {unknown}")
    view = f"_ins_{table}_{abs(hash(id(df))) % 10_000_000}"
    conn.register(view, df[cols])
    try:
        col_list = ", ".join(cols)
        conn.execute(f"INSERT INTO {table} ({col_list}) SELECT {col_list} FROM {view}")
    finally:
        conn.unregister(view)
    return len(df)


def table_counts(conn: duckdb.DuckDBPyConnection, tables: Sequence[str]) -> dict[str, int]:
    return {t: int(fetch_scalar(conn, f"SELECT count(*) FROM {t}")) for t in tables}


def latest_success_run_id(conn: duckdb.DuckDBPyConnection, submission_period: str) -> str | None:
    """The run whose rows are 'current' for a period."""
    return fetch_scalar(
        conn,
        """
        SELECT run_id FROM audit_runs
        WHERE run_type = 'PIPELINE' AND status = 'SUCCESS' AND submission_period = ?
        ORDER BY finished_at DESC LIMIT 1
        """,
        [submission_period],
    )


def _jsonable(o: Any) -> Any:
    """Recursively convert NaN/inf to None and numpy/pandas scalars to Python types."""
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [_jsonable(v) for v in o]
    if hasattr(o, "tolist") and not isinstance(o, (str, bytes)):
        return _jsonable(o.tolist())
    if isinstance(o, float):
        return None if (math.isnan(o) or math.isinf(o)) else o
    if isinstance(o, (int, str, bool)) or o is None:
        return o
    if hasattr(o, "isoformat"):
        return o.isoformat()
    if hasattr(o, "item"):
        return _jsonable(o.item())
    return str(o)


def to_json(obj: Any) -> str:
    """Canonical JSON for JSON columns (sorted keys, NaN -> null)."""
    return json.dumps(_jsonable(obj), sort_keys=True, allow_nan=False)


def from_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)
