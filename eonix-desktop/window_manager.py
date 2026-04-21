"""Eonix desktop window manager with headless-safe fallbacks and taskbar."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import httpx

GTK_AVAILABLE = False
try:  # pragma: no cover
    import gi  # type: ignore

    gi.require_version("Gtk", "4.0")
    from gi.repository import GLib, Gtk  # type: ignore

    GTK_AVAILABLE = True
except Exception:  # pragma: no cover
    GLib = Gtk = None  # type: ignore

XLIB_AVAILABLE = False
try:  # pragma: no cover
    from Xlib import X, display  # type: ignore

    XLIB_AVAILABLE = True
except Exception:  # pragma: no cover
    X = display = None  # type: ignore


@dataclass
class EonixWindow:
    xid: int
    title: str
    pid: int
    position: tuple[int, int, int, int]
    is_focused: bool = False
    goal_score: float = 0.0
    snap_zone: Optional[str] = None


class _StubTaskbarWindow:
    def __init__(self):
        self.visible = False

    def present(self) -> None:
        self.visible = True


class EonixWindowManager:
    def __init__(
        self,
        screen_size: tuple[int, int] = (1920, 1080),
        top_offset: int = 40,
        bottom_offset: int = 40,
        window_source: Optional[Callable[[], list[EonixWindow]]] = None,
        goal_client: Optional[httpx.Client] = None,
        context_client: Optional[httpx.Client] = None,
    ):
        self.screen_size = screen_size
        self.top_offset = top_offset
        self.bottom_offset = bottom_offset
        self.window_source = window_source
        self.goal_client = goal_client or httpx.Client(timeout=1.0)
        self.context_client = context_client or httpx.Client(timeout=1.0)
        self.registry: dict[int, EonixWindow] = {}
        self.hotkeys: dict[str, str] = {}
        self._focused_xid: Optional[int] = None
        self._xdisplay = None
        if XLIB_AVAILABLE:
            try:
                self._xdisplay = display.Display()  # type: ignore[attr-defined]
            except Exception:
                self._xdisplay = None

    def _active_goal_name(self) -> str:
        try:
            res = self.goal_client.get("http://127.0.0.1:7735/goal/active")
            if res.status_code == 200 and isinstance(res.json(), dict):
                return str(res.json().get("name") or "")
        except Exception:
            pass
        return ""

    def _score_window(self, title: str, goal_name: str) -> float:
        if not title.strip() or not goal_name.strip():
            return 0.0
        a = {w for w in title.lower().split() if w}
        b = {w for w in goal_name.lower().split() if w}
        if not a or not b:
            return 0.0
        inter = len(a & b)
        if inter == 0:
            return 0.0
        # cosine-like normalized overlap
        denom = (len(a) * len(b)) ** 0.5
        return max(0.0, min(1.0, inter / denom))

    def _is_ignored_window(self, title: str) -> bool:
        t = title.lower()
        bad = ["eonix desktop", "tray", "panel", "eonix top bar", "eonix wallpaper"]
        return any(x in t for x in bad)

    def _scan_xlib_windows(self) -> list[EonixWindow]:  # pragma: no cover
        if self._xdisplay is None:
            return []
        out: list[EonixWindow] = []
        try:
            root = self._xdisplay.screen().root
            children = root.query_tree().children
            for win in children:
                attrs = win.get_attributes()
                if attrs.map_state != X.IsViewable:
                    continue
                title = str(win.get_wm_name() or "").strip()
                if not title or self._is_ignored_window(title):
                    continue
                geom = win.get_geometry()
                pid = 0
                try:
                    atom = self._xdisplay.intern_atom("_NET_WM_PID")
                    prop = win.get_full_property(atom, X.AnyPropertyType)
                    if prop and prop.value:
                        pid = int(prop.value[0])
                except Exception:
                    pid = 0
                out.append(
                    EonixWindow(
                        xid=int(win.id),
                        title=title,
                        pid=pid,
                        position=(int(geom.x), int(geom.y), int(geom.width), int(geom.height)),
                    )
                )
        except Exception:
            return []
        return out

    def scan_windows(self) -> list[EonixWindow]:
        if self.window_source is not None:
            windows = self.window_source()
        elif XLIB_AVAILABLE and self._xdisplay is not None:
            windows = self._scan_xlib_windows()
        else:
            windows = list(self.registry.values())

        goal_name = self._active_goal_name()
        new_registry: dict[int, EonixWindow] = {}
        for w in windows:
            if self._is_ignored_window(w.title):
                continue
            w.goal_score = self._score_window(w.title, goal_name)
            w.is_focused = bool(self._focused_xid == w.xid)
            new_registry[w.xid] = w
        self.registry = new_registry
        return list(self.registry.values())

    def register_virtual_window(self, title: str, pid: int = 0, position: tuple[int, int, int, int] = (0, 40, 800, 600)) -> int:
        xid = max(self.registry.keys(), default=1000) + 1
        self.registry[xid] = EonixWindow(xid=xid, title=title, pid=pid, position=position)
        return xid

    def focus(self, xid: int) -> None:
        if xid not in self.registry:
            return
        self._focused_xid = xid
        for key, w in self.registry.items():
            w.is_focused = key == xid
        try:
            self.context_client.post("http://127.0.0.1:7736/context/event", json={"type": "window_focus", "xid": xid})
        except Exception:
            pass

    def move(self, xid: int, x: int, y: int) -> None:
        if xid not in self.registry:
            return
        _, _, w, h = self.registry[xid].position
        self.registry[xid].position = (int(x), int(y), int(w), int(h))

    def resize(self, xid: int, w: int, h: int) -> None:
        if xid not in self.registry:
            return
        x, y, _, _ = self.registry[xid].position
        self.registry[xid].position = (int(x), int(y), int(w), int(h))

    def _calculate_snap_coords(
        self, zone: str, screen_width: Optional[int] = None, screen_height: Optional[int] = None
    ) -> tuple[int, int, int, int]:
        sw = int(screen_width or self.screen_size[0])
        sh = int(screen_height or self.screen_size[1])
        top = int(self.top_offset)
        bottom = max(0, int(self.bottom_offset))
        usable_h = max(1, sh - top - bottom)
        half_w = sw // 2
        half_h = usable_h // 2

        mapping = {
            "left": (0, top, half_w, usable_h),
            "right": (half_w, top, sw - half_w, usable_h),
            "top": (0, top, sw, half_h),
            "fullscreen": (0, top, sw, usable_h),
            "topleft": (0, top, half_w, half_h),
            "topright": (half_w, top, sw - half_w, half_h),
            "bottomleft": (0, top + half_h, half_w, usable_h - half_h),
            "bottomright": (half_w, top + half_h, sw - half_w, usable_h - half_h),
        }
        return mapping.get(zone, (0, top, sw, usable_h))

    def _snap_coords(self, zone: str) -> tuple[int, int, int, int]:
        return self._calculate_snap_coords(zone)

    def snap(self, xid: int, zone: str) -> None:
        if xid not in self.registry:
            return
        x, y, w, h = self._snap_coords(zone)
        self.move(xid, x, y)
        self.resize(xid, w, h)
        self.registry[xid].snap_zone = zone

    def close(self, xid: int) -> None:
        if xid in self.registry:
            self.registry.pop(xid)

    def register_hotkeys(self) -> dict[str, str]:
        self.hotkeys = {
            "Super+Left": "snap_left",
            "Super+Right": "snap_right",
            "Super+Up": "snap_fullscreen",
            "Super+Down": "unsnap",
            "Super+Tab": "focus_cycle_goal",
            "Alt+F4": "close",
        }
        return self.hotkeys

    def cycle_focus_by_goal_score(self) -> Optional[int]:
        ranked = self.get_goal_relevant_windows()
        if not ranked:
            return None
        self.focus(ranked[0].xid)
        return ranked[0].xid

    def get_goal_relevant_windows(self) -> list[EonixWindow]:
        return sorted(self.registry.values(), key=lambda x: x.goal_score, reverse=True)

    # ── GTK Window Hosting ──────────────────────────────────
    def open(self, title: str, content, x: int = 100, y: int = 80,
             w: int = 640, h: int = 420):
        """Open a new GTK window with custom Eonix chrome."""
        if not GTK_AVAILABLE:
            return None

        win = Gtk.Window()
        win.set_decorated(False)
        win.set_default_size(w, h)
        win.set_resizable(True)
        win.set_css_classes(["eonix-app-window"])

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # ── Custom titlebar ──
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        bar.set_css_classes(["eonix-titlebar"])
        bar.set_size_request(-1, 38)

        # Traffic light buttons
        btn_box = Gtk.Box(spacing=8)
        btn_box.set_valign(Gtk.Align.CENTER)
        btn_box.set_margin_start(14)
        for css_cls, symbol, action in [
            ("btn-close", "×", lambda *_: win.close()),
            ("btn-min",   "−", lambda *_: win.minimize()),
            ("btn-max",   "+", lambda *_: None),
        ]:
            btn = Gtk.Button(label=symbol)
            btn.set_css_classes(["traffic-btn", css_cls])
            btn.set_size_request(14, 14)
            btn.connect("clicked", action)
            btn_box.append(btn)
        bar.append(btn_box)

        spacer1 = Gtk.Box()
        spacer1.set_hexpand(True)
        bar.append(spacer1)

        lbl = Gtk.Label(label=title)
        lbl.set_css_classes(["eonix-window-title"])
        bar.append(lbl)

        spacer2 = Gtk.Box()
        spacer2.set_hexpand(True)
        bar.append(spacer2)

        # Drag support via motion controller
        drag = Gtk.GestureDrag()
        self._drag_start_x = 0
        self._drag_start_y = 0
        def _on_drag_begin(gesture, x, y):
            pass
        def _on_drag_update(gesture, off_x, off_y):
            pass
        drag.connect("drag-begin", _on_drag_begin)
        drag.connect("drag-update", _on_drag_update)
        bar.add_controller(drag)

        outer.append(bar)

        # ── Content ──
        if content is not None:
            content.set_vexpand(True)
            content.set_hexpand(True)
            outer.append(content)

        win.set_child(outer)

        # Open animation
        win.set_opacity(0.0)
        def _animate_open():
            t = getattr(win, '_anim_t', 0.0)
            t += 16 / 220.0
            if t >= 1.0:
                t = 1.0
                win.set_opacity(1.0)
                return False
            p = 1 - (1 - t) ** 3  # ease-out-cubic
            win.set_opacity(p)
            win._anim_t = t
            return True
        win._anim_t = 0.0
        GLib.timeout_add(16, _animate_open)

        win.present()

        # Register in window manager
        xid = self.register_virtual_window(title, position=(x, y, w, h))
        win._eonix_xid = xid
        return win


class EonixTaskbar:
    def __init__(self, wm: EonixWindowManager, headless: bool = True):
        self.wm = wm
        self.headless = headless
        self.buttons: list[str] = []
        self.window = _StubTaskbarWindow()
        if GTK_AVAILABLE and not headless:  # pragma: no cover
            self._build_ui()

    def _build_ui(self) -> None:  # pragma: no cover
        self.window = Gtk.Window(title="Eonix Taskbar")  # type: ignore
        self.window.set_default_size(1920, 36)
        self.container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)  # type: ignore
        self.window.set_child(self.container)
        GLib.timeout_add_seconds(2, self._refresh_tick)  # type: ignore

    def _refresh_tick(self) -> bool:  # pragma: no cover
        self.refresh()
        return True

    def refresh(self) -> list[str]:
        windows = self.wm.scan_windows()
        self.buttons = []
        for w in windows:
            txt = (w.title[:20] + "...") if len(w.title) > 20 else w.title
            if w.goal_score >= 0.3:
                txt = "● " + txt
            self.buttons.append(txt)
        return self.buttons

    def button_count(self) -> int:
        return len(self.buttons)


# ---------------------------
# Inline unit tests (pytest)
# ---------------------------


def test_scan_windows_returns_list():
    source = lambda: [EonixWindow(1, "VS Code", 11, (0, 40, 800, 600))]
    wm = EonixWindowManager(window_source=source)
    out = wm.scan_windows()
    assert isinstance(out, list)


def test_snap_left_calculates_correct_coords():
    wm = EonixWindowManager(screen_size=(1920, 1080), top_offset=40, bottom_offset=40)
    xid = wm.register_virtual_window("Editor")
    wm.snap(xid, "left")
    assert wm.registry[xid].position == (0, 40, 960, 1000)


def test_snap_right_calculates_correct_coords():
    wm = EonixWindowManager(screen_size=(1920, 1080), top_offset=40, bottom_offset=40)
    xid = wm.register_virtual_window("Editor")
    wm.snap(xid, "right")
    assert wm.registry[xid].position == (960, 40, 960, 1000)


def test_goal_score_sorts_windows_correctly():
    class FakeGoalClient:
        def get(self, _url):
            class Resp:
                status_code = 200

                @staticmethod
                def json():
                    return {"name": "Build Desktop"}

            return Resp()

    source = lambda: [
        EonixWindow(1, "Build Desktop docs", 1, (0, 40, 800, 600)),
        EonixWindow(2, "Random browser", 2, (0, 40, 800, 600)),
    ]
    wm = EonixWindowManager(window_source=source, goal_client=FakeGoalClient())
    wm.scan_windows()
    ranked = wm.get_goal_relevant_windows()
    assert ranked[0].xid == 1


def test_taskbar_button_count_matches_windows():
    source = lambda: [
        EonixWindow(1, "One", 1, (0, 40, 800, 600)),
        EonixWindow(2, "Two", 2, (0, 40, 800, 600)),
    ]
    wm = EonixWindowManager(window_source=source)
    taskbar = EonixTaskbar(wm, headless=True)
    taskbar.refresh()
    assert taskbar.button_count() == 2


def test_focus_updates_registry():
    wm = EonixWindowManager()
    a = wm.register_virtual_window("A")
    b = wm.register_virtual_window("B")
    wm.focus(b)
    assert wm.registry[b].is_focused is True
    assert wm.registry[a].is_focused is False


def test_move_updates_position():
    wm = EonixWindowManager()
    xid = wm.register_virtual_window("A")
    wm.move(xid, 12, 34)
    assert wm.registry[xid].position[:2] == (12, 34)


def test_close_removes_window():
    wm = EonixWindowManager()
    xid = wm.register_virtual_window("A")
    wm.close(xid)
    assert xid not in wm.registry