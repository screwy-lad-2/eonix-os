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

pytestmark = pytest.mark.skipif(sys.platform.startswith("win"), reason="Month 9 integration skips on Windows")


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
        proc = subprocess.run([bash, "-n", str(script)], capture_output=True, text=True)
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
    assert bash
    script = ISO_DIR / "install_eonix_into_chroot.sh"
    assert script.exists()
    proc = subprocess.run([bash, "-n", str(script)], capture_output=True, text=True)
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
