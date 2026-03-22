#!/usr/bin/env python3
"""Auto-retraining daemon for scheduler model versions."""

from __future__ import annotations

import argparse
import json
import re
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
TRAIN_REPORT_PATH = REPO_ROOT / "results" / "scheduler_training_report.json"
ACTIVE_MODEL_PATH = REPO_ROOT / "results" / "active_model.json"
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

    def _load_active_model(self) -> Dict:
        if not ACTIVE_MODEL_PATH.exists():
            md = self._load_metadata()
            return {"version": md.get("version", "v1.0"), "model_ready": bool(md)}
        try:
            return json.loads(ACTIVE_MODEL_PATH.read_text(encoding="utf-8"))
        except Exception:
            md = self._load_metadata()
            return {"version": md.get("version", "v1.0"), "model_ready": bool(md)}

    def _set_active_model(self, version: str, model_ready: bool = True) -> None:
        ACTIVE_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        ACTIVE_MODEL_PATH.write_text(
            json.dumps(
                {
                    "version": version,
                    "model_ready": model_ready,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _metrics_from_payload(payload: Dict) -> Dict[str, float]:
        return {
            "accuracy": float(payload.get("top1", payload.get("accuracy", 0.0)) or 0.0),
            "precision": float(payload.get("precision", payload.get("top1", 0.0)) or 0.0),
            "recall": float(payload.get("recall", payload.get("top1", 0.0)) or 0.0),
            "f1": float(payload.get("f1", payload.get("top1", 0.0)) or 0.0),
            "top3": float(payload.get("top3", 0.0) or 0.0),
        }

    def _load_training_metrics(self) -> Dict[str, float]:
        if TRAIN_REPORT_PATH.exists():
            payload = json.loads(TRAIN_REPORT_PATH.read_text(encoding="utf-8"))
            return self._metrics_from_payload(payload)
        return self._metrics_from_payload(self._load_metadata())

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

    def compare_model_versions(
        self,
        v_old: str,
        v_new: str,
        old_metrics: Dict[str, float],
        new_metrics: Dict[str, float],
    ) -> Dict:
        deltas = {
            key: float(new_metrics.get(key, 0.0)) - float(old_metrics.get(key, 0.0))
            for key in ["accuracy", "precision", "recall", "f1", "top3"]
        }

        improvements = [d for d in deltas.values() if d > 0.0]
        degradations = [d for d in deltas.values() if d < 0.0]
        if improvements and not degradations:
            outcome = "improved"
        elif degradations and not improvements:
            outcome = "degraded"
        elif improvements and degradations:
            outcome = "neutral"
        else:
            outcome = "neutral"

        report_path = REPO_ROOT / "results" / f"model_comparison_{v_new}.txt"
        lines = [
            f"old_version={v_old}",
            f"new_version={v_new}",
            f"outcome={outcome}",
        ]
        for key in ["accuracy", "precision", "recall", "f1", "top3"]:
            lines.append(
                f"{key}: old={old_metrics.get(key, 0.0):.6f} new={new_metrics.get(key, 0.0):.6f} delta={deltas[key]:+.6f}"
            )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        return {
            "outcome": outcome,
            "deltas": deltas,
            "report_path": str(report_path),
        }

    def on_retrain_complete(self, version: str, metrics: Dict[str, float], old_metrics: Dict[str, float], old_version: str) -> Dict:
        print(f"v{version} retrain complete" if not version.startswith("v") else f"{version} retrain complete")

        test_cmd = [sys.executable, str(REPO_ROOT / "tests" / f"test_model_{version}.py")]
        tests_passed = True
        if Path(test_cmd[-1]).exists():
            tests_passed = subprocess.run(test_cmd, check=False).returncode == 0

        cmp_result = self.compare_model_versions(old_version, version, old_metrics, metrics)

        retrain_report = REPO_ROOT / "results" / f"retrain_{version}.txt"
        retrain_report.write_text(json.dumps({"version": version, "metrics": metrics, "tests_passed": tests_passed}, indent=2), encoding="utf-8")

        accuracy_drop = max(0.0, float(old_metrics.get("accuracy", 0.0)) - float(metrics.get("accuracy", 0.0)))
        degraded_over_threshold = accuracy_drop > 0.02

        if (not tests_passed) or degraded_over_threshold:
            # Auto rollback keeps v1.1 (or previous active) metadata as active
            old_meta = self._load_metadata()
            old_meta["version"] = old_version
            old_meta["top1"] = old_metrics.get("accuracy", old_meta.get("top1", 0.0))
            old_meta["top3"] = old_metrics.get("top3", old_meta.get("top3", 0.0))
            old_meta["precision"] = old_metrics.get("precision", old_meta.get("precision", old_meta.get("top1", 0.0)))
            old_meta["recall"] = old_metrics.get("recall", old_meta.get("recall", old_meta.get("top1", 0.0)))
            old_meta["f1"] = old_metrics.get("f1", old_meta.get("f1", old_meta.get("top1", 0.0)))
            self.meta_path.write_text(json.dumps(old_meta, indent=2), encoding="utf-8")
            self._set_active_model(old_version, model_ready=True)
            print("⚠️ v1.2 degraded — rolled back" if version == "v1.2" else f"⚠️ {version} degraded — rolled back")
            return {"activated": False, "rolled_back": True, "tests_passed": tests_passed, "comparison": cmp_result}

        self._set_active_model(version, model_ready=True)
        improvement_pct = round(max(0.0, (metrics.get("accuracy", 0.0) - old_metrics.get("accuracy", 0.0)) * 100.0), 2)
        if version == "v1.2":
            print(f"✅ v1.2 active — {improvement_pct}% improvement")
        else:
            print(f"✅ {version} active — {improvement_pct}% improvement")
        return {"activated": True, "rolled_back": False, "tests_passed": tests_passed, "comparison": cmp_result}

    def check_and_retrain(self, force: bool = False) -> Dict:
        current_md = self._load_metadata()
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
        old_metrics = self._metrics_from_payload(current_md)
        new_metrics = self._load_training_metrics()

        self._backup_existing_model(current.version)
        hook_result = self.on_retrain_complete(next_version, new_metrics, old_metrics, current.version)
        deployed = bool(hook_result.get("activated", False))
        improved = hook_result.get("comparison", {}).get("outcome") == "improved"
        new_top3 = float(new_metrics.get("top3", 0.0))

        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": next_version,
            "data_rows": rows,
            "old_top3": current.top3,
            "new_top3": new_top3,
            "improved": improved,
            "deployed": deployed,
            "rolled_back": bool(hook_result.get("rolled_back", False)),
        }
        self._append_history(record)
        return record

    def status(self) -> None:
        st = self.current_state()
        active = self._load_active_model()
        rows = self.get_sqlite_row_count()
        next_version, threshold = self._next_target(st.version)
        eta = self.estimate_eta_days(rows, threshold)
        print(f"Current model: {active.get('version', st.version)} | Top-3: {st.top3*100:.2f}%")
        print(f"Rows: {rows:,} / {threshold:,} threshold for {next_version}")
        print(f"Next retrain ETA: ~{eta} days")
        print(f"Model ready: {str(bool(active.get('model_ready', True))).lower()}")
        print(f"Active model: {active.get('version', st.version)}")

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
