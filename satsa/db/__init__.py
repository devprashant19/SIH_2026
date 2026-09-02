"""Embedded DuckDB storage: connection management, schema migration, query helpers."""

from satsa.db.connection import Database, get_database
from satsa.db.migrate import apply_schema

__all__ = ["Database", "get_database", "apply_schema"]
