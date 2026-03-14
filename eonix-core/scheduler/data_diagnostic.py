#!/usr/bin/env python3
"""Quick diagnostics for scheduler collector data."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd


DEFAULT_DB = Path.home() / ".eonix" / "scheduler_data.db"


def run_diagnostic(db_path: Path = DEFAULT_DB) -> None:
    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql("SELECT * FROM events", conn)
    finally:
        conn.close()

    if df.empty:
        print("Total rows:    0")
        print("Unique procs:  0")
        print("Avg/class:     0")
        print("Date range:    N/A -> N/A")
        return

    name_col = "name" if "name" in df.columns else "comm"
    unique = df[name_col].nunique()
    avg_per_class = len(df) // max(unique, 1)

    print(f"Total rows:    {len(df):,}")
    print(f"Unique procs:  {unique}")
    print(f"Avg/class:     {avg_per_class}")
    print(f"Date range:    {df['timestamp'].min()} -> {df['timestamp'].max()}")
    print()
    print("Top 10 processes:")
    print(df[name_col].value_counts().head(10).to_string())


if __name__ == "__main__":
    run_diagnostic()
