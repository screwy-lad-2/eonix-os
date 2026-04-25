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


# ── Week 44: UI Polish tests ────────────────────────

def test_terminal_has_dark_theme():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    f = os.path.join(REPO, "eonix-desktop/eonix_theme.css")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "eonix-terminal-view" in c
    assert "#a0ff80" in c  # green terminal text


def test_dock_uses_noto_emoji_font():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    f = os.path.join(REPO, "eonix-desktop/dock.py")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "Noto" in c or "noto" in c


def test_goalpanel_has_css_class():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    f = os.path.join(REPO, "eonix-desktop/desktop.py")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "eonix-goalpanel" in c


def test_agent_startup_is_async():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    f = os.path.join(REPO, "eonix-desktop/desktop.py")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "threading" in c or "idle_add" in c


# ── Week 45: Core Apps tests ────────────────────────

def test_files_app_exists():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert os.path.exists(os.path.join(REPO, "eonix-desktop/apps/files_app.py"))


def test_settings_app_exists():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert os.path.exists(os.path.join(REPO, "eonix-desktop/apps/settings_app.py"))


def test_terminal_uses_vte_or_textview():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    f = os.path.join(REPO, "eonix-desktop/desktop.py")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "Vte" in c or "eonix-terminal-view" in c


def test_files_app_has_dir_loading():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    f = os.path.join(REPO, "eonix-desktop/apps/files_app.py")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "_load_dir" in c
    assert "os.scandir" in c


def test_settings_shows_model_version():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    f = os.path.join(REPO, "eonix-desktop/apps/settings_app.py")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "model_version" in c or "v1.2" in c


def test_no_rm_rf_on_system_dirs():
    """Verify chroot_setup.sh does not delete system-critical directories."""
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    f = os.path.join(REPO, "iso/chroot_setup.sh")
    if not os.path.exists(f):
        pytest.skip("No chroot_setup.sh")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "rm -rf /usr/share/locale" not in c
    assert "rm -rf /usr/lib" not in c
    assert "rm -rf /usr/share/doc" not in c
    assert "rm -rf /usr/share/man" not in c


def test_terminal_launch_has_fallback():
    """Terminal must have VTE fallback."""
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    f = os.path.join(REPO, "eonix-desktop/desktop.py")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "launched_vte" in c or "eonix-terminal-view" in c


# ── Week 46 tests ──

def test_settings_has_dark_css_class():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    f = os.path.join(REPO, "eonix-desktop/apps/settings_app.py")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "eonix-settings-root" in c


def test_terminal_sets_vte_colors():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    f = os.path.join(REPO, "eonix-desktop/desktop.py")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "set_colors" in c or "parse(" in c


def test_traffic_buttons_custom():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    f = os.path.join(REPO, "eonix-desktop/window_manager.py")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "btn-close" in c
    assert "btn-min" in c
    assert "btn-max" in c


def test_window_has_no_decoration():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    f = os.path.join(REPO, "eonix-desktop/window_manager.py")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "set_decorated(False)" in c or "set_titlebar" in c


def test_ai_dot_in_topbar():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    f = os.path.join(REPO, "eonix-desktop/desktop.py")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "ai-active-dot" in c


def test_no_xterm_subprocess():
    """No xterm or system terminal calls anywhere in eonix-desktop."""
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    desktop_dir = os.path.join(REPO, "eonix-desktop")
    for root, dirs, fnames in os.walk(desktop_dir):
        for f in fnames:
            if f.endswith('.py'):
                fpath = os.path.join(root, f)
                with open(fpath, encoding="utf-8") as fp:
                    content = fp.read()
                for bad in ["xterm", "gnome-terminal", "x-terminal-emulator"]:
                    assert bad not in content, f"{bad} found in {fpath}"


def test_mind_app_has_real_content():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    f = os.path.join(REPO, "eonix-desktop/desktop.py")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "mind-online" in c or "LightGBM" in c


def test_settings_has_inline_css_fallback():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    f = os.path.join(REPO, "eonix-desktop/apps/settings_app.py")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "_apply_dark_fallback" in c or "CssProvider" in c


def test_settings_saves_json():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    f = os.path.join(REPO, "eonix-desktop/apps/settings_app.py")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "settings.json" in c
    assert "_save_config" in c


def test_settings_has_appearance_controls():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    f = os.path.join(REPO, "eonix-desktop/apps/settings_app.py")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "Gtk.Switch" in c
    assert "Gtk.Scale" in c
    assert "ColorButton" in c


def test_ai_can_write_settings():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    f = os.path.join(REPO, "eonix-core/eonix_config_schema.py")
    assert os.path.exists(f), "Config schema missing"
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "CONFIG_SCHEMA" in c


def test_nautilus_in_iso_packages():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    f = os.path.join(REPO, "iso/chroot_setup.sh")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "nautilus" in c


def test_ai_chat_app_exists():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    f = os.path.join(REPO, "eonix-desktop/apps/ai_chat_app.py")
    assert os.path.exists(f)
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "EonixAIChat" in c
    assert "_match_command" in c
    assert "psutil" in c


def test_ai_chat_handles_help():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(REPO, "eonix-desktop/apps/ai_chat_app.py"),
              encoding="utf-8") as f:
        c = f.read()
    assert "def _match_command" in c
    assert "dark mode on" in c
    assert "list files" in c
    assert "font" in c


def test_notes_app_exists():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    f = os.path.join(REPO, "eonix-desktop/apps/notes_app.py")
    assert os.path.exists(f)
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "EonixNotes" in c
    assert "notes.json" in c
    assert "_save" in c


def test_hub_has_ai_api():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    f = os.path.join(REPO, "eonix-hub/hub_server.py")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "/api/ai/command" in c
    assert "/api/settings" in c


def test_settings_live_apply():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    f = os.path.join(REPO, "eonix-desktop/apps/settings_app.py")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "_apply_live" in c
    assert "gtk-font-name" in c


def test_desktop_xdg_dirs_in_iso():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    f = os.path.join(REPO, "iso/chroot_setup.sh")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "Desktop" in c
    assert "xdg-user-dirs" in c


def test_ctrl_space_shortcut():
    import os
    REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    f = os.path.join(REPO, "eonix-desktop/desktop.py")
    with open(f, encoding="utf-8") as fp:
        c = fp.read()
    assert "KEY_space" in c
