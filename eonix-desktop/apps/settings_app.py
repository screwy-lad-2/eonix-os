import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk
import subprocess, json, os

class EonixSettings(Gtk.Box):
    SECTIONS = [
        ("🎨", "Appearance"),
        ("🤖", "AI & Model"),
        ("📡", "Network"),
        ("🔔", "Notifications"),
        ("ℹ️",  "About"),
    ]

    def __init__(self):
        super().__init__(
            orientation=Gtk.Orientation.HORIZONTAL)
        self.set_css_classes(["eonix-settings-root"])
        self.set_vexpand(True)
        self.set_hexpand(True)
        self._apply_dark_fallback()

        # Sidebar
        sidebar = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=2)
        sidebar.set_css_classes(["settings-sidebar"])
        sidebar.set_size_request(180, -1)

        for emoji, name in self.SECTIONS:
            btn = Gtk.Button(
                label=f"{emoji}  {name}")
            btn.set_css_classes(["settings-nav-btn"])
            btn.connect(
                "clicked",
                lambda b, n=name: self._show(n))
            sidebar.append(btn)
        self.append(sidebar)

        # Content area
        self.content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=16)
        self.content.set_hexpand(True)
        self.content.set_css_classes(["settings-content"])
        self.content.set_margin_start(24)
        self.content.set_margin_top(20)
        self.content.set_margin_end(24)
        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.content)
        scroll.set_vexpand(True)
        self.append(scroll)

        self._show("About")

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
                    display,
                    provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )
        except Exception as e:
            print(f"[SETTINGS] CSS fallback failed: {e}")

    def _clear(self):
        while c := self.content.get_first_child():
            self.content.remove(c)

    def _label(self, text, css=""):
        l = Gtk.Label(label=text)
        l.set_halign(Gtk.Align.START)
        if css: l.set_css_classes([css])
        return l

    def _show(self, section):
        self._clear()
        if section == "About":
            self._show_about()
        elif section == "AI & Model":
            self._show_ai()
        elif section == "Appearance":
            self._show_appearance()
        elif section == "Network":
            self._show_network()
        elif section == "Notifications":
            self._show_notifs()

    def _show_about(self):
        self.content.append(
            self._label("⚡ Eonix OS",
                        "section-title"))
        for k, v in [
            ("Version",    "v1.5.0-dev"),
            ("Model",      "LightGBM v1.2"),
            ("Accuracy",   "63.47%"),
            ("Tests",      "207+ passing"),
            ("Boot time",  "~30 seconds"),
            ("RAM idle",   "~1.2 GB"),
            ("Agents",     "5 online"),
            ("Built by",   "Shahnoor"),
        ]:
            row = Gtk.Box(spacing=12)
            row.set_css_classes(["settings-row"])
            row.append(self._label(k, "settings-key"))
            row.append(self._label(v, "settings-val"))
            self.content.append(row)

    def _show_ai(self):
        self.content.append(
            self._label("🤖 AI Model Status",
                        "section-title"))
        # Try to read from hub
        try:
            import urllib.request
            with urllib.request.urlopen(
                "http://localhost:7750/hub/status",
                timeout=2) as r:
                data = json.loads(r.read())
            mv = data.get("model_version","v1.2")
            mr = data.get("model_ready", True)
        except Exception:
            mv, mr = "v1.2", True

        for k, v in [
            ("Active model",  mv),
            ("Model ready",   "Yes" if mr else "No"),
            ("Training rows", "148,812"),
            ("Retrain at",    "120,000 rows"),
            ("Algorithm",     "LightGBM"),
        ]:
            row = Gtk.Box(spacing=12)
            row.set_css_classes(["settings-row"])
            row.append(self._label(k,"settings-key"))
            row.append(self._label(v,"settings-val"))
            self.content.append(row)

    def _show_appearance(self):
        self.content.append(
            self._label("🎨 Appearance",
                        "section-title"))
        # Accent color picker (placeholder)
        lbl = self._label(
            "Accent color: Violet (#7c4dff)",
            "settings-val")
        self.content.append(lbl)
        note = self._label(
            "Full color picker coming in v2.0",
            "settings-key")
        self.content.append(note)

    def _show_network(self):
        self.content.append(
            self._label("📡 Network",
                        "section-title"))
        try:
            import socket
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
        except Exception:
            hostname, ip = "eonix-os", "127.0.0.1"
        for k, v in [
            ("Hostname", hostname),
            ("IP",       ip),
            ("Sync",     "zeroconf enabled"),
        ]:
            row = Gtk.Box(spacing=12)
            row.set_css_classes(["settings-row"])
            row.append(self._label(k,"settings-key"))
            row.append(self._label(v,"settings-val"))
            self.content.append(row)

    def _show_notifs(self):
        self.content.append(
            self._label("🔔 Notifications",
                        "section-title"))
        self.content.append(self._label(
            "AI proactive alerts: Enabled",
            "settings-val"))
        self.content.append(self._label(
            "Retrain alerts: Enabled",
            "settings-val"))
