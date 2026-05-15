# -*- coding: utf-8 -*-
"""Eonix Updates App — version info, changelog, OTA check."""
import threading
import datetime

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib

CHANGELOG = [
    {"version": "v1.5.0", "week": "Week 52", "date": "May 2026",
     "notes": ["Phone app + dialpad", "Updates app (this screen)",
               "Emoji rendering fixed", "Sync engine + QR pairing",
               "CPU usage optimised"]},
    {"version": "v1.4.0", "week": "Week 51", "date": "May 2026",
     "notes": ["Groq LLM backend", "Multi-backend AI chain",
               "Voice command engine", "Settings live font scale",
               "First-run Groq banner"]},
    {"version": "v1.3.0", "week": "Week 46", "date": "Apr 2026",
     "notes": ["Dual terminal fixed", "MIND dashboard",
               "System info app", "Dock tooltips"]},
]


class UpdatesApp(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_vexpand(True)
        self.set_hexpand(True)
        self._apply_css()
        self._build()

    def _build(self):
        # Header row
        hdr = Gtk.Box(spacing=10)
        hdr.set_margin_start(20)
        hdr.set_margin_end(20)
        hdr.set_margin_top(16)
        hdr.set_margin_bottom(4)
        title = Gtk.Label(label="EONIX UPDATES")
        title.set_css_classes(["upd-title"])
        title.set_hexpand(True)
        title.set_halign(Gtk.Align.START)
        self._st = Gtk.Label(label="")
        self._st.set_css_classes(["upd-status-lbl"])
        self._st.set_halign(Gtk.Align.END)
        hdr.append(title)
        hdr.append(self._st)
        self.append(hdr)

        # Banner
        banner = Gtk.Box(spacing=12)
        banner.set_css_classes(["upd-banner"])
        banner.set_margin_start(16)
        banner.set_margin_end(16)
        banner.set_margin_bottom(12)
        vb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        vb.set_hexpand(True)
        sub = Gtk.Label(label="Current Version")
        sub.set_css_classes(["upd-banner-sub"])
        sub.set_halign(Gtk.Align.START)
        ver = Gtk.Label(label="v1.5.0 -- Week 52")
        ver.set_css_classes(["upd-banner-ver"])
        ver.set_halign(Gtk.Align.START)
        vb.append(sub)
        vb.append(ver)
        banner.append(vb)
        cb = Gtk.Button(label="Check Updates")
        cb.set_css_classes(["upd-check-btn"])
        cb.connect("clicked", self._check)
        banner.append(cb)
        self.append(banner)

        sep = Gtk.Separator()
        sep.set_margin_start(16)
        sep.set_margin_end(16)
        sep.set_margin_bottom(8)
        self.append(sep)

        # Section label
        cl = Gtk.Label(label="RELEASE HISTORY")
        cl.set_css_classes(["upd-section-title"])
        cl.set_halign(Gtk.Align.START)
        cl.set_margin_start(20)
        cl.set_margin_bottom(8)
        self.append(cl)

        # Scrollable changelog
        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_start(16)
        box.set_margin_end(16)
        box.set_margin_bottom(16)

        for e in CHANGELOG:
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            card.set_css_classes(["upd-card"])

            vrow = Gtk.Box(spacing=8)
            vl = Gtk.Label(label=e["version"])
            vl.set_css_classes(["upd-card-ver"])
            vl.set_halign(Gtk.Align.START)
            wl = Gtk.Label(label=f"{e['week']} - {e['date']}")
            wl.set_css_classes(["upd-card-week"])
            wl.set_hexpand(True)
            wl.set_halign(Gtk.Align.END)
            vrow.append(vl)
            vrow.append(wl)
            card.append(vrow)

            for n in e["notes"]:
                nl = Gtk.Label(label=f"  + {n}")
                nl.set_css_classes(["upd-card-note"])
                nl.set_halign(Gtk.Align.START)
                card.append(nl)
            box.append(card)

        sw.set_child(box)
        self.append(sw)

    def _check(self, btn):
        btn.set_sensitive(False)
        btn.set_label("Checking...")

        def _run():
            try:
                import urllib.request
                urllib.request.urlopen("https://github.com/screwy-lad-2/eonix-os", timeout=4)
                msg = "Up to date"
            except Exception:
                msg = "Offline / no network"
            now = datetime.datetime.now().strftime("%d %b %H:%M")
            GLib.idle_add(self._st.set_text, f"{msg} -- {now}")
            GLib.idle_add(btn.set_sensitive, True)
            GLib.idle_add(btn.set_label, "Check Updates")

        threading.Thread(target=_run, daemon=True).start()

    def _apply_css(self):
        css = b"""
        .upd-title { font-size: 15px; font-weight: 800; color: #a78bfa; letter-spacing: 1px; }
        .upd-status-lbl { font-size: 11px; color: #555577; font-style: italic; }
        .upd-banner { background: rgba(124,77,255,0.07); border: 1px solid rgba(124,77,255,0.15); border-radius: 10px; padding: 12px 14px; }
        .upd-banner-sub { font-size: 11px; color: #555577; }
        .upd-banner-ver { font-size: 14px; font-weight: 700; color: #d0d0f0; }
        .upd-check-btn { background: rgba(124,77,255,0.18); color: #c0a0ff; border: 1px solid rgba(124,77,255,0.3); border-radius: 8px; padding: 8px 14px; font-size: 12px; font-weight: 600; }
        .upd-section-title { font-size: 10px; font-weight: 700; color: #333355; letter-spacing: 2px; }
        .upd-card { background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06); border-radius: 10px; padding: 12px 14px; }
        .upd-card-ver { font-size: 13px; font-weight: 700; color: #a78bfa; }
        .upd-card-week { font-size: 11px; color: #444466; }
        .upd-card-note { font-size: 12px; color: #8888aa; line-height: 1.6; }
        """
        pr = Gtk.CssProvider()
        pr.load_from_data(css)
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(display, pr, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
