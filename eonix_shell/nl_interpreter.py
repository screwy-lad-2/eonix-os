"""Compatibility shim for eonix-shell/nl_interpreter.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "eonix-shell" / "nl_interpreter.py"
_SPEC = importlib.util.spec_from_file_location("eonix_shell_nl_interpreter_impl", str(_MODULE_PATH))
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"Unable to load nl_interpreter module at {_MODULE_PATH}")

_MOD = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MOD
_SPEC.loader.exec_module(_MOD)

NLInterpreter = _MOD.NLInterpreter
NLResult = _MOD.NLResult
INTENT_SHELL = _MOD.INTENT_SHELL
INTENT_QUERY = _MOD.INTENT_QUERY
INTENT_MEMORY = _MOD.INTENT_MEMORY
INTENT_GOAL = _MOD.INTENT_GOAL

__all__ = [
    "NLInterpreter",
    "NLResult",
    "INTENT_SHELL",
    "INTENT_QUERY",
    "INTENT_MEMORY",
    "INTENT_GOAL",
]
