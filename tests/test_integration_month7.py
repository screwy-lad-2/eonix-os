"""Month 7 integration tests for desktop, window manager, sessions, and settings."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
SYS_PATHS = [ROOT, ROOT / "eonix-desktop", ROOT / "eonix-mind"]
for p in SYS_PATHS:
    sys.path.insert(0, str(p))


def _python() -> str:
    return sys.executable


def _run(cmd: list[str], timeout: int = 12, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    proc_env = os.environ.copy()
    proc_env.setdefault("EONIX_HEADLESS", "1")
    proc_env["PYTHONPATH"] = os.pathsep.join([str(p) for p in SYS_PATHS] + [proc_env.get("PYTHONPATH", "")])
    proc_env.setdefault("PYTHONIOENCODING", "utf-8")
    if env:
        proc_env.update(env)
    return subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=proc_env,
    )


def test_desktop_starts_in_panel_only_mode():
    proc = _run([_python(), "eonix-desktop/desktop.py", "--panel-only"], timeout=10)
    stderr = proc.stderr or ""
    assert proc.returncode == 0
    assert "ImportError" not in stderr
    assert "Traceback" not in stderr


def test_memory_widget_standalone_starts():
    proc = _run([_python(), "eonix-desktop/memory_widget.py"], timeout=10)
    assert proc.returncode == 0


def test_window_manager_snap_geometry():
    from window_manager import EonixWindowManager

    wm = EonixWindowManager()
    coords = wm._calculate_snap_coords("left", 1920, 1080)
    assert coords == (0, 40, 960, 1000)


def test_session_manager_save_restore_roundtrip(tmp_path: Path):
    from session_manager import SessionManager
    from window_manager import EonixWindowManager

    wm = EonixWindowManager()
    wm.register_virtual_window("Test Window", pid=101, position=(0, 40, 800, 600))
    sm = SessionManager(wm=wm, sessions_dir=tmp_path)
    sm.save_session("test-goal-week26")
    sessions = sm.list_sessions()
    assert any(s.get("goal_id") == "test-goal-week26" for s in sessions)


def test_settings_config_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from settings import EonixSettings

    cfg_path = tmp_path / "config.json"
    monkeypatch.setenv("EONIX_CONFIG", str(cfg_path))
    settings = EonixSettings(config_path=cfg_path)
    cfg = settings.load()
    cfg["device_name"] = "integration-month7"
    settings.save(cfg)
    reloaded = settings.load()
    assert reloaded["device_name"] == "integration-month7"


def test_all_desktop_modules_importable():
    modules = ["desktop", "settings", "memory_widget", "window_manager", "session_manager"]
    for mod in modules:
        __import__(mod)


def test_desktop_banner_contains_all_sections():
    proc = _run([_python(), "eonix-mind/mind_v2.py", "--banner-only"], timeout=12)
    out = proc.stdout or ""
    assert "⚡ EONIX" in out
    assert "Goal:" in out
    assert "RAM:" in out
    assert "Model:" in out
    assert "Desktop:" in out


def test_goal_workspace_restore_calls_session_manager():
    from desktop import EonixGoalPanel

    panel = EonixGoalPanel(headless=True)
    mock_sm = MagicMock()
    panel.set_session_manager(mock_sm)
    panel.active_goal_id = "goal-123"
    panel.open_workspace()
    mock_sm.restore_session.assert_called_once_with("goal-123")


def test_splash_screen_implemented():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    desktop = os.path.join(REPO, "eonix-desktop/desktop.py")
    with open(desktop, encoding="utf-8") as f: content = f.read()
    assert "fullscreen" in content  # Fullscreen desktop window
    assert "eonix-topbar" in content  # TopBar CSS class
    assert "eonix-goalpanel" in content  # GoalPanel CSS class


def test_workspace_css_class_set():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    desktop = os.path.join(REPO, "eonix-desktop/desktop.py")
    with open(desktop, encoding="utf-8") as f: content = f.read()
    assert "eonix-workspace" in content


def test_clock_format_string():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    desktop = os.path.join(REPO, "eonix-desktop/desktop.py")
    with open(desktop, encoding="utf-8") as f: content = f.read()
    assert "%I:%M" in content
    assert "%p" in content


# ── Week 43: Core Canvas tests ──────────────────────

def test_wallpaper_module_exists():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert os.path.exists(os.path.join(REPO, "eonix-desktop/wallpaper.py"))


def test_dock_module_exists():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert os.path.exists(os.path.join(REPO, "eonix-desktop/dock.py"))


def test_eonix_theme_css_exists():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert os.path.exists(os.path.join(REPO, "eonix-desktop/eonix_theme.css"))


def test_wallpaper_has_four_states():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    f = os.path.join(REPO, "eonix-desktop/wallpaper.py")
    with open(f) as fp:
        c = fp.read()
    for state in ["idle", "active", "thinking", "retrain"]:
        assert state in c

