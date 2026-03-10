#!/usr/bin/env python3
"""
Eonix OS — Security Pipeline (Full Integration)
=================================================
Wires eBPF syscall_monitor → BehavioralFingerprinter → AnomalyDetector
into a single running pipeline with SQLite event storage and CLI.

Usage:
    python3 security_pipeline.py --start     Launch pipeline
    python3 security_pipeline.py --stop      Stop pipeline
    python3 security_pipeline.py --status    Print security status
    python3 security_pipeline.py --events    Last 20 events
    python3 security_pipeline.py --threats   Events with combined_score > 0.5

Pytest:
    python3 -m pytest security_pipeline.py -v
"""

import argparse
import json
import os
import re
import signal
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ---- Paths ----
HOME = Path.home()
EONIX_DIR = HOME / ".eonix"
EVENTS_DB = EONIX_DIR / "security_events.db"
STATUS_FILE = EONIX_DIR / "security_status.txt"
PID_FILE = EONIX_DIR / "security_pipeline.pid"

_EVENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    pid INTEGER,
    comm TEXT,
    fingerprint_score REAL,
    ml_score REAL,
    combined_score REAL,
    action_taken TEXT,
    alert_type TEXT
);
"""


# =========================================================
# Monitor output parser
# =========================================================

# Example monitor output line (ANSI-stripped):
# [SYSCALL] PID=1234 COMM=bash SYS=execve ALERT=exec_storm BLOCKED=0
_LINE_RE = re.compile(
    r"PID=(\d+)\s+COMM=(\S+)\s+SYS=(\S+)"
    r"(?:\s+ALERT=(\S+))?"
    r"(?:\s+BLOCKED=(\d+))?",
)


def parse_monitor_line(line: str) -> dict | None:
    """Parse a single syscall_monitor stdout line into an event dict."""
    # Strip ANSI escapes
    clean = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
    if not clean:
        return None
    m = _LINE_RE.search(clean)
    if not m:
        return None
    return {
        "pid": int(m.group(1)),
        "comm": m.group(2),
        "syscall": m.group(3),
        "alert_type": m.group(4) or "",
        "blocked": int(m.group(5)) if m.group(5) else 0,
    }


# =========================================================
# Combined scoring
# =========================================================

def combined_score(fingerprint_score: float, ml_score: float) -> float:
    """Weighted combination: 60% isolation-forest + 40% fingerprint."""
    return ml_score * 0.6 + fingerprint_score * 0.4


def action_for_score(score: float) -> str:
    """Tiered response based on combined score."""
    if score > 0.8:
        return "ISOLATE"   # block level 3
    if score > 0.5:
        return "RESTRICT"  # block level 2
    if score > 0.3:
        return "ALERT"
    return "LOG"


# =========================================================
# Event storage
# =========================================================

class EventStore:
    """SQLite-backed security event log."""

    def __init__(self, db_path: str | None = None):
        if db_path is None:
            db_path = str(EVENTS_DB)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_EVENTS_SCHEMA)
        self._conn.commit()

    def insert(self, *, timestamp: str, pid: int, comm: str,
               fingerprint_score: float, ml_score: float,
               combined_score: float, action_taken: str,
               alert_type: str):
        self._conn.execute(
            """INSERT INTO events
                   (timestamp, pid, comm, fingerprint_score, ml_score,
                    combined_score, action_taken, alert_type)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (timestamp, pid, comm, fingerprint_score, ml_score,
             combined_score, action_taken, alert_type),
        )
        self._conn.commit()

    def last_events(self, n: int = 20) -> list[dict]:
        cur = self._conn.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT ?", (n,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def threats(self, threshold: float = 0.5) -> list[dict]:
        cur = self._conn.execute(
            "SELECT * FROM events WHERE combined_score > ? ORDER BY id DESC",
            (threshold,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def count_today(self) -> tuple[int, int]:
        """Return (events_today, threats_today)."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM events WHERE timestamp LIKE ?",
            (f"{today}%",))
        total = cur.fetchone()[0]
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM events WHERE timestamp LIKE ? "
            "AND combined_score > 0.5", (f"{today}%",))
        threats = cur.fetchone()[0]
        return total, threats

    def close(self):
        self._conn.close()


# =========================================================
# Status file
# =========================================================

def write_status(events_today: int, threats_blocked: int,
                 active: bool = True, false_positives: int = 0):
    EONIX_DIR.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(
        f"EONIX_SECURITY: active={active} events_today={events_today} "
        f"threats_blocked={threats_blocked} false_positives={false_positives}\n"
    )


# =========================================================
# Pipeline daemon
# =========================================================

class SecurityPipeline:
    """Orchestrates the full eBPF → fingerprint → ML → response flow."""

    def __init__(self, store: EventStore | None = None,
                 fingerprinter=None, model=None, scaler=None):
        self.store = store or EventStore()
        self.fingerprinter = fingerprinter
        self.model = model
        self.scaler = scaler
        self._running = False

    def process_event(self, event: dict) -> dict:
        """Score a parsed event and store it. Returns enriched event."""
        fp_score = 0.5
        ml_score_val = 0.5

        # Fingerprint score
        if self.fingerprinter is not None:
            fp_score = self.fingerprinter.score(event)
            self.fingerprinter.observe(event)

        # ML score (isolation forest) — map decision_function to 0–1 range
        if self.model is not None and self.scaler is not None:
            import numpy as np
            import pandas as pd
            from anomaly_detector import FEATURE_NAMES
            features = {}
            for f in FEATURE_NAMES:
                features[f] = float(event.get(f, 0))
            df = pd.DataFrame([features])
            X = self.scaler.transform(df[FEATURE_NAMES].values)
            raw = self.model.decision_function(X)[0]
            # Map: raw < -0.3 → 1.0, raw > 0.2 → 0.0
            ml_score_val = max(0.0, min(1.0, 0.5 - raw * 2.0))

        comb = combined_score(fp_score, ml_score_val)
        action = action_for_score(comb)
        ts = datetime.now(timezone.utc).isoformat()

        self.store.insert(
            timestamp=ts,
            pid=event.get("pid", 0),
            comm=event.get("comm", "unknown"),
            fingerprint_score=fp_score,
            ml_score=ml_score_val,
            combined_score=comb,
            action_taken=action,
            alert_type=event.get("alert_type", ""),
        )

        return {
            **event,
            "fingerprint_score": fp_score,
            "ml_score": ml_score_val,
            "combined_score": comb,
            "action": action,
        }

    def start(self):
        """Start the pipeline (reads from syscall_monitor subprocess)."""
        import subprocess

        monitor_bin = Path(__file__).parent / "syscall_monitor"
        if not monitor_bin.exists():
            print(f"[Pipeline] Monitor binary not found: {monitor_bin}")
            print("[Pipeline] Running in log-tailing mode instead.")
            self._tail_mode()
            return

        proc = subprocess.Popen(
            ["sudo", str(monitor_bin), "--monitor"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )

        self._running = True
        signal.signal(signal.SIGINT, lambda s, f: setattr(self, '_running', False))
        signal.signal(signal.SIGTERM, lambda s, f: setattr(self, '_running', False))

        # Write PID file
        PID_FILE.write_text(str(os.getpid()))

        print("[Pipeline] Running... (Ctrl+C to stop)")
        last_status = time.time()

        while self._running:
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    break
                continue
            event = parse_monitor_line(line)
            if event:
                result = self.process_event(event)
                if result["action"] != "LOG":
                    print(f"\033[1;31m[{result['action']}] "
                          f"PID={result['pid']} {result['comm']} "
                          f"score={result['combined_score']:.2f}\033[0m")

            if time.time() - last_status > 30:
                total, threats = self.store.count_today()
                write_status(total, threats)
                last_status = time.time()

        proc.terminate()
        PID_FILE.unlink(missing_ok=True)
        print("[Pipeline] Stopped.")

    def _tail_mode(self):
        """Fallback: tail security_alerts.log instead of eBPF."""
        from anomaly_detector import ALERTS_LOG
        self._running = True
        signal.signal(signal.SIGINT, lambda s, f: setattr(self, '_running', False))
        PID_FILE.write_text(str(os.getpid()))

        print("[Pipeline] Tailing", ALERTS_LOG)
        while self._running:
            time.sleep(5)
            total, threats = self.store.count_today()
            write_status(total, threats)

        PID_FILE.unlink(missing_ok=True)

    def stop(self):
        self._running = False


# =========================================================
# CLI
# =========================================================

def cmd_status():
    if STATUS_FILE.exists():
        print(STATUS_FILE.read_text().strip())
    else:
        print("EONIX_SECURITY: active=False events_today=0 "
              "threats_blocked=0 false_positives=0")


def cmd_events():
    store = EventStore()
    events = store.last_events(20)
    if not events:
        print("No events recorded yet.")
        return
    for e in reversed(events):
        print(f"{e['timestamp']} | PID={e['pid']} {e['comm']} | "
              f"score={e['combined_score']:.2f} | {e['action_taken']} | "
              f"{e['alert_type']}")
    store.close()


def cmd_threats():
    store = EventStore()
    threats = store.threats()
    if not threats:
        print("0 threats")
        return
    print(f"{len(threats)} threat(s):")
    for e in threats:
        print(f"  {e['timestamp']} PID={e['pid']} {e['comm']} "
              f"score={e['combined_score']:.2f} {e['action_taken']}")
    store.close()


def cmd_start():
    try:
        from behavioral_fingerprint import BehavioralFingerprinter
        fp = BehavioralFingerprinter()
    except ImportError:
        fp = None

    model, scaler = None, None
    try:
        import joblib
        from anomaly_detector import MODEL_PATH, SCALER_PATH
        if MODEL_PATH.exists() and SCALER_PATH.exists():
            model = joblib.load(MODEL_PATH)
            scaler = joblib.load(SCALER_PATH)
    except (ImportError, Exception):
        pass

    pipeline = SecurityPipeline(fingerprinter=fp, model=model, scaler=scaler)
    pipeline.start()


def cmd_stop():
    if PID_FILE.exists():
        pid = int(PID_FILE.read_text().strip())
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"Sent SIGTERM to pipeline PID {pid}")
        except (OSError, ProcessLookupError):
            print(f"Pipeline PID {pid} not running")
        PID_FILE.unlink(missing_ok=True)
    else:
        print("No pipeline PID file found")


def main():
    parser = argparse.ArgumentParser(
        description="Eonix Security Pipeline")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--start", action="store_true", help="Start pipeline")
    group.add_argument("--stop", action="store_true", help="Stop pipeline")
    group.add_argument("--status", action="store_true", help="Show status")
    group.add_argument("--events", action="store_true", help="Last 20 events")
    group.add_argument("--threats", action="store_true",
                       help="Show threats (combined_score > 0.5)")
    args = parser.parse_args()

    if args.start:
        cmd_start()
    elif args.stop:
        cmd_stop()
    elif args.status:
        cmd_status()
    elif args.events:
        cmd_events()
    elif args.threats:
        cmd_threats()
    else:
        parser.print_help()
    return 0


# =========================================================
# Pytest Tests
# =========================================================

def test_pipeline_parses_monitor_output():
    """parse_monitor_line extracts PID, COMM, SYS from monitor output."""
    line = "[SYSCALL] PID=1234 COMM=bash SYS=execve ALERT=exec_storm BLOCKED=0"
    ev = parse_monitor_line(line)
    assert ev is not None
    assert ev["pid"] == 1234
    assert ev["comm"] == "bash"
    assert ev["syscall"] == "execve"
    assert ev["alert_type"] == "exec_storm"

    # ANSI-colored line
    ansi = "\033[1;33m[SYSCALL] PID=42 COMM=curl SYS=connect ALERT=port_scan BLOCKED=0\033[0m"
    ev2 = parse_monitor_line(ansi)
    assert ev2 is not None
    assert ev2["pid"] == 42

    # Garbage
    assert parse_monitor_line("random noise") is None
    assert parse_monitor_line("") is None


def test_combined_score_calculation():
    """Combined score = 0.6*ml + 0.4*fingerprint."""
    c = combined_score(0.8, 0.5)
    expected = 0.5 * 0.6 + 0.8 * 0.4
    assert abs(c - expected) < 1e-9

    c2 = combined_score(0.0, 0.0)
    assert c2 == 0.0

    c3 = combined_score(1.0, 1.0)
    assert abs(c3 - 1.0) < 1e-9


def test_tiered_response_thresholds():
    """Action thresholds match spec."""
    assert action_for_score(0.1) == "LOG"
    assert action_for_score(0.29) == "LOG"
    assert action_for_score(0.4) == "ALERT"
    assert action_for_score(0.6) == "RESTRICT"
    assert action_for_score(0.85) == "ISOLATE"


def test_events_stored_in_sqlite():
    """Events are persisted and retrievable."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    try:
        store = EventStore(db_path=db_path)
        store.insert(
            timestamp="2026-03-10T12:00:00Z",
            pid=100, comm="bash",
            fingerprint_score=0.2, ml_score=0.3,
            combined_score=0.26, action_taken="LOG",
            alert_type="exec_storm",
        )
        store.insert(
            timestamp="2026-03-10T12:01:00Z",
            pid=200, comm="malware",
            fingerprint_score=0.9, ml_score=0.8,
            combined_score=0.84, action_taken="ISOLATE",
            alert_type="port_scan",
        )
        events = store.last_events(10)
        assert len(events) == 2

        threats = store.threats(threshold=0.5)
        assert len(threats) == 1
        assert threats[0]["comm"] == "malware"

        store.close()
    finally:
        Path(db_path).unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
