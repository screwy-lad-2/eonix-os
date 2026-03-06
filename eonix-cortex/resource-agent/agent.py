"""
Eonix OS — ResourceAgent
==========================
Dynamically negotiates CPU/RAM/GPU between competing processes
based on the active goal and user-set priorities.

Usage: python3 agent.py
"""

import os
import time
import json
import signal
from datetime import datetime, timezone

try:
    import psutil
except ImportError:
    print("ERROR: psutil not installed. Run: pip install psutil")
    raise SystemExit(1)


ACTIVE_GOAL_FILE = os.path.expanduser("~/.eonix/active_goal.json")
CHECK_INTERVAL_SEC = 5


def get_active_goal() -> dict:
    """Load the current active goal."""
    if os.path.exists(ACTIVE_GOAL_FILE):
        with open(ACTIVE_GOAL_FILE) as f:
            return json.load(f)
    return {"title": "none", "related_apps": []}


def score_process(proc_info: dict, goal: dict) -> float:
    """
    Score a process based on:
    - goal_relevance (0.5): is the process related to the active goal?
    - cpu_usage (0.3): higher CPU = higher priority to manage
    - memory_usage (0.2): higher memory = higher priority to manage
    """
    goal_relevance = 0.0
    proc_name = (proc_info.get("name") or "").lower()
    related_apps = [a.lower() for a in goal.get("related_apps", [])]

    if proc_name in related_apps:
        goal_relevance = 1.0
    elif any(app in proc_name for app in related_apps):
        goal_relevance = 0.5

    cpu = min(1.0, (proc_info.get("cpu_percent") or 0) / 100.0)
    mem = min(1.0, (proc_info.get("memory_percent") or 0) / 100.0)

    return (goal_relevance * 0.5) + (cpu * 0.3) + (mem * 0.2)


def audit_resources():
    """Run one resource audit cycle."""
    goal = get_active_goal()

    processes = []
    for proc in psutil.process_iter(
        ["pid", "name", "cpu_percent", "memory_percent", "status"]
    ):
        try:
            info = proc.info
            if info["status"] != "zombie":
                info["score"] = score_process(info, goal)
                processes.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    # Sort by score (highest first)
    processes.sort(key=lambda p: p["score"], reverse=True)

    # Log top resource consumers
    top_5 = processes[:5]
    print(f"[ResourceAgent] {datetime.now(timezone.utc).strftime('%H:%M:%S')} "
          f"— Goal: {goal.get('title', 'none')}")
    for p in top_5:
        print(f"  PID {p['pid']:>6} | {p['name']:<20} | "
              f"CPU {p.get('cpu_percent', 0):5.1f}% | "
              f"MEM {p.get('memory_percent', 0):5.1f}% | "
              f"score {p['score']:.2f}")
    print()

    return processes


def main():
    print("=" * 50)
    print("  EONIX ResourceAgent")
    print("=" * 50)
    print(f"  Check interval: {CHECK_INTERVAL_SEC}s")
    print("  Press Ctrl+C to stop\n")

    running = True

    def signal_handler(sig, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Initial CPU reading
    psutil.cpu_percent(interval=None)

    while running:
        audit_resources()
        time.sleep(CHECK_INTERVAL_SEC)

    print("\n[ResourceAgent] Stopped.")


if __name__ == "__main__":
    main()
