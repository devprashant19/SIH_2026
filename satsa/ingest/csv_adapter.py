"""CSV / TSV adapter. One file = one table; the table is inferred from the file name."""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd

from satsa.ingest.base import BaseAdapter, blank_to_none, guess_table_from_name


class CsvAdapter(BaseAdapter):
    name = "csv"
    extensions = (".csv", ".tsv", ".txt")

    def read(self, path: Path) -> dict[str, pd.DataFrame]:
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            sample = fh.read(8192)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            sep = dialect.delimiter
        except csv.Error:
            sep = "\t" if path.suffix.lower() == ".tsv" else ","
        df = pd.read_csv(path, sep=sep, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        df.columns = [str(c).strip() for c in df.columns]
        return {guess_table_from_name(path): blank_to_none(df)}
