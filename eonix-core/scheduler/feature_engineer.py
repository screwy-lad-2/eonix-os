"""
Eonix OS — Scheduler Feature Engineer
=======================================
Reads raw LAUNCH/EXIT events from the data collector's SQLite DB and
engineers a feature matrix suitable for ML model training.

Input:  ~/.eonix/scheduler_data.db  (events table)
Output: datasets/scheduler/feature_matrix.parquet
        datasets/scheduler/feature_stats.json

Run:    python feature_engineer.py
Test:   python -m pytest feature_engineer.py -v
"""

import json
import os
import sqlite3
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DB_PATH = os.path.join(os.path.expanduser("~"), ".eonix", "scheduler_data.db")
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = REPO_ROOT / "datasets" / "scheduler"

# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

def load_events(db_path: str = DB_PATH) -> pd.DataFrame:
    """Load LAUNCH events from the collector database."""
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(
        "SELECT * FROM events WHERE event_type = 'LAUNCH' ORDER BY timestamp",
        conn,
    )
    conn.close()
    return df


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build the full feature matrix from raw LAUNCH events."""
    df = df.copy()

    # -- Time features --
    df["hour_of_day"] = df["session_hour"].astype(int)
    df["day_of_week"] = df["session_dow"].astype(int)

    # -- Pressure features (already 0-1) --
    df["cpu_pressure"] = df["cpu_percent"].clip(0.0, 100.0) / 100.0
    df["ram_pressure"] = df["memory_percent"].clip(0.0, 1.0)

    # -- Previous-process context (last 10 launched) --
    for k in range(1, 11):
        df[f"prev_{k}"] = df["name"].shift(k)

    # -- Rolling 5-min frequency of same process --
    df["ts"] = df["timestamp"]
    freq_list = []
    names = df["name"].values
    timestamps = df["ts"].values
    for i in range(len(df)):
        cutoff = timestamps[i] - 300  # 5 minutes
        count = 0
        j = i - 1
        while j >= 0 and timestamps[j] >= cutoff:
            if names[j] == names[i]:
                count += 1
            j -= 1
        freq_list.append(count)
    df["rolling_5min_freq"] = freq_list

    # -- Co-occurrence score: how often this process appears near
    #    the top-3 most frequent processes globally --
    top3 = df["name"].value_counts().head(3).index.tolist()
    co_scores = []
    for i in range(len(df)):
        window_start = max(0, i - 10)
        window = set(names[window_start:i])
        score = sum(1 for t in top3 if t in window)
        co_scores.append(score)
    df["co_occurrence_score"] = co_scores

    # -- Inter-arrival gap: seconds since this process last launched --
    last_seen: dict[str, float] = {}
    gaps = []
    for i in range(len(df)):
        name = names[i]
        ts = timestamps[i]
        if name in last_seen:
            gaps.append(float(ts - last_seen[name]))
        else:
            gaps.append(0.0)
        last_seen[name] = ts
    df["inter_arrival_gap"] = gaps

    # -- Target: next process name --
    df["next_process_name"] = df["name"].shift(-1)

    # -- Drop rows with null target (last row) and null prev columns --
    df = df.dropna(subset=["next_process_name"])

    # Fill any remaining NaN in prev_* columns with "UNKNOWN"
    for k in range(1, 11):
        df[f"prev_{k}"] = df[f"prev_{k}"].fillna("UNKNOWN")

    # -- Select final feature columns --
    feature_cols = (
        ["hour_of_day", "day_of_week", "cpu_pressure", "ram_pressure"]
        + [f"prev_{k}" for k in range(1, 11)]
        + ["rolling_5min_freq", "co_occurrence_score", "inter_arrival_gap"]
    )
    target_col = "next_process_name"

    # Also keep some metadata for traceability
    result = df[feature_cols + [target_col, "name", "pid", "timestamp"]].copy()
    result = result.reset_index(drop=True)
    return result


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export_results(df: pd.DataFrame, output_dir: Path = OUTPUT_DIR):
    """Save feature matrix as parquet and stats as JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Parquet
    parquet_path = output_dir / "feature_matrix.parquet"
    df.to_parquet(parquet_path, index=False)
    print(f"  Parquet: {parquet_path} ({len(df)} rows)")

    # Stats JSON (numeric columns only)
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    stats = {}
    for col in numeric_cols:
        stats[col] = {
            "mean": float(df[col].mean()),
            "std": float(df[col].std()),
            "min": float(df[col].min()),
            "max": float(df[col].max()),
        }
    stats_path = output_dir / "feature_stats.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)
    print(f"  Stats:   {stats_path}")


def print_summary(df: pd.DataFrame):
    """Print a human-readable summary of the feature matrix."""
    print(f"\n  Total samples:        {len(df)}")
    print(f"  Unique target classes: {df['next_process_name'].nunique()}")
    print(f"\n  Top 10 most frequent targets:")
    for name, count in df["next_process_name"].value_counts().head(10).items():
        pct = 100.0 * count / len(df)
        print(f"    {name:30s}  {count:5d}  ({pct:.1f}%)")

    numeric = df.select_dtypes(include=[np.number])
    if len(numeric.columns) > 1:
        print(f"\n  Feature correlations (numeric):")
        corr = numeric.corr()
        print(corr.to_string())


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    print("Eonix Feature Engineer")
    print("=" * 40)

    if not os.path.exists(DB_PATH):
        print(f"  ERROR: DB not found at {DB_PATH}")
        print("  Start the collector first: python collect_data.py --start")
        return

    df_raw = load_events()
    print(f"  Loaded {len(df_raw)} LAUNCH events from {DB_PATH}")

    if len(df_raw) < 12:
        print("  ERROR: Need at least 12 events to engineer features")
        return

    df = engineer_features(df_raw)
    export_results(df)
    print_summary(df)


if __name__ == "__main__":
    main()


# ===========================================================================
# Tests
# ===========================================================================

def _make_test_df(n: int = 50) -> pd.DataFrame:
    """Create a minimal synthetic DataFrame for testing."""
    rng = np.random.RandomState(42)
    names = ["chrome.exe", "code.exe", "explorer.exe", "python.exe", "svchost.exe"]
    rows = []
    t = 1700000000.0
    for i in range(n):
        t += rng.uniform(1, 30)
        rows.append({
            "id": i + 1,
            "timestamp": t,
            "event_type": "LAUNCH",
            "pid": rng.randint(1000, 30000),
            "name": rng.choice(names),
            "cpu_percent": rng.uniform(0, 50),
            "memory_percent": rng.uniform(0.1, 0.9),
            "parent_pid": rng.randint(1, 1000),
            "session_hour": rng.randint(0, 24),
            "session_dow": rng.randint(0, 7),
        })
    return pd.DataFrame(rows)


class TestFeatureMatrix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = _make_test_df(50)
        cls.df = engineer_features(cls.raw)

    def test_feature_matrix_has_correct_columns(self):
        expected = {"hour_of_day", "day_of_week", "cpu_pressure", "ram_pressure",
                    "rolling_5min_freq", "co_occurrence_score", "inter_arrival_gap",
                    "next_process_name", "name", "pid", "timestamp"}
        expected.update({f"prev_{k}" for k in range(1, 11)})
        self.assertTrue(expected.issubset(set(self.df.columns)),
                        f"Missing columns: {expected - set(self.df.columns)}")

    def test_no_null_values_in_features(self):
        feature_cols = ["hour_of_day", "day_of_week", "cpu_pressure",
                        "ram_pressure", "rolling_5min_freq",
                        "co_occurrence_score", "inter_arrival_gap"]
        for col in feature_cols:
            self.assertFalse(self.df[col].isnull().any(),
                             f"Null values in {col}")

    def test_target_column_exists(self):
        self.assertIn("next_process_name", self.df.columns)
        self.assertFalse(self.df["next_process_name"].isnull().any())

    def test_hour_range_valid(self):
        self.assertTrue((self.df["hour_of_day"] >= 0).all())
        self.assertTrue((self.df["hour_of_day"] <= 23).all())

    def test_pressure_range_valid(self):
        for col in ["cpu_pressure", "ram_pressure"]:
            self.assertTrue((self.df[col] >= 0.0).all(),
                            f"{col} has values < 0")
            self.assertTrue((self.df[col] <= 1.0).all(),
                            f"{col} has values > 1")
