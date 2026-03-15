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
    "eonix-shell/nl_interpreter.py",
    "eonix-shell/shell.py",
    "eonix-shell/branding.py",
    "eonix-hub/hub_server.py",
    "tests/test_integration_month5.py",
    "tests/test_integration_month6.py",
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
    "eonix-desktop/desktop.py",
    "eonix-desktop/settings.py",
    "eonix-desktop/memory_widget.py",
    "eonix-desktop/window_manager.py",
    "eonix-desktop/session_manager.py",
    "tests/test_integration_month7.py",
    "iso/test_iso_build.py",
]

WEEK16_MIN_EXPECTED_PASS = 68
WEEK17_MIN_EXPECTED_PASS = 74
MONTH5_MIN_EXPECTED_PASS = 82
WEEK19_MIN_EXPECTED_PASS = 88
WEEK20_MIN_EXPECTED_PASS = 96
WEEK21_MIN_EXPECTED_PASS = 100
WEEK22_MIN_EXPECTED_PASS = 108
WEEK23_MIN_EXPECTED_PASS = 116
WEEK24_MIN_EXPECTED_PASS = 124
WEEK25_MIN_EXPECTED_PASS = 138
MONTH7_MIN_EXPECTED_PASS = 146
WEEK27_MIN_EXPECTED_PASS = 154

INTEGRATION_SUITES = {"tests/test_integration_month5.py", "tests/test_integration_month6.py", "tests/test_integration_month7.py"}
SERVICE_SCRIPTS = [
    ("eonix-cortex/goal-engine/engine.py", ["--start"]),
    ("eonix-cortex/context-agent/agent.py", ["--start"]),
    ("eonix-cortex/resource-agent/agent.py", ["--start"]),
    ("eonix-sync/sync_daemon.py", ["--start", "--port", "7740"]),
    ("eonix-hub/hub_server.py", []),
]

PER_SUITE_TIMEOUT_SECONDS = 600


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("EONIX_HEADLESS", "1")
    return env


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


def _run_integration_with_stack(root: Path, suite: str) -> subprocess.CompletedProcess:
    procs: list[subprocess.Popen] = []
    env = _subprocess_env()
    try:
        for rel, args in SERVICE_SCRIPTS:
            script = root / rel
            cmd = [sys.executable, str(script), *args]
            procs.append(
                subprocess.Popen(
                    cmd,
                    cwd=root,
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            )

        time.sleep(10)
        first = subprocess.run(
            [sys.executable, "-m", "pytest", suite, "-q"],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=PER_SUITE_TIMEOUT_SECONDS,
        )
        if first.returncode == 0:
            return first

        # Retry once after warm-up for occasional startup race conditions.
        time.sleep(3)
        second = subprocess.run(
            [sys.executable, "-m", "pytest", suite, "-q"],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=PER_SUITE_TIMEOUT_SECONDS,
        )
        if second.returncode == 0:
            return second

        second.stdout = (first.stdout or "") + "\n--- retry ---\n" + (second.stdout or "")
        second.stderr = (first.stderr or "") + "\n--- retry ---\n" + (second.stderr or "")
        return second
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
    env = _subprocess_env()

    for suite in SUITES:
        suite_path = root / suite
        if not suite_path.exists():
            lines.append(f"  {suite}: skipped (missing)")
            continue

        if suite in INTEGRATION_SUITES:
            proc = _run_integration_with_stack(root, suite)
        else:
            cmd = [sys.executable, "-m", "pytest", suite, "-q"]
            proc = subprocess.run(
                cmd,
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                timeout=PER_SUITE_TIMEOUT_SECONDS,
            )
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
    lines.append(f"TARGET (Week 20 NL+Voice): >= {WEEK20_MIN_EXPECTED_PASS} passed")
    lines.append(f"TARGET (Week 21 Install+Brand): >= {WEEK21_MIN_EXPECTED_PASS} passed")
    lines.append(f"TARGET (Week 22 Month6): >= {WEEK22_MIN_EXPECTED_PASS} passed")
    lines.append(f"TARGET (Week 23 Desktop): >= {WEEK23_MIN_EXPECTED_PASS} passed")
    lines.append(f"TARGET (Week 24 Memory+Launcher): >= {WEEK24_MIN_EXPECTED_PASS} passed")
    lines.append(f"TARGET (Week 25 WM+Sessions): >= {WEEK25_MIN_EXPECTED_PASS} passed")
    lines.append(f"TARGET (Month 7 Desktop GUI): >= {MONTH7_MIN_EXPECTED_PASS} passed")
    lines.append(f"TARGET (Week 27 ISO Bootstrap): >= {WEEK27_MIN_EXPECTED_PASS} passed")

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
