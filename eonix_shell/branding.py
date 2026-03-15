"""Compatibility shim for eonix-shell/branding.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "eonix-shell" / "branding.py"
_SPEC = importlib.util.spec_from_file_location("eonix_shell_branding_impl", str(_MODULE_PATH))
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"Unable to load branding module at {_MODULE_PATH}")

_MOD = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MOD
_SPEC.loader.exec_module(_MOD)

print_boot_art = _MOD.print_boot_art
progress_bar = _MOD.progress_bar
status_line = _MOD.status_line
format_banner = _MOD.format_banner

__all__ = ["print_boot_art", "progress_bar", "status_line", "format_banner"]
