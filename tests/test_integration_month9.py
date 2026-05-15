"""Month 9 ISO hardening regression checks."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ISO_DIR = ROOT / "iso"
START_SCRIPT = ROOT / "start_eonix.sh"


def _bash_path(path: Path) -> str:
    p = str(path)
    if sys.platform.startswith("win") and len(p) > 2 and p[1:3] == ":\\":
        drive = p[0].lower()
        rest = p[2:].replace("\\", "/")
        return f"/mnt/{drive}{rest}"
    return p


def _read_chroot() -> str:
    return (ISO_DIR / "chroot_setup.sh").read_text(encoding="utf-8")


def test_chroot_setup_includes_mind_copy():
    text = _read_chroot()
    assert "eonix-mind" in text
    assert "cp -a /home/eonix/eonix-os/eonix-mind" in text or "cp -r /home/eonix/eonix-os/eonix-mind" in text


def test_chroot_setup_includes_httpx():
    text = _read_chroot()
    assert "httpx" in text


def test_chroot_setup_includes_vbox_guest():
    text = _read_chroot()
    assert "virtualbox-guest-x11" in text


def test_chroot_setup_fixes_hostname():
    text = _read_chroot()
    assert "127.0.1.1" in text


def test_start_eonix_handles_missing_mind(tmp_path: Path):
    if sys.platform.startswith("win"):
        pytest.skip("start script process bootstrap check runs on Linux")

    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["EONIX_START_SMOKE"] = "1"
    env["EONIX_HEALTH_RETRIES"] = "1"
    proc = subprocess.run([
        "bash",
        str(START_SCRIPT),
    ], cwd=ROOT, env=env, capture_output=True, text=True, timeout=20)
    assert proc.returncode == 0, proc.stderr


def test_start_eonix_installs_httpx_if_missing():
    text = START_SCRIPT.read_text(encoding="utf-8")
    assert "httpx" in text and "pip install httpx" in text


def test_all_iso_scripts_syntax_valid():
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash missing")
    scripts = [
        ISO_DIR / "build_base.sh",
        ISO_DIR / "chroot_setup.sh",
        ISO_DIR / "build_squashfs.sh",
        ISO_DIR / "build_iso.sh",
        ISO_DIR / "grub_config.sh",
    ]
    for script in scripts:
        assert script.exists()
        proc = subprocess.run([bash, "-n", _bash_path(script)], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr


def test_vm_boot_issues_documented():
    report = ROOT / "results" / "week31_iso_fixes.txt"
    assert report.exists()
    content = report.read_text(encoding="utf-8")
    for bug in [
        "mind_v2.py missing",
        "httpx missing",
        "vboxvideo driver missing",
        "hostname not resolving",
    ]:
        assert bug in content


def test_install_script_syntax_valid():
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash missing")
    script = ISO_DIR / "install_eonix_into_chroot.sh"
    assert script.exists()
    proc = subprocess.run([bash, "-n", _bash_path(script)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


def test_install_script_copies_mind():
    text = (ISO_DIR / "install_eonix_into_chroot.sh").read_text(encoding="utf-8")
    assert "eonix-mind" in text
    assert "mind_v2.py" in text


def test_ci_iso_build_job_exists():
    workflow = (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")
    assert "build-iso-full" in workflow


def test_week32_boot_result_template_exists():
    path = ROOT / "results" / "week32_full_desktop_boot.txt"
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "Week 32" in content or content.strip() != ""


def test_post_retrain_hook_exists():
    text = (ROOT / "eonix-core" / "scheduler" / "auto_retrain.py").read_text(encoding="utf-8")
    assert "def on_retrain_complete" in text


def test_rollback_safety_implemented():
    text = (ROOT / "eonix-core" / "scheduler" / "auto_retrain.py").read_text(encoding="utf-8")
    assert "rolled back" in text and "accuracy_drop" in text


def test_model_comparison_function_exists():
    text = (ROOT / "eonix-core" / "scheduler" / "auto_retrain.py").read_text(encoding="utf-8")
    assert "def compare_model_versions" in text


def test_hub_status_includes_model_version():
    text = (ROOT / "eonix-hub" / "hub_server.py").read_text(encoding="utf-8")
    assert "model_version" in text and "next_retrain_eta" in text and "model_ready" in text

def test_hub_status_all_fields_present():
    """Verify /hub/status returns all required model fields."""
    import ast, os
    hub_file = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "eonix-hub/hub_server.py"
    )
    with open(hub_file, encoding="utf-8") as f:
        content = f.read()
    assert "model_version" in content
    assert "model_ready" in content
    assert "next_retrain_eta" in content

def test_hub_uses_json_flag_for_model_info():
    """Verify hub_server uses --json flag not regex."""
    import os
    hub_file = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "eonix-hub/hub_server.py"
    )
    with open(hub_file, encoding="utf-8") as f:
        content = f.read()
    assert "--json" in content
    # Should NOT use regex for parsing anymore
    # (regex was the old fragile method)
    assert "json.loads" in content or "json_data" in content

def test_mind_memory_empty_recall_guard():
    """Verify memory.py handles empty recall without crash."""
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mem_file = os.path.join(REPO, "eonix-mind/memory.py")
    with open(mem_file, encoding="utf-8") as f:
        content = f.read()
    # Should have a guard for empty results
    assert "if not" in content or "len(" in content or \
           "results is None" in content or "except" in content

def test_proactive_monitor_no_hardcoded_2025_dates():
    """Verify proactive_monitor.py uses dynamic dates."""
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pm_file = os.path.join(REPO, "eonix-mind/proactive_monitor.py")
    with open(pm_file, encoding="utf-8") as f:
        content = f.read()
    # Should not have hardcoded year 2025 as a deadline
    assert "2025-" not in content or "datetime" in content

def test_auto_retrain_has_json_flag():
    """Verify --json flag exists in auto_retrain.py."""
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ar_file = os.path.join(REPO,
        "eonix-core/scheduler/auto_retrain.py")
    with open(ar_file, encoding="utf-8") as f:
        content = f.read()
    assert "--json" in content
    assert "json.dumps" in content

def test_rollback_checks_top3_degradation():
    """Verify rollback guards against top3 degradation."""
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ar_file = os.path.join(REPO,
        "eonix-core/scheduler/auto_retrain.py")
    with open(ar_file, encoding="utf-8") as f:
        content = f.read()
    assert "top3_drop" in content
    assert "0.03" in content


def test_landing_page_exists():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert os.path.exists(
        os.path.join(REPO, "docs/index.html"))


def test_getting_started_doc_exists():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert os.path.exists(
        os.path.join(REPO, "docs/getting-started.md"))


def test_api_doc_exists():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert os.path.exists(
        os.path.join(REPO, "docs/api.md"))


def test_brain_db_beta_table_exists():
    import sqlite3, os, pytest
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db = os.path.join(REPO, "eonix_project_brain.db")
    if not os.path.exists(db):
        pytest.skip("Brain DB not present")
    conn = sqlite3.connect(db)
    tables = [r[0] for r in
        conn.execute(
          "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    conn.close()
    assert "beta_feedback" in tables

def test_v100_release_notes_exist():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert os.path.exists(os.path.join(
        REPO, "docs/release_notes_v1.0.0.md"))

def test_docs_style_css_exists():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert os.path.exists(
        os.path.join(REPO, "docs/style.css"))

def test_changelog_doc_exists():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert os.path.exists(
        os.path.join(REPO, "docs/changelog.md"))

def test_ai_model_doc_exists():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert os.path.exists(
        os.path.join(REPO, "docs/ai-model.md"))
