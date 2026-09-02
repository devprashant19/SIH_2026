"""FastAPI dependencies: settings and database handles stored on app.state at startup."""

from __future__ import annotations

from collections.abc import Iterator

import duckdb
from fastapi import Request

from satsa.config import Settings
from satsa.db.connection import Database


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_db_dep(request: Request) -> Database:
    return request.app.state.db


def get_reader(request: Request) -> Iterator[duckdb.DuckDBPyConnection]:
    """A read-only cursor for the duration of one request."""
    db: Database = request.app.state.db
    cur = db.reader()
    try:
        yield cur
    finally:
        cur.close()
