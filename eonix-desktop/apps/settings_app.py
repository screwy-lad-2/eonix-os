# -*- coding: utf-8 -*-
"""Eonix Settings — 7 panels, live font + accent, LLM key management, voice, OTA."""
import os
import json
import sys
import subprocess
import threading

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CORE = os.path.join(_ROOT, "eonix-core")
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

MODEL_PATH = os.path.expanduser(
    "~/.config/eonix/models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf")


class EonixSettings(Gtk.Box):

    SECTIONS = [
        ("appearance", "Appearance"),
        ("ai", "AI & Agents"),
        ("display", "Display"),
        ("voice", "Voice"),
        ("sync", "Sync"),
        ("privacy", "Privacy"),
        ("updates", "Updates"),
        ("about", "About"),
    ]

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.set_vexpand(True)
        self.set_hexpand(True)
        self._cfg = self._load_cfg()
        self._apply_css()
        self._build()
        self._font_provider = Gtk.CssProvider()

    # ── Config ────────────────────────────────────────
    def _load_cfg(self):
        path = os.path.expanduser("~/.config/eonix/settings.json")
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_setting(self, key, val):
        path = os.path.expanduser("~/.config/eonix/settings.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            cfg = {}
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    cfg = json.load(f)
            cfg[key] = val
            with open(path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
            self._cfg = cfg
        except Exception as e:
            print(f"[Settings] save: {e}")

    # ── Build ─────────────────────────────────────────
    def _build(self):
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        sidebar.set_css_classes(["settings-sidebar"])
        sidebar.set_margin_top(12)
        sidebar.set_size_request(185, -1)

        self._stack = Gtk.Stack()
        self._stack.set_vexpand(True)
        self._stack.set_hexpand(True)
        self._stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self._stack.set_transition_duration(130)

        for key, label in self.SECTIONS:
            btn = Gtk.Button(label=label)
            btn.set_css_classes(["settings-nav-btn"])
            btn.set_halign(Gtk.Align.FILL)
            _k = key
            btn.connect("clicked", lambda w, k=_k: self._stack.set_visible_child_name(k))
            sidebar.append(btn)

            content = self._build_panel(key)
            scroll = Gtk.ScrolledWindow()
            scroll.set_vexpand(True)
            scroll.set_hexpand(True)
            scroll.set_child(content)
            self._stack.add_titled(scroll, key, label)

        self.append(sidebar)
        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        self.append(sep)
        self.append(self._stack)
        GLib.idle_add(self._stack.set_visible_child_name, "appearance")

    # ── Panel router ──────────────────────────────────
    def _build_panel(self, key):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_css_classes(["settings-content"])
        box.set_margin_start(20)
        box.set_margin_end(20)
        box.set_margin_top(16)
        box.set_margin_bottom(16)
        dispatch = {
            "appearance": self._panel_appearance,
            "ai": self._panel_ai,
            "display": self._panel_display,
            "voice": self._panel_voice,
            "sync": self._panel_sync,
            "privacy": self._panel_privacy,
            "updates": self._panel_updates,
            "about": self._panel_about,
        }
        fn = dispatch.get(key)
        if fn:
            fn(box)
        return box

    # ── Helpers ───────────────────────────────────────
    def _sec(self, box, text):
        lbl = Gtk.Label(label=text)
        lbl.set_css_classes(["settings-sec-title"])
        lbl.set_halign(Gtk.Align.START)
        lbl.set_margin_top(10)
        lbl.set_margin_bottom(2)
        box.append(lbl)

    def _row(self, box, key, value="", widget=None):
        row = Gtk.Box(spacing=0)
        row.set_css_classes(["settings-row"])
        row.set_margin_bottom(3)
        k = Gtk.Label(label=key)
        k.set_css_classes(["settings-key"])
        k.set_size_request(190, -1)
        k.set_halign(Gtk.Align.START)
        row.append(k)
        if widget is not None:
            widget.set_hexpand(True)
            widget.set_halign(Gtk.Align.END)
            row.append(widget)
        else:
            v = Gtk.Label(label=str(value))
            v.set_css_classes(["settings-val"])
            v.set_halign(Gtk.Align.END)
            v.set_hexpand(True)
            row.append(v)
        box.append(row)
        return row

    def _action_btn(self, box, label, callback, style="normal"):
        btn = Gtk.Button(label=label)
        classes = ["settings-action-btn"]
        if style == "warning":
            classes.append("settings-btn-warn")
        btn.set_css_classes(classes)
        btn.set_margin_top(6)
        btn.connect("clicked", callback)
        box.append(btn)
        return btn

    # ── APPEARANCE ────────────────────────────────────
    def _panel_appearance(self, box):
        self._sec(box, "THEME")
        accent_box = Gtk.Box(spacing=8)
        accent_box.set_margin_bottom(4)
        for color in ["#7c4dff", "#00bcd4", "#e91e63", "#4caf50", "#ff9800", "#f44336"]:
            btn = Gtk.Button()
            btn.set_size_request(28, 28)
            css = (f".swatch-{color[1:]}{{background:{color};border-radius:50%;"
                   "border:2px solid rgba(255,255,255,0.25);min-width:28px;min-height:28px;}}").encode()
            pr = Gtk.CssProvider()
            pr.load_from_data(css)
            display = Gdk.Display.get_default()
            if display:
                Gtk.StyleContext.add_provider_for_display(display, pr, 800)
            btn.set_css_classes([f"swatch-{color[1:]}"])
            _c = color
            btn.connect("clicked", lambda _, c=_c: self._apply_accent(c))
            accent_box.append(btn)
        box.append(accent_box)

        self._sec(box, "TYPOGRAPHY")
        self._font_lbl = Gtk.Label(label=f"Font size: {self._cfg.get('font_size', 12)}px")
        self._font_lbl.set_css_classes(["settings-val"])
        self._font_lbl.set_halign(Gtk.Align.START)

        font_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 9, 18, 1)
        font_scale.set_value(self._cfg.get("font_size", 12))
        font_scale.set_hexpand(True)
        font_scale.set_draw_value(True)
        font_scale.connect("value-changed", self._live_font_size)
        self._row(box, "Font Size (px)", widget=font_scale)
        box.append(self._font_lbl)

        self._sec(box, "UI SCALE")
        note = Gtk.Label(label="Font size changes are instant.\nUI scale requires restart.")
        note.set_css_classes(["settings-note"])
        note.set_halign(Gtk.Align.START)
        note.set_wrap(True)
        box.append(note)

        self._scale_dd = Gtk.DropDown.new_from_strings(
            ["100% (Default)", "125%", "150%", "175%", "200%"])
        saved_s = self._cfg.get("ui_scale", 1.0)
        scale_map = {1.0: 0, 1.25: 1, 1.5: 2, 1.75: 3, 2.0: 4}
        self._scale_dd.set_selected(scale_map.get(saved_s, 0))
        self._row(box, "UI Scale (restart needed)", widget=self._scale_dd)
        self._action_btn(box, "Save Scale + Restart Desktop", self._save_scale_restart, style="warning")

    def _live_font_size(self, scale):
        size = int(scale.get_value())
        css = f"* {{ font-size: {size}px; }}".encode()
        display = Gdk.Display.get_default()
        if display:
            try:
                Gtk.StyleContext.remove_provider_for_display(display, self._font_provider)
            except Exception:
                pass
            self._font_provider.load_from_data(css)
            Gtk.StyleContext.add_provider_for_display(
                display, self._font_provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        if hasattr(self, "_font_lbl"):
            self._font_lbl.set_text(f"Font size: {size}px \u2014 applied live")
        self._save_setting("font_size", size)

    def _apply_accent(self, color):
        css = (f".dock-btn:hover{{background:{color}22;}}"
               f".eonix-btn-primary{{background:{color};}}"
               f".topbar-launcher-btn{{color:{color};}}").encode()
        pr = Gtk.CssProvider()
        pr.load_from_data(css)
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(display, pr, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        self._save_setting("accent_color", color)

    def _save_scale_restart(self, _):
        factors = [1.0, 1.25, 1.5, 1.75, 2.0]
        idx = self._scale_dd.get_selected()
        f = factors[idx]
        self._save_setting("ui_scale", f)
        xp = os.path.expanduser("~/.xprofile")
        lines = []
        if os.path.exists(xp):
            with open(xp) as fp:
                lines = [l for l in fp.readlines() if "GDK_SCALE" not in l and "QT_SCALE" not in l]
        lines += [f"export GDK_SCALE={f}\n", f"export QT_SCALE_FACTOR={f}\n", f"export GDK_DPI_SCALE={f}\n"]
        with open(xp, "w") as fp:
            fp.writelines(lines)

    # ── AI & AGENTS ───────────────────────────────────
    def _panel_ai(self, box):
        self._sec(box, "AI STATUS")
        self._row(box, "Model", "LightGBM v1.2")
        self._row(box, "Accuracy", "63.47%")
        self._row(box, "Chat Engine", "Multi-backend LLM")

        self._sec(box, "API KEYS")
        api_note = Gtk.Label(label="Groq = free cloud LLM.\ngroq.com \u2192 free tier \u2192 API keys.\nLlama 3.3 70B, 30 RPM free.")
        api_note.set_css_classes(["settings-note"])
        api_note.set_halign(Gtk.Align.START)
        api_note.set_wrap(True)
        box.append(api_note)

        groq = Gtk.Entry()
        groq.set_placeholder_text("gsk_... (Groq API key)")
        groq.set_visibility(False)
        groq.set_hexpand(True)
        groq.set_text(self._cfg.get("groq_api_key", ""))
        self._row(box, "Groq API Key", widget=groq)

        oai = Gtk.Entry()
        oai.set_placeholder_text("sk-... (OpenAI API key)")
        oai.set_visibility(False)
        oai.set_hexpand(True)
        oai.set_text(self._cfg.get("openai_api_key", ""))
        self._row(box, "OpenAI API Key", widget=oai)

        def _save_keys(_):
            self._save_setting("groq_api_key", groq.get_text().strip())
            self._save_setting("openai_api_key", oai.get_text().strip())
            save_btn.set_label("Saved!")
            GLib.timeout_add(1500, lambda: save_btn.set_label("Save Keys"))
        save_btn = self._action_btn(box, "Save Keys", _save_keys)

        # Groq connection test
        self._groq_test_lbl = Gtk.Label(label="")
        self._groq_test_lbl.set_css_classes(["settings-note"])
        self._groq_test_lbl.set_halign(Gtk.Align.START)
        self._groq_test_lbl.set_margin_top(4)

        def _test_groq_connection(btn):
            key = groq.get_text().strip()
            if not key:
                self._groq_test_lbl.set_text("No key entered.")
                return
            btn.set_sensitive(False)
            btn.set_label("Testing...")
            import urllib.request
            def _run():
                try:
                    data = json.dumps({
                        "model": "llama-3.3-70b-versatile",
                        "messages": [{"role": "user", "content": "Say: OK"}],
                        "max_tokens": 5
                    }).encode()
                    req = urllib.request.Request(
                        "https://api.groq.com/openai/v1/chat/completions",
                        data=data,
                        headers={"Authorization": f"Bearer {key}",
                                  "Content-Type": "application/json"},
                        method="POST")
                    with urllib.request.urlopen(req, timeout=8) as r:
                        res = json.loads(r.read())
                    reply = res["choices"][0]["message"]["content"].strip()
                    msg = f'Connected! Groq responded: "{reply}"'
                except Exception as e:
                    msg = f"Failed: {e}\nCheck key is correct & has internet."
                GLib.idle_add(self._groq_test_lbl.set_text, msg)
                GLib.idle_add(btn.set_sensitive, True)
                GLib.idle_add(btn.set_label, "Test Groq Connection")
            threading.Thread(target=_run, daemon=True).start()

        test_btn = Gtk.Button(label="Test Groq Connection")
        test_btn.set_css_classes(["settings-action-btn"])
        test_btn.set_margin_top(6)
        test_btn.connect("clicked", _test_groq_connection)
        box.append(test_btn)
        box.append(self._groq_test_lbl)

        self._sec(box, "LOCAL LLM (OFFLINE)")
        installed = os.path.exists(MODEL_PATH)
        self._row(box, "Model", "TinyLlama 1.1B Q4 (637MB)")
        self._row(box, "Status", "Ready" if installed else "Not installed")
        if not installed:
            self._action_btn(box, "Download TinyLlama (offline AI)", self._download_model)
        else:
            lbl = Gtk.Label(label="Local LLM ready. No internet needed.")
            lbl.set_css_classes(["settings-note"])
            lbl.set_halign(Gtk.Align.START)
            box.append(lbl)

    def _download_model(self, btn):
        btn.set_sensitive(False)
        btn.set_label("Downloading (637MB)...")
        URL = ("https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF/resolve/"
               "main/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf")
        def _dl():
            try:
                import urllib.request
                os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
                urllib.request.urlretrieve(URL, MODEL_PATH)
                GLib.idle_add(btn.set_label, "Done! TinyLlama ready.")
            except Exception as e:
                GLib.idle_add(btn.set_label, f"Failed: {e}")
                GLib.idle_add(btn.set_sensitive, True)
        threading.Thread(target=_dl, daemon=True).start()

    # ── DISPLAY ───────────────────────────────────────
    def _panel_display(self, box):
        self._sec(box, "SCREEN")
        res = "1920x1080"
        try:
            r = subprocess.run(["xrandr", "--current"], capture_output=True, text=True, timeout=3)
            for line in r.stdout.split("\n"):
                if "*" in line:
                    parts = line.split()
                    if parts:
                        res = parts[0]
                    break
        except Exception:
            pass
        self._row(box, "Resolution", res)
        self._row(box, "Compositor", "X11")

        self._sec(box, "BRIGHTNESS")
        bright = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 10, 100, 5)
        bright.set_value(self._cfg.get("brightness", 80))
        bright.set_hexpand(True)
        bright.set_draw_value(True)
        bright.connect("value-changed", lambda s: self._save_setting("brightness", int(s.get_value())))
        self._row(box, "Brightness %", widget=bright)

    # ── VOICE ─────────────────────────────────────────
    def _panel_voice(self, box):
        self._sec(box, "VOICE COMMANDS")
        v_sw = Gtk.Switch()
        v_sw.set_active(self._cfg.get("voice_enabled", True))
        v_sw.connect("notify::active", lambda s, _: self._save_setting("voice_enabled", s.get_active()))
        self._row(box, "Enable Voice", widget=v_sw)
        self._row(box, "Wake Word", '"Hey Eonix"')
        self._row(box, "Offline TTS", "espeak-ng")

        self._sec(box, "SPEECH SETTINGS")
        speed = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 80, 220, 10)
        speed.set_value(self._cfg.get("voice_speed", 160))
        speed.set_hexpand(True)
        speed.set_draw_value(True)
        speed.connect("value-changed", lambda s: self._save_setting("voice_speed", int(s.get_value())))
        self._row(box, "Speed (words/min)", widget=speed)

        vol = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 5)
        vol.set_value(self._cfg.get("voice_vol", 90))
        vol.set_hexpand(True)
        vol.set_draw_value(True)
        vol.connect("value-changed", lambda s: self._save_setting("voice_vol", int(s.get_value())))
        self._row(box, "Volume", widget=vol)

    # ── SYNC ──────────────────────────────────────────
    def _panel_sync(self, box):
        self._sec(box, "SYNC ENGINE")
        self._row(box, "Sync Server", "localhost:7740")
        self._row(box, "Protocol", "HTTP push/pull")
        self._row(box, "Tables", "notes  goals  settings")

        self._sync_status = Gtk.Label(label="Not checked yet")
        self._sync_status.set_css_classes(["settings-note"])
        self._sync_status.set_halign(Gtk.Align.START)
        self._sync_status.set_margin_top(6)
        box.append(self._sync_status)

        self._sec(box, "ACTIONS")
        btn_row = Gtk.Box(spacing=10)
        btn_row.set_margin_top(6)

        sync_btn = Gtk.Button(label="Sync Now")
        sync_btn.set_css_classes(["settings-action-btn"])
        sync_btn.connect("clicked", self._do_sync)
        btn_row.append(sync_btn)

        qr_btn = Gtk.Button(label="Show QR Code")
        qr_btn.set_css_classes(["settings-action-btn"])
        qr_btn.connect("clicked", self._show_qr)
        btn_row.append(qr_btn)

        box.append(btn_row)

        self._sec(box, "CONNECTED DEVICES")
        self._row(box, "eonix-pc", "This device")
        note = Gtk.Label(label="Scan QR on another device to pair.\nSync runs on local network only.")
        note.set_css_classes(["settings-note"])
        note.set_halign(Gtk.Align.START)
        note.set_wrap(True)
        note.set_margin_top(6)
        box.append(note)

    def _do_sync(self, btn):
        btn.set_sensitive(False)
        btn.set_label("Syncing...")
        import sys as _s
        _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        sync_path = os.path.join(_root, "eonix-sync")
        if sync_path not in _s.path:
            _s.path.insert(0, sync_path)
        def _run():
            try:
                from sync_client import EonixSyncClient
                result = EonixSyncClient().full_sync()
                import datetime
                now = datetime.datetime.now().strftime("%d %b %H:%M")
                msg = f"Synced {now}: " + ", ".join(f"{k}={v}" for k, v in result.items())
            except Exception as e:
                msg = f"Sync failed: {e}"
            GLib.idle_add(self._sync_status.set_text, msg)
            GLib.idle_add(btn.set_sensitive, True)
            GLib.idle_add(btn.set_label, "Sync Now")
        threading.Thread(target=_run, daemon=True).start()

    def _show_qr(self, btn):
        import sys as _s
        _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        sync_path = os.path.join(_root, "eonix-sync")
        if sync_path not in _s.path:
            _s.path.insert(0, sync_path)
        try:
            from qr_pair import make_qr, get_local_ip
            path, url = make_qr()
            if path:
                info = Gtk.Label(label=f"Scan to pair\n{url}")
                info.set_css_classes(["settings-note"])
                info.set_halign(Gtk.Align.CENTER)
                info.set_margin_top(10)
                self._sync_status.set_text(f"QR saved to {path} - URL: {url}")
            else:
                self._sync_status.set_text(f"QR: {url}")
        except Exception as e:
            ip = "localhost"
            self._sync_status.set_text(f"Pair URL: http://{ip}:7740 (qrcode pkg not installed)")

    # ── PRIVACY ───────────────────────────────────────
    def _panel_privacy(self, box):
        self._sec(box, "DATA POLICY")
        self._row(box, "Data stored", "Locally only")
        self._row(box, "Cloud sync", "Never (opt-in)")
        self._row(box, "Telemetry", "None")

        self._sec(box, "AI LEARNING")
        ai_sw = Gtk.Switch()
        ai_sw.set_active(self._cfg.get("ai_learn", True))
        ai_sw.connect("notify::active", lambda s, _: self._save_setting("ai_learn", s.get_active()))
        self._row(box, "AI learns from usage", widget=ai_sw)

    # ── UPDATES ───────────────────────────────────────
    def _panel_updates(self, box):
        self._sec(box, "EONIX OS")
        self._row(box, "Version", "v1.5.0")
        self._row(box, "Build", "Week 51")

        self._upd_lbl = Gtk.Label(label="Not checked yet")
        self._upd_lbl.set_css_classes(["settings-note"])
        self._upd_lbl.set_halign(Gtk.Align.START)
        self._upd_lbl.set_margin_top(6)
        box.append(self._upd_lbl)

        self._action_btn(box, "Check for Updates", self._check_updates)

        self._sec(box, "HOME SAFETY")
        note = Gtk.Label(label="/home is always preserved.\nGoals, Notes, AI data survive all updates.")
        note.set_css_classes(["settings-note"])
        note.set_halign(Gtk.Align.START)
        note.set_wrap(True)
        box.append(note)

    def _check_updates(self, btn):
        btn.set_sensitive(False)
        btn.set_label("Checking...")
        def _run():
            import datetime
            try:
                from ota_updater import EonixOTA
                r = EonixOTA().check_for_updates()
                if r.get("available"):
                    msg = f"Update available: v{r['latest']}"
                elif "error" in r:
                    msg = "No internet."
                else:
                    msg = "Up to date!"
            except Exception:
                msg = "Check failed."
            now = datetime.datetime.now().strftime("%d %b %H:%M")
            GLib.idle_add(self._upd_lbl.set_text, f"Checked {now}: {msg}")
            GLib.idle_add(btn.set_sensitive, True)
            GLib.idle_add(btn.set_label, "Check for Updates")
        threading.Thread(target=_run, daemon=True).start()

    # ── ABOUT ─────────────────────────────────────────
    def _panel_about(self, box):
        import platform
        self._sec(box, "EONIX OS")
        self._row(box, "Version", "v1.5.0")
        self._row(box, "Build Week", "51")
        self._row(box, "Kernel", platform.release())
        self._row(box, "Python", platform.python_version())
        self._row(box, "Desktop", "Eonix Aura GTK4")

        self._sec(box, "AI STACK")
        self._row(box, "Chat Engine", "Multi-backend LLM")
        self._row(box, "Cloud LLM", "Groq / OpenAI (opt-in)")
        self._row(box, "Local model", "TinyLlama 1.1B (opt-in)")
        self._row(box, "Voice TTS", "espeak-ng (offline)")

        self._sec(box, "CREDITS")
        c = Gtk.Label(label="Built with Python + GTK4\nMIT License \u2014 Open Source\ngithub.com/shahnoor-exe/eonix-os")
        c.set_css_classes(["settings-note"])
        c.set_halign(Gtk.Align.START)
        box.append(c)

    # ── CSS ───────────────────────────────────────────
    def _apply_css(self):
        css = b"""
        .settings-sidebar {
          background-color: #0a0a16; min-width: 185px;
          padding-top: 6px; padding-bottom: 6px; }
        .settings-nav-btn {
          background: transparent; color: #7a7a9a; border: none;
          border-radius: 8px; padding: 9px 14px; margin: 1px 8px; font-size: 13px; }
        .settings-nav-btn:hover {
          background: rgba(124,77,255,.18); color: #d0d0f0; }
        .settings-content { background: transparent; }
        .settings-sec-title {
          font-size: 10px; font-weight: 800; color: #444466;
          letter-spacing: 1.8px; }
        .settings-row {
          background: rgba(255,255,255,.04); border-radius: 8px;
          padding: 8px 12px; min-height: 34px; }
        .settings-key { font-size: 13px; color: #8888a8; }
        .settings-val { font-size: 13px; font-weight: 600; color: #d0d0e8; }
        .settings-note { font-size: 12px; color: #505072; line-height: 1.6; }
        .settings-action-btn {
          background: rgba(124,77,255,.18); color: #a78bfa;
          border: 1px solid rgba(124,77,255,.3); border-radius: 8px;
          padding: 8px 16px; font-size: 13px; font-weight: 600; }
        .settings-action-btn:hover {
          background: rgba(124,77,255,.35); color: #d0b0ff; }
        .settings-btn-warn {
          background: rgba(255,152,0,.15); color: #ffa726;
          border-color: rgba(255,152,0,.3); }
        .settings-btn-warn:hover {
          background: rgba(255,152,0,.28); }
        """
        pr = Gtk.CssProvider()
        pr.load_from_data(css)
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(
                display, pr, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
