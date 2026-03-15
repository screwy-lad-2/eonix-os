"""Month 6 integration checks for shell, branding, installer, and live pipeline."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

BASE = {
    "context": "http://127.0.0.1:7736",
    "hub": "http://127.0.0.1:7750",
}

ROOT = Path(__file__).resolve().parents[1]


def _python() -> str:
    return sys.executable


def _run(cmd: list[str], env: dict | None = None, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=timeout,
    )


def _require_live_stack() -> None:
    try:
        r = httpx.get(f"{BASE['hub']}/hub/status", timeout=3.0)
        if r.status_code == 200:
            return
    except Exception:
        pass
    pytest.skip("Month 6 integration requires live stack: run `bash start_eonix.sh` first")


def _stack_ready() -> bool:
    try:
        r = httpx.get(f"{BASE['hub']}/hub/status", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


def _start_stack_for_test() -> list[subprocess.Popen]:
    services = [
        ("eonix-cortex/goal-engine/engine.py", ["--start"]),
        ("eonix-cortex/context-agent/agent.py", ["--start"]),
        ("eonix-cortex/resource-agent/agent.py", ["--start"]),
        ("eonix-sync/sync_daemon.py", ["--start", "--port", "7740"]),
        ("eonix-hub/hub_server.py", []),
    ]
    procs: list[subprocess.Popen] = []
    for rel, args in services:
        procs.append(
            subprocess.Popen(
                [_python(), str(ROOT / rel), *args],
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        )
    time.sleep(10)
    return procs


def _wait_for_pipeline(timeout_s: float = 25.0) -> bool:
    deadline = time.time() + float(timeout_s)
    while time.time() < deadline:
        try:
            c = httpx.get(f"{BASE['context']}/context/status", timeout=2.0)
            h = httpx.get(f"{BASE['hub']}/hub/status", timeout=2.0)
            if c.status_code == 200 and h.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1.0)
    return False


def test_eonix_shell_starts_and_shows_banner():
    proc = _run([_python(), "eonix-shell/shell.py", "--banner-only"], timeout=60)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "EONIX SHELL" in out
    assert ("No active goal" in out) or ("Goal:" in out)
    assert "v" in out


def test_branding_boot_art_contains_required_elements(capsys):
    from eonix_shell.branding import print_boot_art

    print_boot_art(version="v0.6.0", device_id="test-device", tagline="Month 6")
    out = capsys.readouterr().out
    assert "EONIX" in out
    assert "v0.6.0" in out


def test_nl_interpreter_classifies_shell_intent():
    from eonix_shell.nl_interpreter import INTENT_SHELL, NLInterpreter

    nl = NLInterpreter()
    intent = nl.classify_intent("show me all python files")
    assert intent == INTENT_SHELL


def test_nl_interpreter_translates_to_safe_bash():
    from eonix_shell.nl_interpreter import NLInterpreter

    nl = NLInterpreter()
    cmd = nl.translate_to_bash("list all text files here")
    assert isinstance(cmd, str)
    assert len(cmd.strip()) > 0
    assert "rm -rf" not in cmd.lower()


def test_installer_syntax_valid():
    proc = _run(["bash", "-n", "install/eonix-install.sh"], timeout=30)
    assert proc.returncode == 0, proc.stderr


def test_installer_dev_mode_idempotent(tmp_path):
    home = Path("/tmp/eonix-month6-test")
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["CI"] = "true"

    first = _run(["bash", "install/eonix-install.sh", "--dev"], env=env, timeout=300)
    second = _run(["bash", "install/eonix-install.sh", "--dev"], env=env, timeout=300)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    second_out = second.stdout or ""
    assert "EONIX INSTALL COMPLETE" in second_out
    assert ".eonix" in second_out


def test_shell_eon_help_lists_all_commands():
    proc = _run([_python(), "eonix-shell/shell.py", "--run-command", "eon help"], timeout=90)
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout.lower()
    for cmd in [
        "status",
        "goal",
        "remember",
        "recall",
        "sync",
        "hub",
        "history",
        "help",
        "listen",
        "nl",
    ]:
        assert cmd in out


def test_full_shell_to_context_pipeline():
    started: list[subprocess.Popen] = []
    if not _stack_ready():
        started = _start_stack_for_test()

    try:
        if not _wait_for_pipeline(timeout_s=30.0):
            pytest.skip("live context/hub endpoints are unavailable in this environment")

        event = {"type": "shell", "command": "ls", "cwd": "/tmp"}
        r = httpx.post(f"{BASE['context']}/context/event", json=event, timeout=5.0)
        assert r.status_code == 200

        found = False
        for _ in range(12):
            t = httpx.get(f"{BASE['hub']}/hub/timeline", timeout=5.0)
            assert t.status_code == 200
            rows = t.json()
            assert isinstance(rows, list)
            for row in rows:
                if not isinstance(row, dict):
                    continue
                text = json.dumps(row).lower()
                if "shell" in text and "ls" in text:
                    found = True
                    break
            if found:
                break
            time.sleep(0.5)

        assert found, "shell event did not appear in hub timeline"
    finally:
        for p in started:
            try:
                p.terminate()
            except Exception:
                pass
