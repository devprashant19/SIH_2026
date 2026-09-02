"""JSON adapter.

Accepted shapes:
  - a JSON array of alert records
  - JSON Lines (one record per line)
  - an object with any of the table keys: {"entity": {...}, "alerts": [...], "assets": [...], ...}
Nested records are flattened with dotted keys (e.g. "analyst.id"); mapping files can alias them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from satsa.ingest.base import TABLES, BaseAdapter, blank_to_none


def _records_to_df(records: list[dict]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    df = pd.json_normalize(records, sep=".")
    # Lists (e.g. expected_telemetry_sources) are kept as lists, everything else as strings.
    for col in df.columns:
        df[col] = df[col].map(lambda v: v if isinstance(v, list) else ("" if v is None else str(v)))
    return df


class JsonAdapter(BaseAdapter):
    name = "json"
    extensions = (".json", ".jsonl", ".ndjson")

    def read(self, path: Path) -> dict[str, pd.DataFrame]:
        text = path.read_text(encoding="utf-8-sig")
        stripped = text.lstrip()
        if path.suffix.lower() in (".jsonl", ".ndjson") or (stripped and stripped[0] == "{" and "\n{" in stripped):
            try:
                data = [json.loads(line) for line in text.splitlines() if line.strip()]
            except json.JSONDecodeError:
                data = json.loads(text)
        else:
            data = json.loads(text)

        out: dict[str, pd.DataFrame] = {}
        if isinstance(data, list):
            out["alerts"] = _records_to_df(data)
        elif isinstance(data, dict):
            for table in TABLES:
                if table in data and isinstance(data[table], list):
                    out[table] = _records_to_df(data[table])
            if "entity" in data and isinstance(data["entity"], dict):
                out["entities"] = _records_to_df([data["entity"]])
            if not out:  # a single alert object
                out["alerts"] = _records_to_df([data])
        else:
            raise ValueError(f"{path}: unsupported JSON top-level type {type(data).__name__}")

        return {k: _clean(v) for k, v in out.items()}


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    list_cols = [c for c in df.columns if df[c].map(lambda v: isinstance(v, list)).any()]
    scalar = blank_to_none(df.drop(columns=list_cols)) if len(df.columns) > len(list_cols) else df.iloc[:, :0]
    for c in list_cols:
        scalar[c] = df[c]
    return scalar
