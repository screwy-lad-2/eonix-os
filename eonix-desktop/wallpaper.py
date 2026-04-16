"""Eonix AI Neural Particle Wallpaper — reactive to system state.

Renders 80 particles connected by lines (neural network visualization)
that responds to 4 states: IDLE, ACTIVE, THINKING, RETRAIN.
Uses GTK4 DrawingArea + Cairo for hardware-accelerated rendering.
"""
from __future__ import annotations

import math
import os
import random
from typing import Optional

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

# ── States ──────────────────────────────────────────
IDLE = "idle"
ACTIVE = "active"
THINKING = "thinking"
RETRAIN = "retrain"

# ── Color palettes per state ────────────────────────
STATE_COLORS = {
    IDLE:     (0.48, 0.30, 1.00),   # soft violet
    ACTIVE:   (0.30, 0.80, 1.00),   # cyan-violet
    THINKING: (0.60, 0.20, 1.00),   # deep purple
    RETRAIN:  (0.90, 0.55, 0.10),   # orange-gold
}

STATE_SPEEDS = {
    IDLE:     1.0,
    ACTIVE:   2.2,
    THINKING: 1.5,
    RETRAIN:  1.8,
}


class Particle:
    """A single drifting particle with position, velocity, radius, and alpha."""

    __slots__ = ("x", "y", "vx", "vy", "r", "a")

    def __init__(self, w: float, h: float):
        self.reset(w, h)

    def reset(self, w: float, h: float) -> None:
        self.x = random.uniform(0, w)
        self.y = random.uniform(0, h)
        speed = random.uniform(0.15, 0.45)
        angle = random.uniform(0, 2 * math.pi)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.r = random.uniform(1.5, 3.2)
        self.a = random.uniform(0.35, 0.75)

    def update(self, w: float, h: float, speed_mult: float = 1.0) -> None:
        self.x += self.vx * speed_mult
        self.y += self.vy * speed_mult
        if self.x < 0:
            self.x = w
        elif self.x > w:
            self.x = 0
        if self.y < 0:
            self.y = h
        elif self.y > h:
            self.y = 0


class _StubWallpaper:
    """Headless stub for testing without GTK."""

    def __init__(self) -> None:
        self.state = IDLE
        self.particles: list[Particle] = []

    def set_state(self, state: str) -> None:
        self.state = state


if GTK_AVAILABLE and not HEADLESS:

    class EonixWallpaper(Gtk.DrawingArea):
        """Full GTK4 neural particle wallpaper."""

        CONNECT_DIST = 130
        N_PARTICLES = 80

        def __init__(self) -> None:
            super().__init__()
            self.w: float = 1920
            self.h: float = 1080
            self.state: str = IDLE
            self.pulse_r: float = 0.0
            self.pulse_alpha: float = 0.0
            self.pulse_on: bool = False
            self.retrain_x: float = 0.0
            self.retrain_on: bool = False
            self.breathe: float = 0.0
            self.breathe_dir: int = 1
            self.particles: list[Particle] = []
            self.set_draw_func(self._draw)
            self.connect("realize", self._on_realize)

        def _on_realize(self, *_args) -> None:
            alloc = self.get_allocation()
            self.w = alloc.width or 1920
            self.h = alloc.height or 1080
            self.particles = [Particle(self.w, self.h) for _ in range(self.N_PARTICLES)]
            GLib.timeout_add(33, self._tick)  # ~30fps

        def set_state(self, state: str) -> None:
            """Change wallpaper state — triggers visual reactions."""
            self.state = state
            if state == THINKING:
                self.pulse_r = 0.0
                self.pulse_alpha = 0.8
                self.pulse_on = True
            elif state == RETRAIN:
                self.retrain_x = 0.0
                self.retrain_on = True

        def _tick(self) -> bool:
            speed = STATE_SPEEDS.get(self.state, 1.0)
            for p in self.particles:
                p.update(self.w, self.h, speed)

            # Breathing pulse
            self.breathe += 0.006 * self.breathe_dir
            if self.breathe >= 1.0:
                self.breathe_dir = -1
            if self.breathe <= 0.0:
                self.breathe_dir = 1

            # Thinking ripple
            if self.pulse_on:
                self.pulse_r += 8.0
                self.pulse_alpha -= 0.012
                if self.pulse_alpha <= 0:
                    self.pulse_on = False
                    self.state = IDLE

            # Retrain sweep
            if self.retrain_on:
                self.retrain_x += self.w / 80
                if self.retrain_x > self.w * 1.2:
                    self.retrain_on = False
                    self.state = IDLE

            self.queue_draw()
            return True

        def _draw(self, _area, cr, w: int, h: int) -> None:
            self.w, self.h = float(w), float(h)
            b = self.breathe
            s = self.state
            rc, gc, bc = STATE_COLORS.get(s, STATE_COLORS[IDLE])

            # ── Background gradient ──────────────────────
            if s == RETRAIN:
                t = min(1.0, self.retrain_x / w) if w > 0 else 0
                cr.set_source_rgb(0.05 + t * 0.10, 0.03 + t * 0.04, 0.10 + t * 0.02)
            else:
                cr.set_source_rgb(0.05, 0.03, 0.10)
            cr.paint()

            # ── Retrain sweep wave ───────────────────────
            if self.retrain_on:
                rx = self.retrain_x
                sweep = cairo.LinearGradient(rx - 120, 0, rx + 80, 0)
                sweep.add_color_stop_rgba(0, 0.9, 0.6, 0, 0)
                sweep.add_color_stop_rgba(0.5, 0.9, 0.55, 0.1, 0.18)
                sweep.add_color_stop_rgba(1, 0.9, 0.6, 0, 0)
                cr.set_source(sweep)
                cr.rectangle(rx - 120, 0, 200, h)
                cr.fill()

            # ── Thinking ripple ──────────────────────────
            if self.pulse_on and self.pulse_alpha > 0:
                cx, cy = w / 2.0, h / 2.0
                ring = cairo.RadialGradient(cx, cy, max(0, self.pulse_r - 20), cx, cy, self.pulse_r)
                ring.add_color_stop_rgba(0, 0.48, 0.30, 1.0, 0)
                ring.add_color_stop_rgba(0.7, 0.48, 0.30, 1.0, self.pulse_alpha * 0.6)
                ring.add_color_stop_rgba(1, 0.48, 0.30, 1.0, 0)
                cr.set_source(ring)
                cr.arc(cx, cy, self.pulse_r, 0, 2 * math.pi)
                cr.fill()

            # ── Connection lines ─────────────────────────
            glow = 0.55 + b * 0.45
            cd2 = self.CONNECT_DIST * self.CONNECT_DIST
            parts = self.particles
            n = len(parts)
            for i in range(n):
                ai = parts[i]
                for j in range(i + 1, n):
                    aj = parts[j]
                    dx = ai.x - aj.x
                    dy = ai.y - aj.y
                    d2 = dx * dx + dy * dy
                    if d2 < cd2:
                        d = math.sqrt(d2)
                        st = 1.0 - d / self.CONNECT_DIST
                        alp = st * 0.38 * glow
                        cr.set_source_rgba(rc, gc, bc, alp)
                        cr.set_line_width(0.9 * st)
                        cr.move_to(ai.x, ai.y)
                        cr.line_to(aj.x, aj.y)
                        cr.stroke()

            # ── Particles ────────────────────────────────
            for p in parts:
                cr.set_source_rgba(min(1.0, rc + 0.15), gc, bc, p.a * glow)
                cr.arc(p.x, p.y, p.r, 0, 2 * math.pi)
                cr.fill()

            # ── Center ambient glow ──────────────────────
            cx, cy = w / 2.0, h / 2.0
            rg = cairo.RadialGradient(cx, cy, 0, cx, cy, w * 0.38)
            rg.add_color_stop_rgba(0, rc * 0.6, gc * 0.3, bc, 0.07 + b * 0.06)
            rg.add_color_stop_rgba(1, 0, 0, 0, 0)
            cr.set_source(rg)
            cr.paint()

else:
    # Headless fallback
    EonixWallpaper = _StubWallpaper  # type: ignore[misc,assignment]


# ── Inline tests ─────────────────────────────────────
def test_wallpaper_states_exist():
    assert IDLE == "idle"
    assert ACTIVE == "active"
    assert THINKING == "thinking"
    assert RETRAIN == "retrain"


def test_particle_wraps_around():
    p = Particle(100, 100)
    p.x = 101
    p.y = -1
    p.vx = 1
    p.vy = -1
    p.update(100, 100)
    assert 0 <= p.x <= 100
    assert 0 <= p.y <= 100


def test_stub_wallpaper_set_state():
    wp = _StubWallpaper()
    wp.set_state(THINKING)
    assert wp.state == THINKING


def test_state_colors_defined():
    for s in [IDLE, ACTIVE, THINKING, RETRAIN]:
        assert s in STATE_COLORS
        assert len(STATE_COLORS[s]) == 3


def test_state_speeds_defined():
    for s in [IDLE, ACTIVE, THINKING, RETRAIN]:
        assert s in STATE_SPEEDS
        assert STATE_SPEEDS[s] > 0
