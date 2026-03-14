"""Compatibility re-export for eonix-mind/proactive_monitor.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_REAL = Path(__file__).resolve().parents[1] / "eonix-mind" / "proactive_monitor.py"
_spec = importlib.util.spec_from_file_location("eonix_mind_proactive_real", str(_REAL))
if _spec is None or _spec.loader is None:
    raise ImportError("Could not load eonix-mind/proactive_monitor.py")

_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

ProactiveMonitor = _mod.ProactiveMonitor
