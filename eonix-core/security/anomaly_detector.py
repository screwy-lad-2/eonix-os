#!/usr/bin/env python3
"""
Eonix OS — Security Anomaly Detector
=====================================
Builds behavioral fingerprints from security_alerts.log and
uses Isolation Forest for real-time anomaly detection.

Usage:
    python3 anomaly_detector.py --train    Train model on ADFA-LD or synthetic data
    python3 anomaly_detector.py --detect   Real-time anomaly detection loop
    python3 anomaly_detector.py --status   Show model info

Pytest:
    python3 -m pytest anomaly_detector.py -v
"""

import os
import sys
import time
import signal
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import joblib

# ---- Paths ----

HOME = Path.home()
EONIX_DIR = HOME / ".eonix"
ALERTS_LOG = EONIX_DIR / "security_alerts.log"
ANOMALY_LOG = EONIX_DIR / "anomaly_detections.log"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MODEL_DIR = Path("models/security")
MODEL_PATH = MODEL_DIR / "isolation_forest.pkl"
SCALER_PATH = MODEL_DIR / "scaler.pkl"
DATASET_DIR = PROJECT_ROOT / "datasets" / "security"

# Feature names
FEATURE_NAMES = [
    "execve_rate", "openat_rate", "connect_rate", "mmap_rate",
    "fork_rate", "ptrace_ever", "setuid_ever", "unique_files",
    "unique_hosts", "session_duration",
]

# Tiered response thresholds (decision_function scores)
# IsolationForest decision_function: negative = anomaly, positive = normal
# Thresholds calibrated to model score distribution
TIER_LOG = -0.1
TIER_RESTRICT = -0.2
TIER_KILL = -0.3


# =========================================================
# PART 1 — Feature Extraction from security_alerts.log
# =========================================================

def parse_alerts_log(path=None):
    """Parse security_alerts.log into per-process feature vectors."""
    if path is None:
        path = ALERTS_LOG
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=["pid"] + FEATURE_NAMES)

    procs = defaultdict(lambda: {
        "execve": 0, "openat": 0, "connect": 0, "mmap": 0,
        "fork": 0, "ptrace": 0, "setuid": 0,
        "first_ts": None, "last_ts": None, "comm": "",
    })

    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) < 4:
                continue
            ts_str = parts[0]
            pid_part = parts[1]
            comm_part = parts[2]
            alert_part = parts[3]

            pid = int(pid_part.split("=")[1]) if "=" in pid_part else 0
            alert = alert_part.lower()
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except (ValueError, IndexError):
                ts = datetime.now(timezone.utc)

            p = procs[pid]
            if p["first_ts"] is None:
                p["first_ts"] = ts
            p["last_ts"] = ts
            p["comm"] = comm_part

            if "exec" in alert:
                p["execve"] += 1
            elif "openat" in alert or "open" in alert:
                p["openat"] += 1
            elif "connect" in alert or "port_scan" in alert:
                p["connect"] += 1
            elif "mmap" in alert:
                p["mmap"] += 1
            elif "fork" in alert:
                p["fork"] += 1
            elif "ptrace" in alert:
                p["ptrace"] += 1
            elif "setuid" in alert or "privilege" in alert:
                p["setuid"] += 1

    rows = []
    for pid, p in procs.items():
        duration = 1.0
        if p["first_ts"] and p["last_ts"]:
            d = (p["last_ts"] - p["first_ts"]).total_seconds()
            if d > 0:
                duration = d
        rows.append({
            "pid": pid,
            "execve_rate": p["execve"] / duration,
            "openat_rate": p["openat"] / duration,
            "connect_rate": p["connect"] / duration,
            "mmap_rate": p["mmap"] / duration,
            "fork_rate": p["fork"] / duration,
            "ptrace_ever": 1.0 if p["ptrace"] > 0 else 0.0,
            "setuid_ever": 1.0 if p["setuid"] > 0 else 0.0,
            "unique_files": float(p["openat"]),
            "unique_hosts": float(p["connect"]),
            "session_duration": duration,
        })

    return pd.DataFrame(rows)


# =========================================================
# PART 5 — ADFA-LD Dataset Handling
# =========================================================

def load_adfa_ld(dataset_dir=None):
    """Load ADFA-LD syscall traces and engineer features."""
    if dataset_dir is None:
        dataset_dir = DATASET_DIR
    dataset_dir = Path(dataset_dir)

    trace_dirs = list(dataset_dir.rglob("Training_Data_Master"))
    if not trace_dirs:
        trace_dirs = list(dataset_dir.rglob("*Training*"))
    if not trace_dirs:
        trace_files = list(dataset_dir.rglob("*.txt"))
        if not trace_files:
            return None
        return _features_from_trace_files(trace_files)

    all_files = []
    for td in trace_dirs:
        all_files.extend(td.rglob("*.txt"))
    if not all_files:
        return None

    return _features_from_trace_files(all_files)


def _features_from_trace_files(trace_files):
    """Convert syscall trace files to feature vectors."""
    syscall_map = {
        # x86_64
        59: "execve", 257: "openat", 42: "connect", 9: "mmap",
        56: "clone", 101: "ptrace", 105: "setuid",
        # i386 (ADFA-LD was collected on 32-bit Linux)
        11: "execve", 295: "openat", 102: "connect",
        90: "mmap", 192: "mmap",
        120: "clone", 26: "ptrace", 23: "setuid", 213: "setuid",
    }

    rows = []
    for tf in trace_files:
        try:
            with open(tf) as f:
                content = f.read().strip()
            if not content:
                continue
            syscalls = []
            for token in content.split():
                try:
                    syscalls.append(int(token))
                except ValueError:
                    continue
            if len(syscalls) < 5:
                continue
        except (OSError, UnicodeDecodeError):
            continue

        counts = defaultdict(int)
        for sc in syscalls:
            name = syscall_map.get(sc, "")
            if name:
                counts[name] += 1

        duration = max(len(syscalls) / 100.0, 1.0)
        rows.append({
            "execve_rate": counts["execve"] / duration,
            "openat_rate": counts["openat"] / duration,
            "connect_rate": counts["connect"] / duration,
            "mmap_rate": counts["mmap"] / duration,
            "fork_rate": counts["clone"] / duration,
            "ptrace_ever": 1.0 if counts["ptrace"] > 0 else 0.0,
            "setuid_ever": 1.0 if counts["setuid"] > 0 else 0.0,
            "unique_files": float(min(counts["openat"], 50)),
            "unique_hosts": float(min(counts["connect"], 20)),
            "session_duration": duration,
        })

    if not rows:
        return None
    return pd.DataFrame(rows)


def generate_synthetic_training_data(n_samples=500):
    """Generate synthetic normal behavior data for training."""
    rng = np.random.RandomState(42)
    data = {
        "execve_rate": rng.exponential(0.5, n_samples),
        "openat_rate": rng.exponential(2.0, n_samples),
        "connect_rate": rng.exponential(1.0, n_samples),
        "mmap_rate": rng.exponential(1.5, n_samples),
        "fork_rate": rng.exponential(0.3, n_samples),
        "ptrace_ever": np.zeros(n_samples),
        "setuid_ever": np.zeros(n_samples),
        "unique_files": rng.poisson(5, n_samples).astype(float),
        "unique_hosts": rng.poisson(2, n_samples).astype(float),
        "session_duration": rng.exponential(30, n_samples),
    }
    return pd.DataFrame(data)


# =========================================================
# PART 2 — Training Mode
# =========================================================

def train_model(dataset_dir=None):
    """Train Isolation Forest on ADFA-LD or synthetic data."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    df = load_adfa_ld(dataset_dir)
    if df is None or len(df) < 10:
        print("ADFA-LD dataset not found or insufficient; using synthetic data.")
        print("To use real data, download ADFA-LD:")
        print("  git clone https://github.com/verazuo/"
              "a-labelled-version-of-the-ADFA-LD-dataset.git "
              "datasets/security/ADFA-LD")
        df = generate_synthetic_training_data()

    X = df[FEATURE_NAMES].values
    print(f"Training samples: {len(X)}")
    print(f"Features: {FEATURE_NAMES}")

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = IsolationForest(
        n_estimators=200,
        contamination=0.05,
        random_state=42,
    )
    model.fit(X_scaled)

    joblib.dump(model, MODEL_PATH)
    joblib.dump(scaler, SCALER_PATH)

    scores = model.decision_function(X_scaled)
    print(f"Score range: [{scores.min():.3f}, {scores.max():.3f}]")
    print(f"Anomalies detected in training: {(scores < 0).sum()}/{len(scores)}")
    print(f"Model saved to {MODEL_PATH}")
    print(f"Scaler saved to {SCALER_PATH}")
    return model, scaler


# =========================================================
# PART 3 — Detection Mode
# =========================================================

def detect_anomalies():
    """Real-time anomaly detection loop."""
    if not MODEL_PATH.exists() or not SCALER_PATH.exists():
        print("ERROR: Model not trained. Run: python3 anomaly_detector.py --train")
        return 1

    model = joblib.load(MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)
    EONIX_DIR.mkdir(parents=True, exist_ok=True)

    print("[Eonix Anomaly Detector] Running... (Ctrl+C to stop)")

    loop_running = True

    def stop(sig, frame):
        nonlocal loop_running
        loop_running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    while loop_running:
        df = parse_alerts_log()
        if len(df) == 0:
            time.sleep(5)
            continue

        X = df[FEATURE_NAMES].values
        X_scaled = scaler.transform(X)
        scores = model.decision_function(X_scaled)

        for i, (_, row) in enumerate(df.iterrows()):
            score = scores[i]
            pid = int(row["pid"])

            # PART 4 — Tiered Response
            if score < TIER_KILL:
                action = "KILL (block level 3)"
                level = "3"
            elif score < TIER_RESTRICT:
                action = "RESTRICT (block level 2)"
                level = "2"
            elif score < TIER_LOG:
                action = "LOG (observe)"
                level = None
            else:
                continue

            ts = datetime.now(timezone.utc).isoformat()
            msg = f"ANOMALY: PID={pid} score={score:.3f} action={action}"
            print(f"\033[1;31m{msg}\033[0m")

            with open(ANOMALY_LOG, "a") as f:
                f.write(f"{ts} | PID={pid} | score={score:.3f} | {action}\n")

            if level:
                monitor_bin = Path("eonix-core/security/syscall_monitor")
                if monitor_bin.exists():
                    subprocess.run(
                        ["sudo", str(monitor_bin), "--block", str(pid), level],
                        capture_output=True,
                    )

        time.sleep(5)

    print("[Eonix Anomaly Detector] Stopped.")
    return 0


# =========================================================
# CLI
# =========================================================

def main():
    parser = argparse.ArgumentParser(
        description="Eonix Security Anomaly Detector")
    parser.add_argument("--train", action="store_true",
                        help="Train Isolation Forest model")
    parser.add_argument("--detect", action="store_true",
                        help="Run real-time anomaly detection")
    parser.add_argument("--status", action="store_true",
                        help="Show model info")
    args = parser.parse_args()

    if args.train:
        train_model()
    elif args.detect:
        return detect_anomalies()
    elif args.status:
        if MODEL_PATH.exists():
            model = joblib.load(MODEL_PATH)
            print(f"Model: {MODEL_PATH} ({MODEL_PATH.stat().st_size} bytes)")
            print(f"Estimators: {model.n_estimators}")
            print(f"Contamination: {model.contamination}")
        else:
            print("No model trained yet. Run: python3 anomaly_detector.py --train")
    else:
        parser.print_help()
    return 0


# =========================================================
# PART 6 — Pytest Tests
# =========================================================

def test_feature_extraction_correct_shape():
    """Feature extraction produces correct number of columns."""
    import tempfile
    with tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False) as f:
        f.write("2026-03-10T00:00:00Z | PID=100 | bash | exec_storm | LOG\n")
        f.write("2026-03-10T00:00:01Z | PID=100 | bash | fork_bomb | LOG\n")
        f.write("2026-03-10T00:00:02Z | PID=200 | curl | port_scan | LOG\n")
        tmp = f.name

    try:
        df = parse_alerts_log(tmp)
        assert len(df) == 2, f"Expected 2 rows, got {len(df)}"
        for feat in FEATURE_NAMES:
            assert feat in df.columns, f"Missing feature: {feat}"
    finally:
        os.unlink(tmp)


def test_isolation_forest_trains_without_error():
    """Model trains successfully on synthetic data."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model, scaler = train_model(dataset_dir="/nonexistent")
    assert model is not None
    assert scaler is not None
    assert MODEL_PATH.exists()
    assert SCALER_PATH.exists()


def test_anomaly_score_range():
    """Anomaly scores fall within expected range."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model, scaler = train_model(dataset_dir="/nonexistent")
    df = generate_synthetic_training_data(50)
    X = scaler.transform(df[FEATURE_NAMES].values)
    scores = model.decision_function(X)
    assert np.all(np.isfinite(scores)), "Non-finite scores detected"
    assert scores.min() > -1.5, f"Score too low: {scores.min()}"
    assert scores.max() < 1.5, f"Score too high: {scores.max()}"


def test_normal_process_not_flagged():
    """Normal process behavior scores above threshold."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model, scaler = train_model(dataset_dir="/nonexistent")
    normal = pd.DataFrame([{
        "execve_rate": 0.5, "openat_rate": 2.0, "connect_rate": 1.0,
        "mmap_rate": 1.5, "fork_rate": 0.3, "ptrace_ever": 0.0,
        "setuid_ever": 0.0, "unique_files": 5.0, "unique_hosts": 2.0,
        "session_duration": 30.0,
    }])
    X = scaler.transform(normal[FEATURE_NAMES].values)
    score = model.decision_function(X)[0]
    assert score > TIER_LOG, f"Normal process flagged with score {score}"


def test_suspicious_process_flagged():
    """Suspicious process with extreme values is scored as anomalous."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model, scaler = train_model(dataset_dir="/nonexistent")
    suspicious = pd.DataFrame([{
        "execve_rate": 200.0, "openat_rate": 500.0, "connect_rate": 800.0,
        "mmap_rate": 200.0, "fork_rate": 500.0, "ptrace_ever": 1.0,
        "setuid_ever": 1.0, "unique_files": 500.0, "unique_hosts": 300.0,
        "session_duration": 0.5,
    }])
    X = scaler.transform(suspicious[FEATURE_NAMES].values)
    score = model.decision_function(X)[0]
    assert score < TIER_LOG, f"Suspicious process NOT flagged, score={score}"


if __name__ == "__main__":
    sys.exit(main())
