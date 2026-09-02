"""DuckDB connection management.

DuckDB allows one read-write process per database file. Inside that process we keep a
single connection and hand out cursors: readers get a cheap ``cursor()`` each, writers
take a process-wide lock so pipeline runs, ingests and feedback writes never interleave.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import duckdb

from satsa.config import Settings, get_settings


class Database:
    def __init__(self, path: Path | str, *, read_only: bool = False) -> None:
        self.path = Path(path)
        self.read_only = read_only
        if not read_only and str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(self.path), read_only=read_only)
        self._write_lock = threading.RLock()

    # --- readers ------------------------------------------------------------------

    def reader(self) -> duckdb.DuckDBPyConnection:
        """A cursor for read-only work. Safe to use from any thread; close when done."""
        return self._conn.cursor()

    @contextmanager
    def read(self) -> Iterator[duckdb.DuckDBPyConnection]:
        cur = self.reader()
        try:
            yield cur
        finally:
            cur.close()

    # --- writers ------------------------------------------------------------------

    @contextmanager
    def write(self) -> Iterator[duckdb.DuckDBPyConnection]:
        """Exclusive write access wrapped in a transaction (commit on success, rollback on error)."""
        if self.read_only:
            raise RuntimeError("database opened read-only")
        with self._write_lock:
            cur = self._conn.cursor()
            cur.begin()
            try:
                yield cur
                cur.commit()
            except Exception:
                cur.rollback()
                raise
            finally:
                cur.close()

    def try_write_lock(self) -> bool:
        """Non-blocking probe used by the API to answer 409 when a run is already active."""
        acquired = self._write_lock.acquire(blocking=False)
        if acquired:
            self._write_lock.release()
        return acquired

    def close(self) -> None:
        self._conn.close()


_db_singleton: Database | None = None
_db_lock = threading.Lock()


def get_database(settings: Settings | None = None) -> Database:
    """Process-wide Database bound to settings.db_path (used by API and CLI)."""
    global _db_singleton
    with _db_lock:
        if _db_singleton is None:
            settings = settings or get_settings()
            _db_singleton = Database(settings.db_path)
        return _db_singleton


def reset_database_singleton() -> None:
    global _db_singleton
    with _db_lock:
        if _db_singleton is not None:
            _db_singleton.close()
        _db_singleton = None
