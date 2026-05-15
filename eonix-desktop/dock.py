"""Eonix Physics-Based Animated Dock.

Frosted glass pill with 7 app icons, spring-physics hover magnification,
bounce-on-click, running indicator dots, and tooltip overlays.
All animations at 60fps via 16ms GLib timer.
"""
from __future__ import annotations

import math
import os
from typing import Callable, Optional

GTK_AVAILABLE = False
try:
    import gi
    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk, GLib, Gdk  # type: ignore
    import cairo
    GTK_AVAILABLE = True
except Exception:
    Gtk = GLib = Gdk = None  # type: ignore
    cairo = None  # type: ignore

HEADLESS = not GTK_AVAILABLE or os.environ.get("EONIX_HEADLESS", "0") == "1" or not os.environ.get("DISPLAY")

# ── App definitions ─────────────────────────────────
APPS = [
    ("SH",  "EonixShell", "Terminal"),
    ("DIR", "Files",      "Files"),
    ("AIM", "Goals",      "Goals"),
    ("CFG", "Settings",   "Settings"),
    ("HUB", "Hub",        "Hub"),
    ("BOT", "MIND",       "MIND"),
    ("AI",  "AIChat",     "AI Chat"),
    ("PAD", "Notes",      "Notes"),
    ("SYS", "System",     "System"),
]

# ── Constants ───────────────────────────────────────
SZ = 56         # base icon size px
GAP = 10        # gap between icons
H_SCALE = 1.45  # hover scale
N_SCALE = 1.20  # neighbor scale
A_SPEED = 0.16  # animation lerp speed
B_AMP = 18      # bounce amplitude px


class Icon:
    """Single dock icon with animation state."""

    __slots__ = ("emoji", "name", "cmd", "scale", "target",
                 "by", "bph", "active", "running")

    def __init__(self, emoji: str, name: str, cmd: str = "") -> None:
        self.emoji = emoji
        self.name = name
        self.cmd = cmd
        self.scale: float = 1.0
        self.target: float = 1.0
        self.by: float = 0.0       # bounce y offset
        self.bph: float = 0.0      # bounce phase
        self.active: bool = False   # currently bouncing?
        self.running: bool = False  # app is running?

    def tick(self) -> bool:
        """Advance one animation frame. Returns True if visual changed."""
        dirty = False
        d = self.target - self.scale
        if abs(d) > 0.004:
            self.scale += d * A_SPEED
            dirty = True
        else:
            self.scale = self.target
        if self.active:
            self.bph += 0.22
            fade = max(0.0, 1.0 - self.bph / math.pi)
            self.by = math.sin(self.bph) * B_AMP * fade
            if self.bph >= math.pi:
                self.active = False
                self.by = 0.0
            dirty = True
        return dirty

    def launch(self) -> None:
        """Trigger bounce animation and mark as running."""
        self.active = True
        self.bph = 0.0
        self.running = True


class _StubDock:
    """Headless dock stub for testing."""

    def __init__(self, on_launch: Optional[Callable] = None) -> None:
        self.icons = [Icon(e, n, c) for e, n, c in APPS]
        self.hovered = -1
        self.on_launch = on_launch
        self.visible = False

    def set_hexpand(self, *_a) -> None:
        pass

    def set_size_request(self, *_a) -> None:
        pass

    def launch_app(self, index: int) -> None:
        if 0 <= index < len(self.icons):
            self.icons[index].launch()
            if self.on_launch:
                self.on_launch(self.icons[index].name)


if GTK_AVAILABLE and not HEADLESS:

    class EonixDock(Gtk.DrawingArea):
        """Full GTK4 physics-based dock widget."""

        H = 110  # widget height (room for hover tooltip above pill)

        def __init__(self, on_launch: Optional[Callable] = None) -> None:
            super().__init__()
            self.icons = [Icon(e, n, c) for e, n, c in APPS]
            self.hovered: int = -1
            self.on_launch = on_launch
            self.set_size_request(-1, self.H)
            self.set_hexpand(True)
            self.set_draw_func(self._draw)

            # Motion tracking
            motion = Gtk.EventControllerMotion()
            motion.connect("motion", self._motion)
            motion.connect("leave", self._leave)
            self.add_controller(motion)

            # Click handling
            click = Gtk.GestureClick()
            click.connect("pressed", self._click)
            self.add_controller(click)

            GLib.timeout_add(80, self._tick)  # 12fps — CPU friendly

        def _icon_x(self, i: int, w: int) -> float:
            total = len(self.icons) * (SZ + GAP) - GAP
            return (w - total) / 2.0 + i * (SZ + GAP)

        def _motion(self, _ctrl, mx: float, _my: float) -> None:
            w = self.get_width()
            prev = self.hovered
            self.hovered = -1
            for i in range(len(self.icons)):
                cx = self._icon_x(i, w) + SZ / 2.0
                if abs(mx - cx) < (SZ + GAP) / 2.0:
                    self.hovered = i
                    break
            for i, ic in enumerate(self.icons):
                diff = abs(i - self.hovered) if self.hovered >= 0 else 99
                if diff == 0:
                    ic.target = H_SCALE
                elif diff == 1:
                    ic.target = N_SCALE
                else:
                    ic.target = 1.0
            if prev != self.hovered:
                self.queue_draw()

        def _leave(self, *_args) -> None:
            self.hovered = -1
            for ic in self.icons:
                ic.target = 1.0

        def _click(self, _gesture, _n: int, x: float, _y: float) -> None:
            w = self.get_width()
            for i, ic in enumerate(self.icons):
                if abs(x - (self._icon_x(i, w) + SZ / 2.0)) < (SZ + GAP) / 2.0:
                    ic.launch()
                    # All app launching handled via on_launch callback only
                    if self.on_launch:
                        self.on_launch(ic.name)
                    break

        def _tick(self) -> bool:
            if any(ic.tick() for ic in self.icons):
                self.queue_draw()
            return True

        def _rrect(self, cr, x: float, y: float, w: float, h: float, r: float) -> None:
            """Draw a rounded rectangle path."""
            cr.new_sub_path()
            cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
            cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
            cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
            cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
            cr.close_path()

        def _draw(self, _area, cr, w: int, h: int) -> None:
            n = len(self.icons)
            bw = n * (SZ + GAP) - GAP + 40
            bh = SZ + 20
            bx = (w - bw) / 2.0
            by = h - bh - 8

            # ── Frosted glass pill background ────────
            cr.set_source_rgba(1, 1, 1, 0.18)
            self._rrect(cr, bx, by, bw, bh, 22)
            cr.fill()

            # ── Pill border ──────────────────────────
            cr.set_source_rgba(1, 1, 1, 0.25)
            self._rrect(cr, bx, by, bw, bh, 22)
            cr.set_line_width(1)
            cr.stroke()

            # ── Violet accent line above dock ────────
            cr.set_source_rgba(0.48, 0.30, 1.0, 0.3)
            cr.set_line_width(1)
            cr.move_to(bx + 20, by)
            cr.line_to(bx + bw - 20, by)
            cr.stroke()

            for i, ic in enumerate(self.icons):
                s = ic.scale
                sz = SZ * s
                ix = self._icon_x(i, w)
                ox = ix + (SZ - sz) / 2.0
                oy = h - SZ - 14 + (SZ - sz) / 2.0 - ic.by

                # ── Icon background glow ─────────────
                if i == self.hovered:
                    cr.set_source_rgba(0.48, 0.30, 1.0, 0.28)
                else:
                    cr.set_source_rgba(1, 1, 1, 0.06)
                self._rrect(cr, ox, oy, sz, sz, 14 * s)
                cr.fill()

                # ── ASCII label (color-coded per app) ─
                _LABEL_COLORS = {
                    "SH": (0.31,0.98,0.48), "DIR": (0.55,0.91,0.99),
                    "AIM": (0.74,0.58,0.97), "CFG": (1.0,0.72,0.42),
                    "HUB": (1.0,0.47,0.78), "BOT": (0.65,0.55,0.98),
                    "AI": (0.31,0.98,0.48), "PAD": (0.95,0.98,0.55),
                    "SYS": (1.0,0.33,0.33),
                }
                _r, _g, _b = _LABEL_COLORS.get(ic.emoji, (1,1,1))
                cr.set_source_rgba(_r, _g, _b, 0.92)
                cr.select_font_face("Sans", 0, 1)  # bold
                cr.set_font_size(sz * 0.28)
                te = cr.text_extents(ic.emoji)
                cr.move_to(
                    ox + (sz - te.width) / 2 - te.x_bearing,
                    oy + (sz + te.height) / 2 - te.y_bearing - te.height * 0.1,
                )
                cr.show_text(ic.emoji)

                # ── Running indicator dot ────────────
                if ic.running:
                    cr.set_source_rgba(0.48, 0.30, 1.0, 0.9)
                    cr.arc(ix + SZ / 2.0, h - 5, 3, 0, 2 * math.pi)
                    cr.fill()

                # ── Hover tooltip ────────────────────
                if i == self.hovered:
                    cr.select_font_face("Inter", 0, 0)
                    cr.set_font_size(12)
                    te2 = cr.text_extents(ic.name)
                    tx = ix + SZ / 2.0 - te2.width / 2.0
                    # Draw ABOVE the pill background
                    ty = by - 12
                    # tooltip background pill
                    tw = te2.width + 20
                    cr.set_source_rgba(10 / 255, 10 / 255, 26 / 255, 0.94)
                    self._rrect(cr, tx - 10, ty - 18, tw, 24, 8)
                    cr.fill()
                    # tooltip border
                    cr.set_source_rgba(0.48, 0.30, 1.0, 0.3)
                    self._rrect(cr, tx - 10, ty - 18, tw, 24, 8)
                    cr.set_line_width(1)
                    cr.stroke()
                    # tooltip text
                    cr.set_source_rgba(0.88, 0.88, 1.0, 0.95)
                    cr.move_to(tx, ty)
                    cr.show_text(ic.name)

else:
    # Headless fallback
    EonixDock = _StubDock  # type: ignore[misc,assignment]


# ── Inline tests ─────────────────────────────────────
def test_icon_tick_converges():
    ic = Icon("⚡", "Test")
    ic.target = 1.45
    for _ in range(200):
        ic.tick()
    assert abs(ic.scale - 1.45) < 0.01


def test_icon_bounce_completes():
    ic = Icon("📁", "Files")
    ic.launch()
    assert ic.active is True
    assert ic.running is True
    for _ in range(200):
        ic.tick()
    assert ic.active is False
    assert ic.by == 0.0


def test_stub_dock_launch():
    launched = []
    dock = _StubDock(on_launch=lambda name: launched.append(name))
    dock.launch_app(0)
    assert len(launched) == 1
    assert launched[0] == "EonixShell"


def test_apps_list_has_nine_entries():
    assert len(APPS) == 9


def test_icon_initial_state():
    ic = Icon("🧠", "Goals")
    assert ic.scale == 1.0
    assert ic.active is False
    assert ic.running is False
