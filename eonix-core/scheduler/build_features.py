#!/usr/bin/env python3
"""Build scheduler feature matrix v2 for ML training."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pandas as pd


DB_PATH = Path.home() / ".eonix" / "scheduler_data.db"
REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "datasets" / "scheduler"
OUT_PARQUET = OUT_DIR / "feature_matrix_v2.parquet"
OUT_META = OUT_DIR / "feature_matrix_v2_meta.json"


def _load_launch_events(db_path: Path) -> pd.DataFrame:
    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql_query(
            "SELECT * FROM events WHERE event_type='LAUNCH' ORDER BY timestamp",
            conn,
        )
    finally:
        conn.close()
    return df


def build_feature_matrix_v2(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        raise ValueError("No LAUNCH events available.")

    work = df.copy().reset_index(drop=True)
    work["proc_name"] = work["name"].fillna("unknown")

    work["hour_of_day"] = work["session_hour"].astype(int)
    work["day_of_week"] = work["session_dow"].astype(int)
    work["is_weekend"] = work["day_of_week"].isin([5, 6]).astype(int)
    work["cpu_pressure"] = work["cpu_percent"].fillna(0.0).clip(0, 100) / 100.0
    work["ram_pressure"] = work["memory_percent"].fillna(0.0).clip(0, 100) / 100.0
    work["ppid"] = work["parent_pid"].fillna(0).astype(int)
    work["pid_mod_10"] = work["pid"].fillna(0).astype(int) % 10
    work["launch_burst_5m"] = 0

    ts = work["timestamp"].values
    names = work["proc_name"].values
    burst = []
    for i in range(len(work)):
        cutoff = ts[i] - 300
        j = i - 1
        c = 0
        while j >= 0 and ts[j] >= cutoff:
            if names[j] == names[i]:
                c += 1
            j -= 1
        burst.append(c)
    work["launch_burst_5m"] = burst

    for k in range(1, 11):
        work[f"prev_{k}"] = work["proc_name"].shift(k).fillna("UNKNOWN")

    work["next_process_name"] = work["proc_name"].shift(-1)
    work = work.dropna(subset=["next_process_name"]).reset_index(drop=True)

    feature_cols = [
        "hour_of_day",
        "day_of_week",
        "is_weekend",
        "cpu_pressure",
        "ram_pressure",
        "ppid",
        "pid_mod_10",
        "launch_burst_5m",
    ] + [f"prev_{k}" for k in range(1, 11)]

    result = work[feature_cols + ["next_process_name", "timestamp", "pid", "proc_name"]]
    return result


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Collector DB missing: {DB_PATH}")

    raw = _load_launch_events(DB_PATH)
    matrix = build_feature_matrix_v2(raw)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    matrix.to_parquet(OUT_PARQUET, index=False)

    feature_count = 18
    unique_classes = int(matrix["next_process_name"].nunique())
    metadata = {
        "rows": int(len(matrix)),
        "feature_count": feature_count,
        "unique_classes": unique_classes,
        "source_db": os.fspath(DB_PATH),
    }
    OUT_META.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(f"feature_matrix_v2.parquet saved: {OUT_PARQUET}")
    print(f"{len(matrix)} rows x {feature_count} features")
    print(f"Unique classes: {unique_classes}")


if __name__ == "__main__":
    main()


def test_build_feature_matrix_v2_rejects_empty_input():
    df = pd.DataFrame()
    try:
        build_feature_matrix_v2(df)
        assert False, "expected ValueError for empty launch events"
    except ValueError as exc:
        assert "No LAUNCH events" in str(exc)


def test_build_feature_matrix_v2_derives_expected_columns():
    df = pd.DataFrame(
        [
            {
                "timestamp": 1000,
                "name": "code",
                "session_hour": 10,
                "session_dow": 1,
                "cpu_percent": 12.0,
                "memory_percent": 45.0,
                "parent_pid": 10,
                "pid": 101,
            },
            {
                "timestamp": 1100,
                "name": "python",
                "session_hour": 10,
                "session_dow": 1,
                "cpu_percent": 22.0,
                "memory_percent": 50.0,
                "parent_pid": 10,
                "pid": 102,
            },
            {
                "timestamp": 1180,
                "name": "code",
                "session_hour": 10,
                "session_dow": 1,
                "cpu_percent": 30.0,
                "memory_percent": 60.0,
                "parent_pid": 10,
                "pid": 103,
            },
        ]
    )

    out = build_feature_matrix_v2(df)
    assert len(out) == 2
    assert "next_process_name" in out.columns
    assert "launch_burst_5m" in out.columns
    assert int(out["launch_burst_5m"].min()) >= 0
