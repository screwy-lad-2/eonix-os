#!/usr/bin/env python3
"""
Eonix OS — Behavioral Fingerprinter
====================================
Builds per-process behavioral profiles using Welford's online
algorithm for incremental mean/variance — no history storage needed.

Usage:
    Imported by security_pipeline.py and anomaly_detector.py
    python3 -m pytest behavioral_fingerprint.py -v

Pytest:
    5 tests
"""

import json
import math
import sqlite3
import tempfile
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---- Paths ----
HOME = Path.home()
EONIX_DIR = HOME / ".eonix"
DEFAULT_DB = EONIX_DIR / "security_profiles.db"

# Syscall feature keys tracked per profile
TRACKED_SYSCALLS = [
    "execve", "openat", "connect", "mmap", "clone", "ptrace", "setuid",
]


# =========================================================
# PART 1 — Profile Data Structure
# =========================================================

@dataclass
class ProcessProfile:
    name: str
    observed_sessions: int = 0
    # Welford state: mean, M2 (sum of squared deviations), count
    _mean: dict = field(default_factory=dict)
    _m2: dict = field(default_factory=dict)
    typical_files: set = field(default_factory=set)
    typical_connections: set = field(default_factory=set)
    typical_runtime_sec: float = 0.0
    first_seen: str = ""
    last_seen: str = ""
    trust_level: float = 0.0

    @property
    def avg_syscall_rates(self) -> dict:
        return dict(self._mean)

    @property
    def stddev_syscall_rates(self) -> dict:
        out = {}
        for k, m2 in self._m2.items():
            n = self.observed_sessions
            out[k] = math.sqrt(m2 / n) if n > 1 else 0.0
        return out


# =========================================================
# PART 2 — Profile Builder
# =========================================================

_SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    name TEXT PRIMARY KEY,
    observed_sessions INTEGER DEFAULT 0,
    mean_json TEXT DEFAULT '{}',
    m2_json TEXT DEFAULT '{}',
    typical_files TEXT DEFAULT '[]',
    typical_connections TEXT DEFAULT '[]',
    typical_runtime_sec REAL DEFAULT 0.0,
    first_seen TEXT DEFAULT '',
    last_seen TEXT DEFAULT '',
    trust_level REAL DEFAULT 0.0
);
"""


class BehavioralFingerprinter:
    """Incremental per-process behavioral profiler using Welford's algorithm."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = str(DEFAULT_DB)
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(_SCHEMA)
        self._conn.commit()
        self._cache: dict[str, ProcessProfile] = {}
        self._load_all()

    # ---- persistence ----

    def _load_all(self):
        cur = self._conn.execute("SELECT * FROM profiles")
        for row in cur.fetchall():
            p = ProcessProfile(name=row[0])
            p.observed_sessions = row[1]
            p._mean = json.loads(row[2])
            p._m2 = json.loads(row[3])
            p.typical_files = set(json.loads(row[4]))
            p.typical_connections = set(json.loads(row[5]))
            p.typical_runtime_sec = row[6]
            p.first_seen = row[7]
            p.last_seen = row[8]
            p.trust_level = row[9]
            self._cache[p.name] = p

    def _save(self, p: ProcessProfile):
        self._conn.execute(
            """INSERT INTO profiles
                   (name, observed_sessions, mean_json, m2_json,
                    typical_files, typical_connections,
                    typical_runtime_sec, first_seen, last_seen, trust_level)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                   observed_sessions=excluded.observed_sessions,
                   mean_json=excluded.mean_json,
                   m2_json=excluded.m2_json,
                   typical_files=excluded.typical_files,
                   typical_connections=excluded.typical_connections,
                   typical_runtime_sec=excluded.typical_runtime_sec,
                   first_seen=excluded.first_seen,
                   last_seen=excluded.last_seen,
                   trust_level=excluded.trust_level
            """,
            (
                p.name,
                p.observed_sessions,
                json.dumps(p._mean),
                json.dumps(p._m2),
                json.dumps(sorted(p.typical_files)),
                json.dumps(sorted(p.typical_connections)),
                p.typical_runtime_sec,
                p.first_seen,
                p.last_seen,
                p.trust_level,
            ),
        )
        self._conn.commit()

    def close(self):
        self._conn.close()

    # ---- Welford update ----

    @staticmethod
    def _welford_update(old_mean: float, old_m2: float, n: int, x: float):
        """Return (new_mean, new_m2) after incorporating sample x (n is count AFTER update)."""
        delta = x - old_mean
        new_mean = old_mean + delta / n
        delta2 = x - new_mean
        new_m2 = old_m2 + delta * delta2
        return new_mean, new_m2

    # ---- public API ----

    def observe(self, event: dict) -> None:
        """Update running stats for process identified by event['comm']."""
        comm = event.get("comm", "unknown")
        now = datetime.now(timezone.utc).isoformat()

        if comm not in self._cache:
            self._cache[comm] = ProcessProfile(name=comm, first_seen=now)

        p = self._cache[comm]
        p.observed_sessions += 1
        p.last_seen = now
        n = p.observed_sessions

        # Update syscall rates via Welford
        for key in TRACKED_SYSCALLS:
            rate = float(event.get(f"{key}_rate", event.get(key, 0)))
            old_mean = p._mean.get(key, 0.0)
            old_m2 = p._m2.get(key, 0.0)
            new_mean, new_m2 = self._welford_update(old_mean, old_m2, n, rate)
            p._mean[key] = new_mean
            p._m2[key] = new_m2

        # Track typical files / connections
        if "file" in event:
            p.typical_files.add(str(event["file"]))
        if "connection" in event:
            p.typical_connections.add(str(event["connection"]))

        # Incremental runtime average
        rt = float(event.get("session_duration", event.get("runtime", 0)))
        if rt > 0:
            p.typical_runtime_sec += (rt - p.typical_runtime_sec) / n

        # Trust level: after 10+ observations, low variance → high trust
        if n >= 10:
            stds = p.stddev_syscall_rates
            active = [v for v in stds.values() if v > 0]
            if active:
                avg_std = sum(active) / len(active)
                p.trust_level = max(0.0, min(1.0, 1.0 - avg_std / 10.0))
            else:
                p.trust_level = 0.9
        elif n >= 5:
            p.trust_level = 0.3
        else:
            p.trust_level = 0.1

        self._save(p)

    def score(self, event: dict) -> float:
        """Return anomaly score 0.0 (normal) – 1.0 (unknown/suspicious)."""
        comm = event.get("comm", "unknown")
        p = self._cache.get(comm)

        if p is None:
            return 0.8  # never seen
        if p.observed_sessions < 5:
            return 0.5  # uncertain

        # Z-score each feature vs stored mean/stddev
        stds = p.stddev_syscall_rates
        z_scores = []
        for key in TRACKED_SYSCALLS:
            rate = float(event.get(f"{key}_rate", event.get(key, 0)))
            mean = p._mean.get(key, 0.0)
            std = stds.get(key, 0.0)
            if std > 1e-9:
                z_scores.append(abs(rate - mean) / std)
            else:
                z_scores.append(0.0)

        if not z_scores:
            return 0.0
        combined = sum(z_scores) / len(z_scores) / 10.0
        return max(0.0, min(1.0, combined))

    def get_profile(self, name: str) -> Optional[ProcessProfile]:
        return self._cache.get(name)

    def list_profiles(self) -> list[ProcessProfile]:
        return sorted(self._cache.values(), key=lambda p: p.trust_level, reverse=True)

    def export_profiles_json(self, path: str):
        out = []
        for p in self._cache.values():
            d = {
                "name": p.name,
                "observed_sessions": p.observed_sessions,
                "avg_syscall_rates": p.avg_syscall_rates,
                "stddev_syscall_rates": p.stddev_syscall_rates,
                "typical_files": sorted(p.typical_files),
                "typical_connections": sorted(p.typical_connections),
                "typical_runtime_sec": p.typical_runtime_sec,
                "first_seen": p.first_seen,
                "last_seen": p.last_seen,
                "trust_level": p.trust_level,
            }
            out.append(d)
        with open(path, "w") as f:
            json.dump(out, f, indent=2)


# =========================================================
# Pytest Tests
# =========================================================

def test_new_process_gets_suspicious_score():
    """A never-seen process should get score ~0.8."""
    fp = BehavioralFingerprinter(db_path=":memory:")
    score = fp.score({"comm": "never_seen", "execve_rate": 1.0})
    assert score == 0.8, f"Expected 0.8 for unknown, got {score}"
    fp.close()


def test_repeated_normal_process_gets_low_score():
    """After 10+ consistent observations, score should be low."""
    fp = BehavioralFingerprinter(db_path=":memory:")
    for _ in range(15):
        fp.observe({
            "comm": "bash",
            "execve_rate": 1.0, "openat_rate": 5.0, "connect_rate": 0.5,
            "mmap_rate": 2.0, "clone_rate": 0.1, "ptrace_rate": 0.0,
            "setuid_rate": 0.0, "session_duration": 30.0,
        })
    score = fp.score({
        "comm": "bash",
        "execve_rate": 1.0, "openat_rate": 5.0, "connect_rate": 0.5,
        "mmap_rate": 2.0, "clone_rate": 0.1, "ptrace_rate": 0.0,
        "setuid_rate": 0.0,
    })
    assert score < 0.3, f"Expected low score for normal process, got {score}"
    fp.close()


def test_profile_persists_across_restarts():
    """Profile saved to DB survives fingerprinter re-creation."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        fp1 = BehavioralFingerprinter(db_path=db_path)
        fp1.observe({"comm": "nginx", "execve_rate": 0.1, "session_duration": 60.0})
        fp1.close()

        fp2 = BehavioralFingerprinter(db_path=db_path)
        p = fp2.get_profile("nginx")
        assert p is not None, "Profile should persist"
        assert p.observed_sessions == 1
        fp2.close()
    finally:
        Path(db_path).unlink(missing_ok=True)


def test_welford_mean_correct():
    """Welford incremental mean matches numpy."""
    import numpy as np
    values = [3.0, 7.0, 1.0, 9.0, 5.0, 2.0, 8.0, 4.0, 6.0, 10.0]
    mean, m2 = 0.0, 0.0
    for i, v in enumerate(values, 1):
        mean, m2 = BehavioralFingerprinter._welford_update(mean, m2, i, v)
    assert abs(mean - np.mean(values)) < 1e-10, f"Mean mismatch: {mean}"
    variance = m2 / len(values)
    assert abs(variance - np.var(values)) < 1e-10, f"Var mismatch: {variance}"


def test_export_profiles_json_valid():
    """Exported JSON is valid and contains expected fields."""
    fp = BehavioralFingerprinter(db_path=":memory:")
    for _ in range(3):
        fp.observe({"comm": "sshd", "execve_rate": 0.5, "connect_rate": 2.0})
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        path = f.name
    try:
        fp.export_profiles_json(path)
        with open(path) as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["name"] == "sshd"
        assert data[0]["observed_sessions"] == 3
        assert "avg_syscall_rates" in data[0]
    finally:
        Path(path).unlink(missing_ok=True)
    fp.close()
