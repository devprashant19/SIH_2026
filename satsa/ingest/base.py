"""Adapter contract. Each adapter turns one submission file into raw string DataFrames per table."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd

TABLES = ("alerts", "assets", "entities", "escalations", "incidents")


def blank_to_none(df: pd.DataFrame) -> pd.DataFrame:
    """All-string frame with '' -> None so downstream null checks are uniform."""
    out = df.copy()
    for col in out.columns:
        out[col] = out[col].astype("string").str.strip()
        out[col] = out[col].mask(out[col] == "", None)
        out[col] = out[col].astype(object).where(out[col].notna(), None)
    return out


class BaseAdapter(ABC):
    name: str = "base"
    extensions: tuple[str, ...] = ()

    @classmethod
    def detect(cls, path: Path) -> bool:
        return path.suffix.lower() in cls.extensions

    @abstractmethod
    def read(self, path: Path) -> dict[str, pd.DataFrame]:
        """Return {table_name: DataFrame of strings} for the tables present in the file."""


def guess_table_from_name(path: Path) -> str:
    stem = path.stem.lower()
    for table in ("assets", "entities", "escalations", "incidents"):
        if stem.endswith(table) or f"_{table}" in stem:
            return table
    return "alerts"
