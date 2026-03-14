#!/usr/bin/env python3
"""Eonix OS cumulative test runner with deterministic totals."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

SUITES = [
    "eonix-shell/shell.py",
    "eonix-hub/hub_server.py",
    "tests/test_integration_month5.py",
    "eonix-core/scheduler/train_scheduler.py",
    "eonix-core/scheduler/auto_retrain.py",
    "eonix-core/scheduler/build_features.py",
    "eonix-core/security/anomaly_detector.py",
    "eonix-core/security/behavioral_fingerprint.py",
    "eonix-core/security/security_pipeline.py",
    "eonix-cortex/context-agent/agent.py",
    "eonix-cortex/goal-engine/engine.py",
    "eonix-cortex/resource-agent/agent.py",
    "eonix-sync/sync_daemon.py",
    "eonix-sync/state_store.py",
    "eonix-mind/memory.py",
    "eonix-mind/proactive_monitor.py",
    "eonix-mind/system_reader.py",
    "eonix-mind/mind_v1.py",
    "eonix-mind/mind_v2.py",
]

WEEK16_MIN_EXPECTED_PASS = 68
WEEK17_MIN_EXPECTED_PASS = 74
MONTH5_MIN_EXPECTED_PASS = 82
WEEK19_MIN_EXPECTED_PASS = 88

INTEGRATION_SUITE = "tests/test_integration_month5.py"
SERVICE_SCRIPTS = [
    ("eonix-cortex/goal-engine/engine.py", ["--start"]),
    ("eonix-cortex/context-agent/agent.py", ["--start"]),
    ("eonix-cortex/resource-agent/agent.py", ["--start"]),
    ("eonix-sync/sync_daemon.py", ["--start", "--port", "7740"]),
    ("eonix-hub/hub_server.py", []),
]


def parse_counts(output: str) -> tuple[int, int]:
    passed = 0
    failed = 0
    m_pass = re.search(r"(\d+)\s+passed", output)
    if m_pass:
        passed = int(m_pass.group(1))
    m_fail = re.search(r"(\d+)\s+failed", output)
    if m_fail:
        failed = int(m_fail.group(1))
    return passed, failed


def _run_integration_with_stack(root: Path) -> subprocess.CompletedProcess:
    procs: list[subprocess.Popen] = []
    try:
        for rel, args in SERVICE_SCRIPTS:
            script = root / rel
            cmd = [sys.executable, str(script), *args]
            procs.append(
                subprocess.Popen(
                    cmd,
                    cwd=root,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            )

        time.sleep(10)
        return subprocess.run(
            [sys.executable, "-m", "pytest", INTEGRATION_SUITE, "-q"],
            cwd=root,
            capture_output=True,
            text=True,
        )
    finally:
        for p in procs:
            try:
                p.terminate()
            except Exception:
                pass
        time.sleep(1)
        for p in procs:
            try:
                if p.poll() is None:
                    p.kill()
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Run cumulative Eonix test suites")
    parser.add_argument("--output", default="", help="Optional file path to write the summary report")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    lines = ["=== Eonix OS - Full Test Suite ==="]

    total_pass = 0
    total_fail = 0

    for suite in SUITES:
        suite_path = root / suite
        if not suite_path.exists():
            lines.append(f"  {suite}: skipped (missing)")
            continue

        if suite == INTEGRATION_SUITE:
            proc = _run_integration_with_stack(root)
        else:
            cmd = [sys.executable, "-m", "pytest", suite, "-q"]
            proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
        combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
        passed, failed = parse_counts(combined)

        total_pass += passed
        total_fail += failed

        if failed > 0:
            lines.append(f"  {suite}: {passed} passed, {failed} failed")
        else:
            lines.append(f"  {suite}: {passed} passed")

    lines.append("")
    lines.append(f"TOTAL: {total_pass} passed | {total_fail} failed")
    lines.append(f"TARGET (Week 16): >= {WEEK16_MIN_EXPECTED_PASS} passed")
    lines.append(f"TARGET (Week 17): >= {WEEK17_MIN_EXPECTED_PASS} passed")
    lines.append(f"TARGET (Month 5 Close): >= {MONTH5_MIN_EXPECTED_PASS} passed")
    lines.append(f"TARGET (Week 19 Shell): >= {WEEK19_MIN_EXPECTED_PASS} passed")

    text = "\n".join(lines)
    print(text)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n", encoding="utf-8")

    if total_fail > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
