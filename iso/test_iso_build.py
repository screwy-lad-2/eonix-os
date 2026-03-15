from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ISO_DIR = ROOT / "iso"
BASH = shutil.which("bash")
CAN_RUN_ISO_TESTS = BASH is not None and not sys.platform.startswith("win")
pytestmark = pytest.mark.skipif(
    not CAN_RUN_ISO_TESTS,
    reason="ISO script validation runs on Linux/Codespaces",
)


def _run(cmd: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def test_build_script_syntax_valid() -> None:
    result = _run([BASH, "-n", str(ISO_DIR / "build_base.sh")])
    assert result.returncode == 0, result.stderr


def test_chroot_setup_script_syntax_valid() -> None:
    result = _run([BASH, "-n", str(ISO_DIR / "chroot_setup.sh")])
    assert result.returncode == 0, result.stderr


def test_squashfs_script_syntax_valid() -> None:
    result = _run([BASH, "-n", str(ISO_DIR / "build_squashfs.sh")])
    assert result.returncode == 0, result.stderr


def test_iso_script_syntax_valid() -> None:
    result = _run([BASH, "-n", str(ISO_DIR / "build_iso.sh")])
    assert result.returncode == 0, result.stderr


def test_eonix_install_called_with_dev_flag() -> None:
    text = (ISO_DIR / "build_base.sh").read_text(encoding="utf-8")
    assert "eonix-install.sh" in text
    assert re.search(r"eonix-install\.sh[\s\\\n\r]+--dev", text), "Installer must run with --dev"


def test_autostart_config_correct_format() -> None:
    text = (ISO_DIR / "build_base.sh").read_text(encoding="utf-8")
    assert "bash ~/eonix-os/start_eonix.sh &" in text
    assert "startx ~/eonix-os/eonix-desktop/session/start-eonix-desktop.sh" in text


def _run_grub(tmp_path: Path) -> Path:
    env = os.environ.copy()
    env["BUILD_ROOT"] = str(tmp_path / "eonix-iso-build")
    result = _run([BASH, str(ISO_DIR / "grub_config.sh")], env=env)
    assert result.returncode == 0, result.stderr
    return Path(env["BUILD_ROOT"])


def test_grub_config_has_eonix_menu_entry(tmp_path: Path) -> None:
    build_root = _run_grub(tmp_path)
    cfg = (build_root / "image/boot/grub/grub.cfg").read_text(encoding="utf-8")
    assert "menuentry '⚡ Boot EONIX OS'" in cfg
    assert "boot=live" in cfg


def test_grub_timeout_set_to_5(tmp_path: Path) -> None:
    build_root = _run_grub(tmp_path)
    cfg = (build_root / "image/boot/grub/grub.cfg").read_text(encoding="utf-8")
    assert "set timeout=5" in cfg


def test_grub_config_has_safe_mode_entry(tmp_path: Path) -> None:
    build_root = _run_grub(tmp_path)
    cfg = (build_root / "image/boot/grub/grub.cfg").read_text(encoding="utf-8")
    assert "Boot EONIX OS (Safe Mode)" in cfg
    assert "nomodeset" in cfg


def test_efi_directory_structure_correct(tmp_path: Path) -> None:
    build_root = _run_grub(tmp_path)
    assert (build_root / "image/boot/grub/grub.cfg").exists()
    assert (build_root / "image/boot/grub/themes/eonix/theme.txt").exists()
    assert (build_root / "image/EFI/BOOT").is_dir()
