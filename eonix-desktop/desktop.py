"""Eonix Desktop with launcher, memory-integrated GoalPanel, and headless tests."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import httpx
import psutil

try:
    from memory_widget import MemoryWidget
except Exception:  # pragma: no cover - script import fallback
    MemoryWidget = None  # type: ignore

try:
    from session_manager import SessionManager
except Exception:  # pragma: no cover - script import fallback
    SessionManager = None  # type: ignore

try:
    from window_manager import EonixTaskbar, EonixWindowManager
except Exception:  # pragma: no cover - script import fallback
    EonixTaskbar = EonixWindowManager = None  # type: ignore

try:
    from wallpaper import EonixWallpaper as AuraWallpaper
except Exception:  # pragma: no cover
    AuraWallpaper = None  # type: ignore

try:
    from dock import EonixDock
except Exception:  # pragma: no cover
    EonixDock = None  # type: ignore

try:
    from apps.files_app import EonixFiles
    from apps.settings_app import EonixSettings
except Exception:
    EonixFiles = EonixSettings = None  # type: ignore

GTK_AVAILABLE = False
try:  # pragma: no cover - exercised in CI with GTK installed
    import gi  # type: ignore

    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, Gio, GLib, Gtk  # type: ignore

    GTK_AVAILABLE = True
except Exception:  # pragma: no cover - headless fallback
    Gdk = Gio = GLib = Gtk = None  # type: ignore


HEADLESS_DEFAULT = not GTK_AVAILABLE or os.environ.get("EONIX_HEADLESS", "0") == "1" or not os.environ.get("DISPLAY")


def _eonix_dir() -> Path:
    return Path.home() / ".eonix"


def _apps_file() -> Path:
    return _eonix_dir() / "apps.json"


def _recent_apps_file() -> Path:
    return _eonix_dir() / "recent_apps.json"


@dataclass
class SystemMetrics:
    ram_percent: float = 0.0
    cpu_percent: float = 0.0


@dataclass
class GoalSnapshot:
    goal_id: str = ""
    name: str = "No active goal"
    progress: float = 0.0
    recent_memories: list[dict[str, Any]] = field(default_factory=list)
    context_events: int = 0
    last_event: str = "N/A"


@dataclass
class LauncherApp:
    name: str
    icon: str
    cmd: str
    description: str = ""


def _safe_psutil_percent() -> SystemMetrics:
    return SystemMetrics(ram_percent=psutil.virtual_memory().percent, cpu_percent=psutil.cpu_percent(interval=None))


class DataFetcher:
    def __init__(self, session: Optional[httpx.Client] = None):
        self.session = session or httpx.Client(timeout=3.0)
        self._running = False
        self.goal_url = "http://127.0.0.1:7735/goal/active"
        self.context_url = "http://127.0.0.1:7736/context/summary"
        self.sync_url = "http://127.0.0.1:7740/sync/status"

    def fetch_once(self) -> GoalSnapshot:
        goal_id = ""
        goal_name = "No active goal"
        progress = 0.0
        memories: list[dict[str, Any]] = []
        context_events = 0
        last_event = "N/A"
        try:
            g = self.session.get(self.goal_url)
            if g.status_code == 200:
                payload = g.json()
                goal_id = str(payload.get("id") or "")
                goal_name = str(payload.get("name") or goal_name)
                progress = float(payload.get("progress") or 0.0)
        except Exception:
            pass
        try:
            c = self.session.get(self.context_url)
            if c.status_code == 200:
                payload = c.json()
                context_events = int(payload.get("events_today") or 0)
                last_event = str(payload.get("last_event") or last_event)
                memories = payload.get("recent_memories") or []
        except Exception:
            pass
        if context_events == 0:
            from datetime import datetime
            context_events = 1
            last_event = "Eonix OS v0.9.0 started"
            if not memories:
                memories.append({"type": "system", "msg": last_event, "time": datetime.now().isoformat()})

        return GoalSnapshot(
            goal_id=goal_id,
            name=goal_name,
            progress=progress,
            recent_memories=memories,
            context_events=context_events,
            last_event=last_event,
        )

    def fetch_metrics(self) -> SystemMetrics:
        return _safe_psutil_percent()

    async def run_periodic(self, on_goal: Callable[[GoalSnapshot], None], on_metrics: Callable[[SystemMetrics], None]) -> None:
        self._running = True
        while self._running:
            goal = self.fetch_once()
            on_goal(goal)
            on_metrics(self.fetch_metrics())
            await asyncio.sleep(10)

    def stop(self) -> None:
        self._running = False


class _StubLabel:
    def __init__(self, text: str = ""):
        self._text = text

    def set_text(self, text: str) -> None:
        self._text = text

    def get_text(self) -> str:
        return self._text


class _StubWindow:
    def __init__(self, title: str = ""):
        self.title = title
        self.visible = False

    def present(self) -> None:
        self.visible = True

    def hide(self) -> None:
        self.visible = False


class EonixTopBar:
    def __init__(self, headless: bool = HEADLESS_DEFAULT):
        self.headless = headless
        self.active_goal = ""
        self.ram_display = "RAM 0%"
        self.cpu_display = "CPU 0%"
        self.clock_value = "00:00:00"
        self.alerts = []
        self._label_goal = _StubLabel()
        self._label_clock = _StubLabel()
        self._label_metrics = _StubLabel()
        if GTK_AVAILABLE and not headless:
            self._build_ui()

    def _build_ui(self) -> None:
        self.window = Gtk.Window(title="Eonix Top Bar")  # type: ignore
        self.window.set_decorated(False)
        self.window.set_resizable(False)
        self.window.set_default_size(1920, 40)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)  # type: ignore
        box.set_margin_start(12)
        box.set_margin_end(12)
        self._label_goal = Gtk.Label(label="⚡ EONIX | No active goal")  # type: ignore
        self._label_clock = Gtk.Label(label=self.clock_value)  # type: ignore
        self._label_metrics = Gtk.Label(label=f"{self.ram_display}  {self.cpu_display}")  # type: ignore
        box.append(self._label_goal)  # type: ignore
        box.append(self._label_clock)  # type: ignore
        box.append(self._label_metrics)  # type: ignore
        self.window.set_child(box)

    def update_goal(self, name: str) -> None:
        self.active_goal = name[:30]
        text = f"⚡ EONIX | {self.active_goal or 'No active goal'}"
        self._label_goal.set_text(text)

    def update_metrics(self, metrics: SystemMetrics) -> None:
        self.ram_display = f"RAM {metrics.ram_percent:.0f}%"
        self.cpu_display = f"CPU {metrics.cpu_percent:.0f}%"
        self._label_metrics.set_text(f"{self.ram_display}  {self.cpu_display}")

    def tick_clock(self) -> None:
        self.clock_value = time.strftime("%I:%M %p %a %d %b")
        self._label_clock.set_text(self.clock_value)


class EonixGoalPanel:
    def __init__(self, headless: bool = HEADLESS_DEFAULT):
        self.headless = headless
        self.active_goal_id = ""
        self.active_goal_text = "No active goal"
        self.progress = 0.0
        self.memories: list[dict[str, Any]] = []
        self.context_events = 0
        self.last_event = "N/A"
        self.window = _StubWindow()
        self.memory_widget = MemoryWidget(headless=headless) if MemoryWidget else None
        self.memory_expanded = True
        self.memory_count = 0
        self.standalone_requested = False
        self.session_manager = None
        if GTK_AVAILABLE and not headless:
            self._build_ui()

    def _build_ui(self) -> None:
        self.window = Gtk.Window(title="Eonix Goal Panel")  # type: ignore
        self.window.set_default_size(280, 800)
        self.window.set_resizable(False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)  # type: ignore
        self._goal_label = Gtk.Label(label=self.active_goal_text)  # type: ignore
        self._progress_label = Gtk.Label(label="0% complete")  # type: ignore
        self._context_label = Gtk.Label(label="Context: 0 events")  # type: ignore
        self._memory_header = Gtk.Label(label="🧠 Memories (0)")  # type: ignore
        self._expand_button = Gtk.Button(label="↗ Expand")  # type: ignore
        self._expand_button.connect("clicked", lambda _: self.open_memory_standalone())  # type: ignore
        self._open_workspace_button = Gtk.Button(label="▶ Open Workspace")  # type: ignore
        self._open_workspace_button.connect("clicked", lambda _: self.open_workspace())  # type: ignore
        memory_header_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)  # type: ignore
        memory_header_row.append(self._memory_header)  # type: ignore
        memory_header_row.append(self._expand_button)  # type: ignore
        memory_header_row.append(self._open_workspace_button)  # type: ignore
        box.append(self._goal_label)  # type: ignore
        box.append(self._progress_label)  # type: ignore
        box.append(self._context_label)  # type: ignore
        box.append(memory_header_row)  # type: ignore
        if self.memory_widget is not None and hasattr(self.memory_widget, "container"):
            box.append(self.memory_widget.container)  # type: ignore
        self.window.set_child(box)

    def render_goal(self, goal: GoalSnapshot) -> None:
        self.active_goal_id = goal.goal_id
        self.active_goal_text = goal.name
        self.progress = goal.progress
        self.memories = goal.recent_memories
        self.context_events = goal.context_events
        self.last_event = goal.last_event
        if self.memory_widget is not None:
            self.memory_widget.load_memories()
            self.memory_count = self.memory_widget.memory_count()
        if GTK_AVAILABLE and not self.headless:
            self._goal_label.set_text(goal.name)
            pct = f"{goal.progress * 100:.0f}% complete"
            self._progress_label.set_text(pct)
            self._context_label.set_text(f"Context: {self.context_events} events")
            if self.memory_count == 0:
                self._memory_header.set_text("🧠 Memories (0) — Add your first goal with + Add")
            else:
                self._memory_header.set_text(f"🧠 Memories ({self.memory_count})")

    def toggle_memory_section(self) -> None:
        self.memory_expanded = not self.memory_expanded

    def open_memory_standalone(self) -> None:
        self.standalone_requested = True
        if self.memory_widget is not None and self.headless:
            self.memory_widget.open_standalone()
        elif not self.headless:
            subprocess.Popen("python3 eonix-desktop/memory_widget.py", shell=True)

    def set_session_manager(self, manager: Any) -> None:
        self.session_manager = manager

    def open_workspace(self) -> dict[str, Any]:
        if self.session_manager is None:
            return {"ok": False, "error": "session manager missing"}
        if not self.active_goal_id:
            return {"ok": False, "error": "no active goal"}
        return self.session_manager.restore_session(self.active_goal_id)


def _load_aura_css() -> None:
    """Load the Eonix Aura design system CSS globally."""
    if not GTK_AVAILABLE:
        return
    css_path = Path(__file__).parent / "eonix_theme.css"
    if css_path.exists():
        try:
            css_data = css_path.read_bytes()
            provider = Gtk.CssProvider()
            provider.load_from_data(css_data)
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(),
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )
        except Exception:
            pass  # CSS loading is non-fatal


class EonixWallpaper:
    """Wallpaper wrapper — delegates to AuraWallpaper (particle) or basic window."""

    def __init__(self, headless: bool = HEADLESS_DEFAULT):
        self.headless = headless
        self.watermark = ""
        self.aura = None  # The neural particle widget
        self.window = _StubWindow()
        if GTK_AVAILABLE and not headless:
            self.window = Gtk.Window(title="Eonix Desktop")  # type: ignore
            self.window.set_default_size(1920, 1080)
            self.window.set_decorated(False)
            self.window.add_css_class("eonix-workspace")

            # Load Aura CSS design system
            _load_aura_css()

            # Create the neural particle wallpaper widget
            if AuraWallpaper is not None:
                self.aura = AuraWallpaper()
                self.aura.set_hexpand(True)
                self.aura.set_vexpand(True)

    def set_watermark(self, text: str) -> None:
        self.watermark = text

    def set_state(self, state: str) -> None:
        """Forward state change to the neural particle wallpaper."""
        if self.aura is not None and hasattr(self.aura, 'set_state'):
            self.aura.set_state(state)


class EonixLauncher:
    def __init__(
        self,
        headless: bool = HEADLESS_DEFAULT,
        goal_client: Optional[httpx.Client] = None,
        launch_exec: Optional[Callable[[str], None]] = None,
    ):
        self.headless = headless
        self.window = _StubWindow()
        self.visible = False
        self.goal_client = goal_client or httpx.Client(timeout=3.0)
        self.launch_exec = launch_exec or (lambda cmd: subprocess.Popen(cmd, shell=True))
        self.apps = self._load_apps()
        self.recent_apps = self._load_recent_apps()
        self.filtered_apps = list(self.apps)
        self.selected_index = 0
        self.last_query = ""
        self.pending_goal_text = ""
        if GTK_AVAILABLE and not headless:
            self.window = Gtk.Window(title="Eonix Launcher")  # type: ignore
            self.window.set_default_size(600, 400)

    def _default_apps(self) -> list[LauncherApp]:
        return [
            LauncherApp("EonixShell", "⚡", "eonix-shell", "Natural language shell"),
            LauncherApp("Eonix Hub", "🌐", "xdg-open http://localhost:7750", "Open Eonix Hub"),
            LauncherApp("Memory", "🧠", "python3 eonix-desktop/memory_widget.py", "Memory browser"),
            LauncherApp("Settings", "⚙️", "python3 eonix-desktop/settings.py", "Desktop settings"),
            LauncherApp("Files", "📁", "nautilus", "File manager"),
            LauncherApp("Terminal", "🖥️", "gnome-terminal", "Terminal emulator"),
            LauncherApp("Browser", "🌍", "xdg-open https://", "Web browser"),
            LauncherApp("VS Code", "💻", "code .", "Code editor"),
        ]

    def _load_apps(self) -> list[LauncherApp]:
        eonix_dir = _eonix_dir()
        apps_file = _apps_file()
        eonix_dir.mkdir(parents=True, exist_ok=True)
        if not apps_file.exists():
            defaults = [a.__dict__ for a in self._default_apps()]
            apps_file.write_text(json.dumps(defaults, indent=2), encoding="utf-8")
            return self._default_apps()
        try:
            payload = json.loads(apps_file.read_text(encoding="utf-8"))
            out: list[LauncherApp] = []
            for item in payload:
                out.append(
                    LauncherApp(
                        name=str(item.get("name", "App")),
                        icon=str(item.get("icon", "•")),
                        cmd=str(item.get("cmd", "")),
                        description=str(item.get("description", "")),
                    )
                )
            return out or self._default_apps()
        except Exception:
            return self._default_apps()

    def _load_recent_apps(self) -> list[str]:
        recent_file = _recent_apps_file()
        if not recent_file.exists():
            return []
        try:
            data = json.loads(recent_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [str(x) for x in data[:5]]
        except Exception:
            pass
        return []

    def _save_recent_apps(self) -> None:
        recent_file = _recent_apps_file()
        recent_file.parent.mkdir(parents=True, exist_ok=True)
        recent_file.write_text(json.dumps(self.recent_apps[:5], indent=2), encoding="utf-8")

    def record_recent(self, app_name: str) -> None:
        names = [x for x in self.recent_apps if x != app_name]
        self.recent_apps = [app_name, *names][:5]
        self._save_recent_apps()

    def combined_grid(self) -> list[LauncherApp]:
        recent = [a for a in self.apps if a.name in self.recent_apps]
        recent.sort(key=lambda x: self.recent_apps.index(x.name))
        remain = [a for a in self.filtered_apps if a.name not in self.recent_apps]
        return recent + remain

    def filter_apps(self, query: str) -> list[LauncherApp]:
        self.last_query = query
        q = query.strip().lower()
        if not q:
            self.filtered_apps = list(self.apps)
            self.pending_goal_text = ""
        else:
            self.filtered_apps = [
                a
                for a in self.apps
                if q in a.name.lower() or q in (a.description or "").lower()
            ]
            self.pending_goal_text = query if not self.filtered_apps else ""
        self.selected_index = 0
        return self.filtered_apps

    def launch_selected(self) -> bool:
        grid = self.combined_grid()
        if not grid:
            if self.pending_goal_text:
                return self.create_goal_from_input(self.pending_goal_text)
            return False
        idx = max(0, min(self.selected_index, len(grid) - 1))
        app = grid[idx]
        if app.cmd:
            self.launch_exec(app.cmd)
            self.record_recent(app.name)
            self.close()
            return True
        return False

    def create_goal_from_input(self, text: str) -> bool:
        payload = {"name": text.strip(), "description": ""}
        if not payload["name"]:
            return False
        try:
            response = self.goal_client.post("http://127.0.0.1:7735/goal/create", json=payload)
            if response.status_code in (200, 201):
                self.close()
                return True
        except Exception:
            return False
        return False

    def on_key(self, key: str) -> bool:
        if key == "Escape":
            self.close()
            return True
        if key == "Enter":
            return self.launch_selected()
        grid = self.combined_grid()
        if key in ("Down", "Right") and grid:
            self.selected_index = min(self.selected_index + 1, len(grid) - 1)
            return True
        if key in ("Up", "Left") and grid:
            self.selected_index = max(self.selected_index - 1, 0)
            return True
        return False

    def open(self) -> None:
        self.visible = True
        self.window.present()

    def close(self) -> None:
        self.visible = False
        self.window.hide()


class EonixTray:
    def __init__(self):
        self.health_state = "unknown"

    def update(self, healthy: bool) -> None:
        self.health_state = "green" if healthy else "red"


class EonixDesktop:
    def __init__(self, headless: bool = HEADLESS_DEFAULT, panel_only: bool = False):
        self.headless = headless
        self.panel_only = panel_only
        self.current_goal_id = ""
        self.current_goal_name = ""
        self.top_bar = EonixTopBar(headless=headless)
        self.goal_panel = EonixGoalPanel(headless=headless)
        self.wallpaper = EonixWallpaper(headless=headless)
        self.launcher = EonixLauncher(headless=headless)
        self.dock = EonixDock(on_launch=self._handle_dock_launch) if (EonixDock and not headless) else _StubWindow("Dock")
        self.tray = EonixTray()
        self.window_manager = EonixWindowManager() if EonixWindowManager else None
        self.taskbar = EonixTaskbar(self.window_manager, headless=headless) if (EonixTaskbar and self.window_manager) else _StubWindow("Taskbar")
        self.session_manager = SessionManager(wm=self.window_manager) if (SessionManager and self.window_manager) else None
        self.goal_panel.set_session_manager(self.session_manager)
        self.fetcher = DataFetcher()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._bg_thread: Optional[threading.Thread] = None
        self._wm_loop_thread: Optional[threading.Thread] = None
        self._autosave_loop_thread: Optional[threading.Thread] = None
        self._running_loops = False
        self.loop_registry: list[str] = []

    def _launch_terminal(self) -> None:
        """Launch styled terminal inside window manager using VTE if available."""
        if not GTK_AVAILABLE:
            return
        
        widget = None
        try:
            gi.require_version("Vte", "2.91")
            from gi.repository import Vte
            term = Vte.Terminal()
            term.add_css_class("eonix-terminal")
            term.spawn_async(
                Vte.PtyFlags.DEFAULT,
                None, ["/bin/bash"], None,
                GLib.SpawnFlags.DO_NOT_REAP_CHILD,
                None, None, -1, None, None
            )
            widget = term
        except Exception:
            # Fallback: styled TextView
            tv = Gtk.TextView()
            tv.add_css_class("eonix-terminal-view")
            tv.set_editable(True)
            tv.set_monospace(True)
            tv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
            
            buf = tv.get_buffer()
            buf.set_text("eonix@eonix-os:~$ ")
            
            scroll = Gtk.ScrolledWindow()
            scroll.set_child(tv)
            scroll.set_vexpand(True)
            scroll.set_hexpand(True)
            widget = scroll

        if self.window_manager and widget:
            self.window_manager.open(
                "⚡ EonixShell",
                widget,
                x=80, y=60,
                w=700, h=440
            )

    def _handle_dock_launch(self, app_name: str) -> None:
        """Called when a dock icon is clicked."""
        if not self.window_manager:
            return

        if app_name in ("Terminal", "EonixShell"):
            self._launch_terminal()
        elif app_name == "Files" and EonixFiles:
            self.window_manager.open("📁 Files", EonixFiles(), x=140, y=80, w=720, h=480)
        elif app_name == "Settings" and EonixSettings:
            self.window_manager.open("⚙️ Settings", EonixSettings(), x=180, y=100, w=680, h=480)
        # Week 45: wire to actual app launchers

    def _apply_goal_snapshot(self, snapshot: GoalSnapshot) -> None:
        self.current_goal_id = snapshot.goal_id
        self.current_goal_name = snapshot.name
        self.top_bar.update_goal(snapshot.name)
        self.goal_panel.render_goal(snapshot)
        self.wallpaper.set_watermark(snapshot.name)
        # Trigger neural particle "thinking" state when a goal is active
        if snapshot.goal_id:
            self.wallpaper.set_state("active")

    def _apply_metrics(self, metrics: SystemMetrics) -> None:
        self.top_bar.update_metrics(metrics)

    def start_background_refresh(self) -> None:
        if self.headless:
            return
        self._loop = asyncio.new_event_loop()

        def _safe_apply_snapshot(snap: GoalSnapshot) -> None:
            """Marshal GTK updates to the main thread via GLib.idle_add."""
            if GTK_AVAILABLE and GLib:
                GLib.idle_add(self._apply_goal_snapshot, snap)
            else:
                self._apply_goal_snapshot(snap)

        def _safe_apply_metrics(m: SystemMetrics) -> None:
            if GTK_AVAILABLE and GLib:
                GLib.idle_add(self._apply_metrics, m)
            else:
                self._apply_metrics(m)

        async def runner() -> None:
            await self.fetcher.run_periodic(_safe_apply_snapshot, _safe_apply_metrics)

        def spin() -> None:
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(runner())

        self._bg_thread = threading.Thread(target=spin, daemon=True)
        self._bg_thread.start()

    def _wm_scan_loop(self) -> None:
        while self._running_loops:
            if self.window_manager:
                self.window_manager.scan_windows()
            if hasattr(self.taskbar, "refresh"):
                self.taskbar.refresh()  # type: ignore[attr-defined]
            time.sleep(2)

    def _session_autosave_loop(self) -> None:
        while self._running_loops:
            if self.session_manager and self.current_goal_id:
                self.session_manager.save_session(self.current_goal_id, self.current_goal_name)
            time.sleep(300)

    def start_runtime_loops(self) -> None:
        self._running_loops = True
        self.loop_registry.append("wm_scan_2s")
        self.loop_registry.append("session_autosave_5min")
        if self.headless:
            return
        self._wm_loop_thread = threading.Thread(target=self._wm_scan_loop, daemon=True)
        self._autosave_loop_thread = threading.Thread(target=self._session_autosave_loop, daemon=True)
        self._wm_loop_thread.start()
        self._autosave_loop_thread.start()

    def restore_active_goal_workspace(self) -> dict[str, Any]:
        snapshot = self.fetcher.fetch_once()
        self._apply_goal_snapshot(snapshot)
        if not self.session_manager or not snapshot.goal_id:
            return {"ok": False, "error": "no active goal"}
        return self.session_manager.restore_session(snapshot.goal_id)

    def stop(self) -> None:
        self._running_loops = False
        self.fetcher.stop()
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

    def run(self) -> None:
        self.restore_active_goal_workspace()
        self.start_runtime_loops()
        if self.panel_only:
            self.goal_panel.window.present()
            return

        if GTK_AVAILABLE and not self.headless:
            # ── Build the desktop layout ──────────────────────
            # Simple Box layout — no Overlay (DrawingArea has 0 natural size
            # which causes Overlay to collapse). Particles fill workspace.
            root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            root.set_hexpand(True)
            root.set_vexpand(True)

            # ── TopBar (spans full width) ────────────────────
            topbar_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            topbar_box.set_hexpand(True)
            topbar_box.add_css_class("eonix-topbar")
            topbar_box.set_margin_start(12)
            topbar_box.set_margin_end(12)
            lbl_goal = Gtk.Label(label="\u26a1 EONIX | No active goal")
            lbl_clock = Gtk.Label(label=self.top_bar.clock_value)
            lbl_metrics = Gtk.Label(label=f"{self.top_bar.ram_display}  {self.top_bar.cpu_display}")
            topbar_box.append(lbl_goal)
            spacer = Gtk.Box()
            spacer.set_hexpand(True)
            topbar_box.append(spacer)
            topbar_box.append(lbl_metrics)
            topbar_box.append(lbl_clock)
            self.top_bar._label_goal = lbl_goal
            self.top_bar._label_clock = lbl_clock
            self.top_bar._label_metrics = lbl_metrics
            root.append(topbar_box)

            # ── Content row: GoalPanel + Workspace ───────────
            content_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            content_row.set_hexpand(True)
            content_row.set_vexpand(True)

            # GoalPanel sidebar (fixed width, full height)
            panel_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            panel_box.add_css_class("eonix-goalpanel")
            panel_box.set_size_request(240, -1)
            panel_box.set_vexpand(True)

            # Panel header
            header = Gtk.Label(label="\U0001f9e0  GOALS")
            header.set_halign(Gtk.Align.START)
            header.set_margin_start(12)
            header.set_margin_top(12)
            header.set_margin_bottom(8)
            header.add_css_class("eonix-accent")
            panel_box.append(header)

            goal_label = Gtk.Label(label=self.goal_panel.active_goal_text)
            goal_label.set_halign(Gtk.Align.START)
            goal_label.set_margin_start(12)
            progress_label = Gtk.Label(label="0% complete")
            progress_label.set_halign(Gtk.Align.START)
            progress_label.set_margin_start(12)
            progress_label.add_css_class("eonix-muted")
            context_label = Gtk.Label(label="Context: 0 events")
            context_label.set_halign(Gtk.Align.START)
            context_label.set_margin_start(12)
            context_label.add_css_class("eonix-muted")
            memory_header = Gtk.Label(label="\U0001f9e0 Memories (0)")
            memory_header.set_halign(Gtk.Align.START)
            memory_header.set_margin_start(12)
            panel_box.append(goal_label)
            panel_box.append(progress_label)
            panel_box.append(context_label)
            panel_box.append(memory_header)

            # Empty-state hint
            hint = Gtk.Label(label="Add your first goal\nwith the MIND agent")
            hint.set_halign(Gtk.Align.CENTER)
            hint.set_valign(Gtk.Align.CENTER)
            hint.set_vexpand(True)
            hint.add_css_class("eonix-muted")
            panel_box.append(hint)

            if hasattr(self.goal_panel, '_goal_label'):
                self.goal_panel._goal_label = goal_label
                self.goal_panel._progress_label = progress_label
                self.goal_panel._context_label = context_label
                self.goal_panel._memory_header = memory_header
            content_row.append(panel_box)

            # Separator between panel and workspace
            sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
            sep.add_css_class("eonix-separator")
            content_row.append(sep)

            # Workspace: neural particle wallpaper fills this area
            if self.wallpaper.aura is not None:
                self.wallpaper.aura.set_hexpand(True)
                self.wallpaper.aura.set_vexpand(True)
                content_row.append(self.wallpaper.aura)
            else:
                workspace = Gtk.Box()
                workspace.set_hexpand(True)
                workspace.set_vexpand(True)
                workspace.add_css_class("eonix-workspace")
                content_row.append(workspace)

            root.append(content_row)

            # ── Dock at bottom (spans full width) ────────────
            if hasattr(self.dock, 'set_hexpand'):
                self.dock.set_hexpand(True)
                root.append(self.dock)

            self.wallpaper.window.set_child(root)

            # Start clock ticking
            self.top_bar.tick_clock()
            def _clock_tick():
                self.top_bar.tick_clock()
                return True
            GLib.timeout_add(1000, _clock_tick)

        # Present and then fullscreen (order matters for some WMs)
        self.wallpaper.window.present()
        if GTK_AVAILABLE and not self.headless:
            self.wallpaper.window.fullscreen()
        self.start_background_refresh()
        if GTK_AVAILABLE and not self.headless:
            GLib.MainLoop().run()  # GTK4 event loop


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run Eonix Desktop")
    parser.add_argument("--panel-only", action="store_true", help="Start only the GoalPanel")
    parser.add_argument("--headless", action="store_true", help="Force headless mode")
    args = parser.parse_args(argv)
    desktop = EonixDesktop(headless=args.headless or HEADLESS_DEFAULT, panel_only=args.panel_only)
    desktop.run()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


# ---------------------------
# Inline unit tests (pytest)
# ---------------------------

def test_top_bar_initialises_without_crash():
    bar = EonixTopBar(headless=True)
    bar.tick_clock()
    assert bar._label_clock.get_text()


def test_goal_panel_fetches_active_goal(monkeypatch):
    panel = EonixGoalPanel(headless=True)
    snapshot = GoalSnapshot(name="Build Desktop", progress=0.42, recent_memories=[{"type": "file", "text": "edited"}], context_events=3, last_event="file")
    panel.render_goal(snapshot)
    assert panel.active_goal_text == "Build Desktop"
    assert panel.progress == 0.42
    assert panel.context_events == 3


def test_data_refresh_updates_ram_display():
    bar = EonixTopBar(headless=True)
    metrics = SystemMetrics(ram_percent=37.5, cpu_percent=12.3)
    bar.update_metrics(metrics)
    assert "RAM 38%" in bar.ram_display
    assert "CPU 12%" in bar.cpu_display


def test_launcher_opens_on_super_key():
    launcher = EonixLauncher(headless=True)
    launcher.open()
    assert launcher.visible is True
    launcher.close()
    assert launcher.visible is False


def test_desktop_starts_in_panel_only_mode():
    desktop = EonixDesktop(headless=True, panel_only=True)
    desktop.run()
    assert desktop.panel_only is True
    assert desktop.goal_panel.window.visible is True


def test_launcher_filters_apps_on_search(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    launcher = EonixLauncher(headless=True)
    results = launcher.filter_apps("memory")
    assert results
    assert any(a.name == "Memory" for a in results)


def test_launcher_creates_goal_for_unknown_input():
    class FakeGoalClient:
        def __init__(self):
            self.payload = {}

        def post(self, url, json):
            self.payload = {"url": url, "json": json}

            class Resp:
                status_code = 200

            return Resp()

    client = FakeGoalClient()
    launcher = EonixLauncher(headless=True, goal_client=client, launch_exec=lambda _: None)
    launcher.filter_apps("something very unique")
    ok = launcher.create_goal_from_input("something very unique")
    assert ok is True
    assert client.payload["url"].endswith("/goal/create")
    assert client.payload["json"]["name"] == "something very unique"


def test_window_manager_initialises_in_desktop():
    desktop = EonixDesktop(headless=True)
    assert desktop.window_manager is not None


def test_session_auto_save_registered_in_loop():
    desktop = EonixDesktop(headless=True)
    desktop.start_runtime_loops()
    assert "session_autosave_5min" in desktop.loop_registry
    desktop.stop()
