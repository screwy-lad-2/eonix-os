"""Compatibility package for importing Eonix MIND modules."""

from .system_reader import EonixSystemReader
from .memory import EonixMemory
from .proactive_monitor import ProactiveMonitor

__all__ = ["EonixSystemReader", "EonixMemory", "ProactiveMonitor"]
