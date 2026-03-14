#!/usr/bin/env python3
"""Auto-retraining daemon for scheduler model versions."""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = Path.home() / ".eonix" / "scheduler_data.db"
META_PATH = REPO_ROOT / "models" / "onnx" / "model_metadata.json"
HISTORY_PATH = REPO_ROOT / "results" / "retrain_history.json"
TRAIN_SCRIPT = REPO_ROOT / "eonix-core" / "scheduler" / "train_scheduler.py"
BUILD_SCRIPT = REPO_ROOT / "eonix-core" / "scheduler" / "build_features.py"
MODEL_ONNX = REPO_ROOT / "models" / "onnx" / "scheduler.onnx"

VERSION_THRESHOLDS = [
    ("v1.1", 60000),
    ("v1.2", 120000),
    ("v1.3", 200000),
    ("v1.4", 320000),
    ("v1.5", 473000),
]


@dataclass
class ModelState:
    version: str
    top3: float


class AutoRetrainer:
    def __init__(self, db_path: Path = DB_PATH, meta_path: Path = META_PATH, history_path: Path = HISTORY_PATH):
        self.db_path = db_path
        self.meta_path = meta_path
        self.history_path = history_path

    def get_sqlite_row_count(self) -> int:
        if not self.db_path.exists():
            return 0
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.execute("SELECT COUNT(*) FROM events")
            return int(cur.fetchone()[0])
        finally:
            conn.close()

    def _load_metadata(self) -> Dict:
        if not self.meta_path.exists():
            return {"version": "v1.0", "top3": 0.0}
        return json.loads(self.meta_path.read_text(encoding="utf-8"))

    def current_state(self) -> ModelState:
        md = self._load_metadata()
        return ModelState(version=md.get("version", "v1.0"), top3=float(md.get("top3", 0.0)))

    def _next_target(self, current_version: str):
        for ver, threshold in VERSION_THRESHOLDS:
            if ver > current_version:
                return ver, threshold
        return VERSION_THRESHOLDS[-1]

    def estimate_eta_days(self, rows: int, threshold: int, rows_per_day: float = 5000.0) -> float:
        if rows >= threshold:
            return 0.0
        remaining = threshold - rows
        return round(remaining / max(rows_per_day, 1.0), 2)

    def _append_history(self, record: Dict) -> None:
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        history: List[Dict] = []
        if self.history_path.exists():
            history = json.loads(self.history_path.read_text(encoding="utf-8"))
        history.append(record)
        self.history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")

    def _backup_existing_model(self, version: str) -> None:
        if MODEL_ONNX.exists():
            backup = MODEL_ONNX.with_name(f"scheduler_{version}_backup.onnx")
            backup.write_bytes(MODEL_ONNX.read_bytes())

    def check_and_retrain(self, force: bool = False) -> Dict:
        current = self.current_state()
        rows = self.get_sqlite_row_count()
        next_version, threshold = self._next_target(current.version)

        print(f"Current model: {current.version} | Top-3: {current.top3*100:.2f}%")
        print(f"Rows: {rows:,} / {threshold:,} threshold")

        if rows < threshold and not force:
            eta = self.estimate_eta_days(rows, threshold)
            print(f"Next retrain ETA: ~{eta} days")
            return {"triggered": False, "eta_days": eta, "rows": rows}

        subprocess.run([sys.executable, str(BUILD_SCRIPT)], check=True)
        subprocess.run([
            sys.executable, str(TRAIN_SCRIPT), "--trials", "20", "--version", next_version
        ], check=True)

        new_meta = json.loads(META_PATH.read_text(encoding="utf-8"))
        new_top3 = float(new_meta.get("top3", 0.0))
        improved = new_top3 > current.top3

        deployed = False
        if improved:
            self._backup_existing_model(current.version)
            deployed = True
            print(f"✅ DEPLOYED {next_version}: {current.top3*100:.2f}% → {new_top3*100:.2f}% Top-3")
        else:
            print("⚠️ No improvement — keeping current")
            new_meta["version"] = current.version
            new_meta["top3"] = current.top3
            META_PATH.write_text(json.dumps(new_meta, indent=2), encoding="utf-8")

        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": next_version,
            "data_rows": rows,
            "old_top3": current.top3,
            "new_top3": new_top3,
            "improved": improved,
            "deployed": deployed,
        }
        self._append_history(record)
        return record

    def status(self) -> None:
        st = self.current_state()
        rows = self.get_sqlite_row_count()
        next_version, threshold = self._next_target(st.version)
        eta = self.estimate_eta_days(rows, threshold)
        print(f"Current model: {st.version} | Top-3: {st.top3*100:.2f}%")
        print(f"Rows: {rows:,} / {threshold:,} threshold for {next_version}")
        print(f"Next retrain ETA: ~{eta} days")

    def print_history(self) -> None:
        if not self.history_path.exists():
            print("No retrain history yet.")
            return
        print(self.history_path.read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Eonix Scheduler auto retrainer")
    p.add_argument("--check", action="store_true")
    p.add_argument("--daemon", action="store_true")
    p.add_argument("--status", action="store_true")
    p.add_argument("--history", action="store_true")
    p.add_argument("--force", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    retrainer = AutoRetrainer()

    if args.status:
        retrainer.status()
        return
    if args.history:
        retrainer.print_history()
        return
    if args.check:
        retrainer.check_and_retrain(force=args.force)
        return
    if args.daemon:
        while True:
            retrainer.check_and_retrain(force=False)
            time.sleep(21600)
        return

    retrainer.status()


if __name__ == "__main__":
    main()


def test_eta_calculation_correct():
    r = AutoRetrainer()
    eta = r.estimate_eta_days(rows=30000, threshold=60000, rows_per_day=5000)
    assert eta == 6.0


def test_no_retrain_below_threshold(tmp_path):
    db = tmp_path / "scheduler_data.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, timestamp REAL)")
    conn.executemany("INSERT INTO events(timestamp) VALUES (?)", [(1.0,), (2.0,), (3.0,)])
    conn.commit()
    conn.close()

    meta = tmp_path / "model_metadata.json"
    meta.write_text(json.dumps({"version": "v1.0", "top3": 0.5}), encoding="utf-8")

    hist = tmp_path / "retrain_history.json"
    retrainer = AutoRetrainer(db_path=db, meta_path=meta, history_path=hist)
    out = retrainer.check_and_retrain(force=False)
    assert out["triggered"] is False
    assert "eta_days" in out


def test_retrain_history_appends_correctly(tmp_path):
    hist = tmp_path / "retrain_history.json"
    retrainer = AutoRetrainer(history_path=hist)
    retrainer._append_history({"version": "v1.1", "deployed": True})
    retrainer._append_history({"version": "v1.2", "deployed": False})
    data = json.loads(hist.read_text(encoding="utf-8"))
    assert len(data) == 2
    assert data[-1]["version"] == "v1.2"
