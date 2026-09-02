"""Batch ingestion of CSE submissions: adapters -> mapping -> validation -> DuckDB."""

from satsa.ingest.loader import IngestResult, ingest_path, ingest_submission

__all__ = ["IngestResult", "ingest_path", "ingest_submission"]
