from pathlib import Path
import importlib.util

_src = Path(__file__).resolve().parents[1] / "eonix-mind" / "memory.py"
_spec = importlib.util.spec_from_file_location("eonix_mind_memory_impl", str(_src))
_mod = importlib.util.module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
_spec.loader.exec_module(_mod)

EonixMemory = _mod.EonixMemory
