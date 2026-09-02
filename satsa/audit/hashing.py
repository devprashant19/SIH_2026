"""Deterministic hashing used for submission ids, manifests and the audit hash chain."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd
from ulid import ULID


def new_id(prefix: str = "") -> str:
    """Time-ordered unique id (ULID) with an optional prefix, e.g. 'run_01J...'."""
    return f"{prefix}{ULID()}"


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_file(path: Path | str, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while chunk := fh.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def hash_obj(obj: Any) -> str:
    """SHA-256 of canonical JSON (sorted keys, no whitespace)."""
    return hash_bytes(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8"))


def hash_dataframe(df: pd.DataFrame, sort_by: list[str] | None = None) -> str:
    """Order-independent hash of a DataFrame: sorted columns, sorted rows, CSV bytes."""
    if df is None or df.empty:
        return hash_bytes(b"")
    frame = df.reindex(sorted(df.columns), axis=1).copy()
    for col in frame.columns:
        if frame[col].dtype == object and frame[col].map(lambda v: isinstance(v, (list, dict, tuple, set)) or hasattr(v, "tolist")).any():
            frame[col] = frame[col].map(lambda v: json.dumps(v.tolist() if hasattr(v, "tolist") else (sorted(v) if isinstance(v, set) else v), sort_keys=True, default=str))
    keys = [c for c in (sort_by or []) if c in frame.columns] or list(frame.columns)
    frame = frame.sort_values(keys, kind="mergesort").reset_index(drop=True)
    return hash_bytes(frame.to_csv(index=False, date_format="%Y-%m-%dT%H:%M:%S.%f").encode("utf-8"))


def chain_hash(*parts: str | None) -> str:
    """Hash chain link: sha256 of the parts joined with '|' (None -> '')."""
    return hash_bytes("|".join(p or "" for p in parts).encode("utf-8"))
