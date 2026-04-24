"""Eonix OS Unified Config Schema.

Shared between PC desktop and future mobile app.
AI agents read/write this on all platforms.
"""
from __future__ import annotations

import json
import os
import platform
from pathlib import Path
from typing import Any, Dict

CONFIG_SCHEMA: Dict[str, Any] = {
    # Appearance
    "accent_color": "#7c4dff",
    "dark_mode": True,
    "font_scale": 1.0,
    "wallpaper_brightness": 1.0,
    "animations_enabled": True,
    "transparency_level": 0.95,

    # AI
    "ai_enabled": True,
    "ai_model": "LightGBM v1.2",
    "ai_voice_enabled": False,
    "ai_proactive": True,

    # Display
    "display_scaling": 1.0,
    "night_light": False,
    "night_light_temp": 4000,

    # Privacy
    "privacy_telemetry": False,
    "privacy_crash_reports": True,
    "privacy_ai_logging": True,

    # Platform (auto-detected)
    "platform": "desktop",
}


def get_platform() -> str:
    """Detect if running on PC or phone."""
    machine = platform.machine().lower()
    if "arm" in machine or "aarch64" in machine:
        return "mobile"
    return "desktop"


def get_config_path() -> Path:
    """Return the path to eonix settings.json based on platform."""
    return Path.home() / ".config" / "eonix" / "settings.json"


def load_config() -> Dict[str, Any]:
    """Load config, applying schema defaults for missing keys."""
    cfg_path = get_config_path()
    base = dict(CONFIG_SCHEMA)
    base["platform"] = get_platform()
    if cfg_path.exists():
        try:
            with open(cfg_path, encoding="utf-8") as f:
                user_cfg = json.load(f)
            base.update(user_cfg)
        except Exception:
            pass
    return base


def save_config(cfg: Dict[str, Any]) -> None:
    """Save config to disk."""
    cfg_path = get_config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def get_value(key: str) -> Any:
    """Read a single config value."""
    return load_config().get(key, CONFIG_SCHEMA.get(key))


def set_value(key: str, value: Any) -> None:
    """Write a single config value."""
    cfg = load_config()
    cfg[key] = value
    save_config(cfg)


# ── Tests ───────────────────────────────────────────────

def test_schema_has_required_keys():
    required = {
        "accent_color", "dark_mode", "font_scale",
        "ai_enabled", "ai_model", "privacy_telemetry",
        "display_scaling", "platform",
    }
    assert required.issubset(set(CONFIG_SCHEMA.keys()))


def test_get_platform_returns_string():
    result = get_platform()
    assert result in {"desktop", "mobile"}


def test_load_config_returns_defaults():
    cfg = load_config()
    assert "accent_color" in cfg
    assert "platform" in cfg
    assert cfg["platform"] in {"desktop", "mobile"}


if __name__ == "__main__":
    import sys
    cfg = load_config()
    print(json.dumps(cfg, indent=2))
    print(f"\nPlatform: {get_platform()}")
