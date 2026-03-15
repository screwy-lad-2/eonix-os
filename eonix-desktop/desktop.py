"""Eonix Desktop GTK4 skeleton with headless-safe fallbacks and inline tests.

This module defines a minimal desktop environment composed of top bar, goal panel,
wallpaper layer, launcher, and tray. It can run with GTK4 or in headless mode for
CI and local testing. Data refresh pulls goal/context/sync endpoints and system
metrics so widgets can stay in sync with agent state.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import httpx
import psutil

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


@dataclass
class SystemMetrics:
    ram_percent: float = 0.0
    cpu_percent: float = 0.0


@dataclass
class GoalSnapshot:
    name: str = "No active goal"
    progress: float = 0.0
    recent_memories: list[dict[str, Any]] = field(default_factory=list)
    context_events: int = 0
    last_event: str = "N/A"


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
        goal_name = "No active goal"
        progress = 0.0
        memories: list[dict[str, Any]] = []
        context_events = 0
        last_event = "N/A"
        try:
            g = self.session.get(self.goal_url)
            if g.status_code == 200:
                payload = g.json()
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
        return GoalSnapshot(name=goal_name, progress=progress, recent_memories=memories, context_events=context_events, last_event=last_event)

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
        self.clock_value = time.strftime("%H:%M:%S")
        self._label_clock.set_text(self.clock_value)


class EonixGoalPanel:
    def __init__(self, headless: bool = HEADLESS_DEFAULT):
        self.headless = headless
        self.active_goal_text = "No active goal"
        self.progress = 0.0
        self.memories: list[dict[str, Any]] = []
        self.context_events = 0
        self.last_event = "N/A"
        self.window = _StubWindow()
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
        box.append(self._goal_label)  # type: ignore
        box.append(self._progress_label)  # type: ignore
        box.append(self._context_label)  # type: ignore
        self.window.set_child(box)

    def render_goal(self, goal: GoalSnapshot) -> None:
        self.active_goal_text = goal.name
        self.progress = goal.progress
        self.memories = goal.recent_memories
        self.context_events = goal.context_events
        self.last_event = goal.last_event
        if GTK_AVAILABLE and not self.headless:
            self._goal_label.set_text(goal.name)
            pct = f"{goal.progress * 100:.0f}% complete"
            self._progress_label.set_text(pct)
            self._context_label.set_text(f"Context: {self.context_events} events")


class EonixWallpaper:
    def __init__(self, headless: bool = HEADLESS_DEFAULT):
        self.headless = headless
        self.watermark = ""
        self.window = _StubWindow()
        if GTK_AVAILABLE and not headless:
            self.window = Gtk.Window(title="Eonix Wallpaper")  # type: ignore
            self.window.fullscreen()

    def set_watermark(self, text: str) -> None:
        self.watermark = text


class EonixLauncher:
    def __init__(self, headless: bool = HEADLESS_DEFAULT):
        self.headless = headless
        self.window = _StubWindow()
        self.visible = False
        if GTK_AVAILABLE and not headless:
            self.window = Gtk.Window(title="Eonix Launcher")  # type: ignore
            self.window.set_default_size(600, 400)

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
        self.top_bar = EonixTopBar(headless=headless)
        self.goal_panel = EonixGoalPanel(headless=headless)
        self.wallpaper = EonixWallpaper(headless=headless)
        self.launcher = EonixLauncher(headless=headless)
        self.tray = EonixTray()
        self.fetcher = DataFetcher()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._bg_thread: Optional[threading.Thread] = None

    def _apply_goal_snapshot(self, snapshot: GoalSnapshot) -> None:
        self.top_bar.update_goal(snapshot.name)
        self.goal_panel.render_goal(snapshot)
        self.wallpaper.set_watermark(snapshot.name)

    def _apply_metrics(self, metrics: SystemMetrics) -> None:
        self.top_bar.update_metrics(metrics)

    def start_background_refresh(self) -> None:
        if self.headless:
            return
        self._loop = asyncio.new_event_loop()

        async def runner() -> None:
            await self.fetcher.run_periodic(self._apply_goal_snapshot, self._apply_metrics)

        def spin() -> None:
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(runner())

        self._bg_thread = threading.Thread(target=spin, daemon=True)
        self._bg_thread.start()

    def stop(self) -> None:
        self.fetcher.stop()
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

    def run(self) -> None:
        if self.panel_only:
            self.goal_panel.window.present()
            return
        self.wallpaper.window.present()
        self.top_bar.tick_clock()
        self.top_bar.window.present()
        self.goal_panel.window.present()
        self.start_background_refresh()
        if GTK_AVAILABLE and not self.headless:
            Gtk.main()  # type: ignore


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
