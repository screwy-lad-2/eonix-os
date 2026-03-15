"""Eonix Desktop Settings app (GTK4 with headless-safe mode).

The UI is GTK4 when available; tests run headless using stub widgets. Config
persists to ~/.eonix/config.json (or EONIX_CONFIG override). Inline pytest cases
verify load/save logic and port coercion.
"""
from __future__ import annotations

import json
import os
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

CONFIG_PATH = Path(os.environ.get("EONIX_CONFIG", Path.home() / ".eonix" / "config.json"))

GTK_AVAILABLE = False
try:  # pragma: no cover - exercised only when GTK is present
    import gi  # type: ignore

    gi.require_version("Gtk", "4.0")
    from gi.repository import Gio, Gtk  # type: ignore

    GTK_AVAILABLE = True
except Exception:  # pragma: no cover - headless fallback
    Gio = Gtk = None  # type: ignore

HEADLESS_DEFAULT = not GTK_AVAILABLE or os.environ.get("EONIX_HEADLESS", "0") == "1" or not os.environ.get("DISPLAY")


@dataclass
class AgentConfig:
    goal_port: int = 7735
    context_port: int = 7736
    resource_port: int = 7737
    hub_port: int = 7738
    sync_port: int = 7740
    auto_restart_goal: bool = True
    auto_restart_context: bool = True
    auto_restart_resource: bool = True
    auto_restart_hub: bool = True
    auto_restart_sync: bool = True

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class AppearanceConfig:
    accent_color: str = "#00FF88"
    panel_width: int = 260
    topbar_height: int = 40
    particles: bool = True

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class ModelConfig:
    version: str = "1.2.0"
    accuracy: float = 0.92
    retrain_threshold: float = 0.75

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class SettingsConfig:
    device_name: str = platform.node() or "Eonix Device"
    auto_start: bool = True
    nl_mode: bool = True
    history_size: int = 200
    agents: AgentConfig = field(default_factory=AgentConfig)
    appearance: AppearanceConfig = field(default_factory=AppearanceConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    about: dict[str, Any] = field(default_factory=lambda: {
        "device_id": platform.node() or "unknown-device",
        "github": "https://github.com/",
    })

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_name": self.device_name,
            "auto_start": self.auto_start,
            "nl_mode": self.nl_mode,
            "history_size": self.history_size,
            "agents": self.agents.to_dict(),
            "appearance": self.appearance.to_dict(),
            "model": self.model.to_dict(),
            "about": self.about,
        }


DEFAULT_CONFIG = SettingsConfig().to_dict()


def _ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _coerce_ports(agent_cfg: Dict[str, Any]) -> Dict[str, Any]:
    base: Dict[str, Any] = SettingsConfig().agents.to_dict()
    for key, value in agent_cfg.items():
        if key.endswith("_port"):
            try:
                base[key] = int(value)
            except (TypeError, ValueError):
                pass
        elif key.startswith("auto_restart"):
            base[key] = _to_bool(value)
    return base


def load_config(path: Path = CONFIG_PATH) -> Dict[str, Any]:
    if not path.exists():
        _ensure_dir(path)
        path.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
        return json.loads(json.dumps(DEFAULT_CONFIG))

    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        loaded = {}

    # Merge with defaults to guarantee keys exist
    cfg: Dict[str, Any] = json.loads(json.dumps(DEFAULT_CONFIG))
    cfg.update({k: v for k, v in loaded.items() if k in cfg})
    if "agents" in loaded:
        cfg["agents"] = _coerce_ports(loaded.get("agents", {}))
    return cfg


def save_config(cfg: Dict[str, Any], path: Path = CONFIG_PATH) -> None:
    cfg_copy = json.loads(json.dumps(cfg))  # deep copy
    cfg_copy["agents"] = _coerce_ports(cfg_copy.get("agents", {}))
    _ensure_dir(path)
    path.write_text(json.dumps(cfg_copy, indent=2), encoding="utf-8")


class _StubApp:
    def run(self, argv: list[str] | None = None) -> int:
        return 0


class SettingsApp:
    """GTK app wrapper. In headless mode only load/save logic is exercised."""

    def __init__(self, headless: bool = HEADLESS_DEFAULT, config_path: Path = CONFIG_PATH):
        self.headless = headless
        self.config_path = Path(config_path)
        self.config = load_config(self.config_path)
        if GTK_AVAILABLE and not headless:  # pragma: no cover - UI only when GTK exists
            self.app = Gtk.Application(application_id="ai.eonix.settings")
            self.app.connect("activate", self._on_activate)
        else:
            self.app = _StubApp()

    def _on_activate(self, app):  # pragma: no cover - UI only
        window = Gtk.ApplicationWindow(application=app)
        window.set_title("Eonix Settings")
        window.set_default_size(900, 620)
        stack = Gtk.Stack()
        stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        sidebar = Gtk.StackSidebar()
        sidebar.set_stack(stack)
        # Placeholder pages; real widgets omitted for headless tests
        for name in ["General", "Agents", "Appearance", "Model", "About"]:
            label = Gtk.Label(label=f"{name} settings coming soon")
            stack.add_titled(label, name.lower(), name)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.append(sidebar)
        box.append(stack)
        window.set_child(box)
        window.present()

    def save(self) -> None:
        save_config(self.config, self.config_path)

    def run(self, argv: list[str] | None = None) -> int:
        return self.app.run(argv or [])


def main(argv: list[str] | None = None) -> int:
    app = SettingsApp()
    return app.run(argv)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


# ---------------------------
# Inline unit tests (pytest)
# ---------------------------

def test_settings_loads_config_file(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"device_name": "lab", "agents": {"goal_port": 7744}}), encoding="utf-8")
    cfg = load_config(config_file)
    assert cfg["device_name"] == "lab"
    assert cfg["agents"]["goal_port"] == 7744


def test_settings_saves_changes_to_json(tmp_path):
    config_file = tmp_path / "config.json"
    cfg = load_config(config_file)
    cfg["device_name"] = "workstation"
    save_config(cfg, config_file)
    reloaded = json.loads(config_file.read_text(encoding="utf-8"))
    assert reloaded["device_name"] == "workstation"


def test_agent_port_validated_as_integer(tmp_path):
    config_file = tmp_path / "config.json"
    cfg = load_config(config_file)
    cfg["agents"]["goal_port"] = "7740"
    save_config(cfg, config_file)
    loaded = load_config(config_file)
    assert isinstance(loaded["agents"]["goal_port"], int)
    assert loaded["agents"]["goal_port"] == 7740
