"""
Eonix OS — Scheduler Data Collector
====================================
Background process that logs PID, process name, CPU%, RAM%, timestamp
every 100ms to SQLite. Run this for 2+ weeks to build a personal
scheduler training dataset.

Usage: python3 collect_data.py
Stop:  Ctrl+C (graceful shutdown, data is safe)
"""

import sqlite3
import time
import os
import signal
import sys
from datetime import datetime, timezone

import psutil

DB_PATH = os.path.expanduser("~/.eonix/scheduler_data.sqlite")
INTERVAL_SEC = 0.1  # 100ms


def init_db(db_path: str) -> sqlite3.Connection:
    """Initialize the SQLite database with WAL mode for performance."""
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS process_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            epoch_ms INTEGER NOT NULL,
            pid INTEGER NOT NULL,
            name TEXT,
            cpu_percent REAL,
            memory_percent REAL,
            memory_rss_mb REAL,
            status TEXT,
            parent_pid INTEGER,
            num_threads INTEGER
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_timestamp
        ON process_snapshots(epoch_ms)
    """)
    conn.commit()
    return conn


def collect_snapshot(conn: sqlite3.Connection) -> int:
    """Collect a single snapshot of all running processes."""
    now = datetime.now(timezone.utc)
    epoch_ms = int(now.timestamp() * 1000)
    timestamp = now.isoformat()

    rows = []
    for proc in psutil.process_iter(
        ["pid", "name", "cpu_percent", "memory_percent",
         "memory_info", "status", "ppid", "num_threads"]
    ):
        try:
            info = proc.info
            rss_mb = (info["memory_info"].rss / 1048576) if info.get("memory_info") else 0.0
            rows.append((
                timestamp,
                epoch_ms,
                info["pid"],
                info["name"],
                info["cpu_percent"],
                info["memory_percent"],
                rss_mb,
                info["status"],
                info["ppid"],
                info["num_threads"],
            ))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if rows:
        conn.executemany("""
            INSERT INTO process_snapshots
            (timestamp, epoch_ms, pid, name, cpu_percent, memory_percent,
             memory_rss_mb, status, parent_pid, num_threads)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)
        conn.commit()

    return len(rows)


def main():
    print(f"[Eonix Scheduler Collector] Storing data in {DB_PATH}")
    print(f"[Eonix Scheduler Collector] Interval: {INTERVAL_SEC}s")
    print("[Eonix Scheduler Collector] Press Ctrl+C to stop\n")

    conn = init_db(DB_PATH)
    total_snapshots = 0

    # Graceful shutdown
    running = True

    def signal_handler(sig, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Initial CPU percent call (returns 0 on first call)
    psutil.cpu_percent(interval=None)

    while running:
        count = collect_snapshot(conn)
        total_snapshots += 1

        if total_snapshots % 100 == 0:
            print(f"  Snapshot #{total_snapshots}: {count} processes logged")

        time.sleep(INTERVAL_SEC)

    conn.close()
    print(f"\n[Eonix Scheduler Collector] Stopped. Total snapshots: {total_snapshots}")
    print(f"[Eonix Scheduler Collector] Data saved to {DB_PATH}")


if __name__ == "__main__":
    main()
