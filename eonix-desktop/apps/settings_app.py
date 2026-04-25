"""Eonix Settings — KDE-inspired deep settings panel with live controls.

Five categories: Appearance, AI & Agents, Display, Privacy, About.
All settings persist to ~/.config/eonix/settings.json and are
readable/writable by the MIND AI agent (Iron Man mode).
"""
import gi
import os
import json

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib


class EonixSettings(Gtk.Box):
    CONFIG_PATH = os.path.expanduser("~/.config/eonix/settings.json")

    SECTIONS = [
        ("🎨", "Appearance"),
        ("🤖", "AI & Agents"),
        ("🖥️", "Display"),
        ("🔒", "Privacy"),
        ("👤", "About"),
    ]

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.set_vexpand(True)
        self.set_hexpand(True)
        self.set_css_classes(["eonix-settings-root"])
        self._apply_dark_fallback()

        self.config = self._load_config()

        # Sidebar
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        sidebar.set_css_classes(["settings-sidebar"])
        sidebar.set_margin_top(16)
        sidebar.set_margin_bottom(16)
        sidebar.set_margin_start(8)
        sidebar.set_margin_end(8)
        sidebar.set_size_request(190, -1)

        self._nav_btns = {}
        for icon, label in self.SECTIONS:
            btn = Gtk.Button(label=f"{icon}  {label}")
            btn.set_css_classes(["settings-nav-btn"])
            btn.set_halign(Gtk.Align.FILL)
            btn.connect("clicked", lambda _, l=label: self._switch_section(l))
            sidebar.append(btn)
            self._nav_btns[label] = btn
        self.append(sidebar)

        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        self.append(sep)

        # Content area
        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._content.set_vexpand(True)
        self._content.set_hexpand(True)
        self._content.set_css_classes(["settings-content"])
        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self._content)
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)
        self.append(scroll)

        self._switch_section("About")

    # ── Config persistence ──────────────────────

    def _load_config(self):
        os.makedirs(os.path.dirname(self.CONFIG_PATH), exist_ok=True)
        if os.path.exists(self.CONFIG_PATH):
            try:
                with open(self.CONFIG_PATH, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "accent_color": "#7c4dff",
            "wallpaper_brightness": 1.0,
            "font_scale": 1.0,
            "dark_mode": True,
            "ai_enabled": True,
            "ai_model": "LightGBM v1.2",
            "privacy_telemetry": False,
            "privacy_crash_reports": True,
            "display_scaling": 1.0,
        }

    def _save_config(self):
        try:
            with open(self.CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            print(f"[SETTINGS] Save failed: {e}")

    def _set(self, key, value):
        self.config[key] = value
        self._save_config()
        self._apply_live(key, value)
        print(f"[SETTINGS] {key} = {value}")

    def _apply_live(self, key, value):
        """Apply setting change immediately to the running desktop."""
        try:
            display = Gdk.Display.get_default()
            gs = Gtk.Settings.get_default()
            if not gs:
                return

            if key == "font_scale":
                size = max(8, int(10 * float(value)))
                gs.set_property("gtk-font-name", f"Sans {size}")

            elif key == "dark_mode":
                gs.set_property(
                    "gtk-application-prefer-dark-theme", bool(value))

            elif key == "accent_color" and display:
                css = f"""
                .active-section {{
                    background: {value}33;
                    border-left: 3px solid {value};
                }}
                """.encode()
                provider = Gtk.CssProvider()
                provider.load_from_data(css)
                Gtk.StyleContext.add_provider_for_display(
                    display, provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_USER)

            elif key == "wallpaper_brightness":
                bf = os.path.expanduser("~/.config/eonix/wp_brightness")
                os.makedirs(os.path.dirname(bf), exist_ok=True)
                with open(bf, "w") as f:
                    f.write(str(value))
        except Exception as e:
            print(f"[SETTINGS] live apply failed: {e}")

    # ── Navigation ──────────────────────────────

    def _switch_section(self, name):
        for lbl, btn in self._nav_btns.items():
            if lbl == name:
                btn.set_css_classes(["settings-nav-btn", "active-section"])
            else:
                btn.set_css_classes(["settings-nav-btn"])
        dispatch = {
            "Appearance": self._show_appearance,
            "AI & Agents": self._show_ai,
            "Display": self._show_display,
            "Privacy": self._show_privacy,
            "About": self._show_about,
        }
        fn = dispatch.get(name, self._show_about)
        fn()

    def _clear(self):
        child = self._content.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._content.remove(child)
            child = nxt

    # ── UI helpers ──────────────────────────────

    def _title(self, text):
        lbl = Gtk.Label(label=text)
        lbl.set_css_classes(["section-title"])
        lbl.set_halign(Gtk.Align.START)
        lbl.set_margin_start(20)
        lbl.set_margin_top(16)
        lbl.set_margin_bottom(12)
        return lbl

    def _row(self, key_text, widget):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.set_css_classes(["settings-row"])
        row.set_margin_start(16)
        row.set_margin_end(16)
        row.set_margin_bottom(6)
        row.set_hexpand(True)
        key = Gtk.Label(label=key_text)
        key.set_css_classes(["settings-key"])
        key.set_hexpand(True)
        key.set_halign(Gtk.Align.START)
        row.append(key)
        row.append(widget)
        return row

    # ── Sections ────────────────────────────────

    def _show_appearance(self):
        self._clear()
        self._content.append(self._title("🎨 Appearance"))

        # Dark mode toggle
        sw = Gtk.Switch()
        sw.set_active(self.config.get("dark_mode", True))
        sw.connect("notify::active",
                   lambda s, _: self._set("dark_mode", s.get_active()))
        self._content.append(self._row("Dark Mode", sw))

        # Font scale slider
        adj = Gtk.Adjustment(
            value=self.config.get("font_scale", 1.0),
            lower=0.8, upper=1.4, step_increment=0.05)
        slider = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj)
        slider.set_size_request(160, -1)
        slider.set_digits(2)
        slider.connect("value-changed",
                       lambda s: self._set("font_scale", round(s.get_value(), 2)))
        self._content.append(self._row("Font Scale", slider))

        # Wallpaper brightness
        adj2 = Gtk.Adjustment(
            value=self.config.get("wallpaper_brightness", 1.0),
            lower=0.2, upper=1.0, step_increment=0.05)
        slider2 = Gtk.Scale(
            orientation=Gtk.Orientation.HORIZONTAL, adjustment=adj2)
        slider2.set_size_request(160, -1)
        slider2.set_digits(2)
        slider2.connect("value-changed",
                        lambda s: self._set("wallpaper_brightness", round(s.get_value(), 2)))
        self._content.append(self._row("Wallpaper Brightness", slider2))

        # Accent color picker
        color_btn = Gtk.ColorButton()
        rgba = Gdk.RGBA()
        rgba.parse(self.config.get("accent_color", "#7c4dff"))
        color_btn.set_rgba(rgba)
        color_btn.connect("color-set",
                          lambda b: self._set("accent_color", b.get_rgba().to_string()))
        self._content.append(self._row("Accent Color", color_btn))

    def _show_ai(self):
        self._clear()
        self._content.append(self._title("🤖 AI & Agents"))

        # AI enabled toggle
        sw = Gtk.Switch()
        sw.set_active(self.config.get("ai_enabled", True))
        sw.connect("notify::active",
                   lambda s, _: self._set("ai_enabled", s.get_active()))
        self._content.append(self._row("AI Assistant", sw))

        # Read-only AI stats
        for k, v in [
            ("Model", "LightGBM v1.2"),
            ("Accuracy", "63.47%"),
            ("Hub", "localhost:7750"),
            ("GoalEngine", "localhost:7735"),
            ("Agents", "5 connected"),
            ("Brain DB", "Connected"),
        ]:
            lbl = Gtk.Label(label=v)
            lbl.set_css_classes(["settings-val"])
            if v in ("Connected",):
                lbl.set_css_classes(["settings-val", "mind-online"])
            self._content.append(self._row(k, lbl))

    def _show_display(self):
        self._clear()
        self._content.append(self._title("🖥️ Display"))

        # Display scaling dropdown
        combo = Gtk.ComboBoxText()
        for opt in ["1x (100%)", "1.25x (125%)", "1.5x (150%)", "2x (200%)"]:
            combo.append_text(opt)
        combo.set_active(0)
        self._content.append(self._row("Display Scaling", combo))

        # Resolution (read-only)
        try:
            import subprocess as _sp
            res = _sp.check_output(
                ["xrandr", "--current"], text=True, timeout=2)
            resolution = "Unknown"
            for line in res.splitlines():
                if "*" in line:
                    resolution = line.split()[0]
                    break
        except Exception:
            resolution = "1280×800"
        lbl = Gtk.Label(label=resolution)
        lbl.set_css_classes(["settings-val"])
        self._content.append(self._row("Resolution", lbl))

    def _show_privacy(self):
        self._clear()
        self._content.append(self._title("🔒 Privacy"))

        for key, label, default in [
            ("privacy_telemetry", "Send Telemetry", False),
            ("privacy_crash_reports", "Crash Reports", True),
        ]:
            sw = Gtk.Switch()
            sw.set_active(self.config.get(key, default))
            sw.connect("notify::active",
                       lambda s, _, k=key: self._set(k, s.get_active()))
            self._content.append(self._row(label, sw))

    def _show_about(self):
        self._clear()
        self._content.append(self._title("👤 About"))
        for k, v in [
            ("Version", "v1.5.0-dev"),
            ("Desktop", "Eonix Aura"),
            ("AI Core", "MIND v1.2"),
            ("Accuracy", "63.47%"),
            ("Tests", "222+ passing"),
            ("Boot time", "~30 seconds"),
            ("RAM idle", "~1.2 GB"),
            ("Built by", "Shahnoor"),
            ("Started", "July 2025"),
            ("Release", "v1.0.0 May 2026"),
        ]:
            lbl = Gtk.Label(label=v)
            lbl.set_css_classes(["settings-val"])
            self._content.append(self._row(k, lbl))

    # ── Dark CSS fallback ───────────────────────

    def _apply_dark_fallback(self):
        """Inline CSS fallback for dark theme."""
        css = b"""
        .eonix-settings-root {
          background-color: #0d0d1a;
          color: #e0e0e0;
        }
        .settings-sidebar {
          background-color: #0a0a16;
          border-right: 1px solid rgba(124,77,255,0.15);
        }
        .settings-nav-btn {
          background: transparent;
          color: #a0a0c0;
          border: none;
          padding: 10px 14px;
          border-radius: 8px;
          font-weight: 500;
        }
        .settings-nav-btn:hover {
          background: rgba(124,77,255,0.2);
          color: #e0e0e0;
        }
        .active-section {
          background: rgba(124,77,255,0.25);
          color: #ffffff;
          font-weight: 700;
        }
        .settings-content {
          background: transparent;
          padding: 20px 24px;
        }
        .settings-row {
          background-color: rgba(255,255,255,0.04);
          border-radius: 10px;
          padding: 10px 14px;
          margin-bottom: 6px;
        }
        .settings-row:hover {
          background: rgba(124,77,255,0.08);
        }
        .settings-key {
          color: #888aa0;
          font-size: 13px;
        }
        .settings-val {
          color: #e0e0e0;
          font-size: 13px;
          font-weight: 600;
        }
        .section-title {
          font-size: 18px;
          font-weight: 700;
          color: #a78bfa;
          margin-bottom: 12px;
        }
        """
        try:
            provider = Gtk.CssProvider()
            provider.load_from_data(css)
            display = Gdk.Display.get_default()
            if display:
                Gtk.StyleContext.add_provider_for_display(
                    display, provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        except Exception as e:
            print(f"[SETTINGS] CSS fallback failed: {e}")
