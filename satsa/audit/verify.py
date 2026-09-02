"""Recompute the audit hash chain and report the first broken link, if any."""

from __future__ import annotations

from dataclasses import dataclass

import duckdb

from satsa.audit.hashing import chain_hash
from satsa.db.repo import fetch_df


@dataclass
class VerifyResult:
    ok: bool
    n_runs: int
    first_broken_run_id: str | None = None
    detail: str | None = None


def verify_chain(conn: duckdb.DuckDBPyConnection) -> VerifyResult:
    df = fetch_df(conn, "SELECT run_id, prev_run_hash, config_hash, code_hash, input_hash, output_hash, status, run_hash FROM audit_runs WHERE finished_at IS NOT NULL ORDER BY finished_at, run_id")
    prev = None
    for r in df.itertuples(index=False):
        expected = chain_hash(r.prev_run_hash, r.run_id, r.config_hash, r.code_hash, r.input_hash, r.output_hash, r.status)
        if expected != r.run_hash:
            return VerifyResult(False, len(df), r.run_id, "run_hash does not match its recorded inputs")
        if prev is not None and r.prev_run_hash != prev:
            return VerifyResult(False, len(df), r.run_id, "prev_run_hash does not point at the previous finalised run")
        prev = r.run_hash
    return VerifyResult(True, len(df))
