"""Eonix AI Chat — the Iron Man assistant.

Text input → command parser → OS action.
Handles natural language commands for app launching,
system info queries, settings changes, file operations.
"""
import gi
import os
import json

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib


class EonixAIChat(Gtk.Box):

    COMMANDS = {
        "open terminal": "terminal",
        "open files": "files",
        "open settings": "settings",
        "open mind": "mind",
        "open hub": "hub",
        "open goals": "goals",
        "open system": "system",
        "open notes": "notes",
        "dark mode on": "dark_on",
        "dark mode off": "dark_off",
        "show cpu": "cpu",
        "show ram": "ram",
        "show disk": "disk",
        "show time": "time",
        "show date": "date",
        "show week": "week",
        "show version": "version",
        "show ip": "ip",
        "show hostname": "hostname",
        "organize files": "organize",
        "list files": "listfiles",
        "my notes": "shownotes",
        "clear chat": "clear",
        "help": "help",
    }

    def __init__(self, desktop_ref=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_vexpand(True)
        self.set_hexpand(True)
        self._desktop = desktop_ref
        self._history = []
        self._voice = None
        try:
            import sys as _s
            _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            if os.path.join(_root, "eonix-core") not in _s.path:
                _s.path.insert(0, os.path.join(_root, "eonix-core"))
            from voice_engine import EonixVoice
            self._voice = EonixVoice(command_callback=self._on_voice_command)
        except Exception as e:
            print(f"[AI CHAT] Voice init: {e}")
        self._llm = None
        try:
            from llm_engine import EonixLLM
            self._llm = EonixLLM()
        except Exception as e:
            print(f"[AI CHAT] LLM init: {e}")
        self._apply_css()
        self._build_ui()

        self._maybe_show_setup_banner()
    def _apply_css(self):
        css = b"""
        .ai-root {
          background: #080814;
        }
        .ai-header {
          background: #0d0d1a;
          border-bottom: 1px solid rgba(124,77,255,0.25);
          padding: 12px 16px;
        }
        .ai-title {
          font-size: 15px;
          font-weight: 700;
          color: #a78bfa;
        }
        .ai-subtitle {
          font-size: 11px;
          color: #555580;
        }
        .ai-bubble-user {
          background: rgba(124,77,255,0.22);
          border-radius: 16px 16px 4px 16px;
          padding: 10px 14px;
          margin: 4px 8px 4px 48px;
          color: #e0e0e0;
          font-size: 13px;
        }
        .ai-bubble-eonix {
          background: rgba(255,255,255,0.05);
          border-radius: 16px 16px 16px 4px;
          padding: 10px 14px;
          margin: 4px 48px 4px 8px;
          color: #c0c0d8;
          font-size: 13px;
          border: 1px solid rgba(124,77,255,0.15);
        }
        .ai-input-bar {
          background: #0d0d1a;
          border-top: 1px solid rgba(124,77,255,0.2);
          padding: 10px 12px;
        }
        .ai-input {
          background: rgba(255,255,255,0.06);
          border: 1px solid rgba(124,77,255,0.3);
          border-radius: 24px;
          padding: 8px 16px;
          color: #e0e0e0;
          font-size: 13px;
        }
        .ai-input:focus {
          border-color: #7c4dff;
        }
        .ai-send-btn {
          background: #7c4dff;
          color: white;
          border-radius: 50%;
          min-width: 36px;
          min-height: 36px;
          font-size: 16px;
          margin-left: 8px;
        }
        .ai-send-btn:hover {
          background: #9d6fff;
        }
        .ai-status-online {
          color: #50fa7b;
          font-size: 11px;
          font-weight: 700;
        }
        .chat-voice-btn {
          background: rgba(124,77,255,0.2);
          border: none;
          border-radius: 50%;
          color: #a78bfa;
          font-size: 16px;
          min-width: 40px;
          min-height: 40px;
          margin-left: 6px;
        }
        .chat-voice-btn:hover {
          background: rgba(124,77,255,0.4);
        }
        .ai-banner-title {
          font-size: 13px; font-weight: 700; color: #a78bfa; margin-bottom: 4px;
        }
        .ai-source-badge {
          font-size: 10px; color: #444466; font-style: italic;
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
            print(f"[AI CHAT] CSS failed: {e}")

    def _build_ui(self):
        self.set_css_classes(["ai-root"])

        # Header
        header = Gtk.Box(spacing=8)
        header.set_css_classes(["ai-header"])
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        vbox.set_hexpand(True)
        title = Gtk.Label(label="🤖 Eonix AI")
        title.set_css_classes(["ai-title"])
        title.set_halign(Gtk.Align.START)
        subtitle = Gtk.Label(label="MIND Agent • LightGBM v1.2")
        subtitle.set_css_classes(["ai-subtitle"])
        subtitle.set_halign(Gtk.Align.START)
        vbox.append(title)
        vbox.append(subtitle)
        header.append(vbox)
        status = Gtk.Label(label="● ONLINE")
        status.set_css_classes(["ai-status-online"])
        header.append(status)
        self.append(header)
        self._src_lbl = Gtk.Label(label="")
        self._src_lbl.set_halign(Gtk.Align.END)
        self._src_lbl.set_hexpand(True)
        self._src_lbl.set_margin_end(8)
        header.append(self._src_lbl)

        # Chat scroll area
        self._scroll = Gtk.ScrolledWindow()
        self._scroll.set_vexpand(True)
        self._scroll.set_policy(
            Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._chat_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._chat_box.set_margin_top(12)
        self._chat_box.set_margin_bottom(8)
        self._scroll.set_child(self._chat_box)
        self.append(self._scroll)

        # Welcome message
        self._add_eonix_msg(
            "👋 Hello! I'm Eonix AI.\n\n"
            "I can help you:\n"
            "• Open any app — \"open terminal\"\n"
            "• Check system — \"show cpu\"\n"
            "• Change settings — \"dark mode on\"\n"
            "• Manage files — \"list files\"\n"
            "• View notes — \"my notes\"\n\n"
            "Type 'help' for all commands.")

        # Input bar
        input_bar = Gtk.Box(spacing=0)
        input_bar.set_css_classes(["ai-input-bar"])
        self._entry = Gtk.Entry()
        self._entry.set_css_classes(["ai-input"])
        self._entry.set_hexpand(True)
        self._entry.set_placeholder_text("Ask Eonix anything...")
        self._entry.connect("activate", self._on_send)
        input_bar.append(self._entry)
        send_btn = Gtk.Button(label="→")
        send_btn.set_css_classes(["ai-send-btn"])
        send_btn.connect("clicked", self._on_send)
        input_bar.append(send_btn)
        self._voice_btn = Gtk.Button(label="🎤")
        self._voice_btn.set_css_classes(["chat-voice-btn"])
        self._voice_btn.set_tooltip_text("Voice command")
        self._voice_btn.connect("clicked", self._on_voice_click)
        input_bar.append(self._voice_btn)
        self.append(input_bar)

    def _add_user_msg(self, text):
        lbl = Gtk.Label(label=text)
        lbl.set_css_classes(["ai-bubble-user"])
        lbl.set_halign(Gtk.Align.END)
        lbl.set_wrap(True)
        lbl.set_xalign(0)
        self._chat_box.append(lbl)
        self._scroll_to_bottom()

    def _add_eonix_msg(self, text):
        lbl = Gtk.Label(label=text)
        lbl.set_css_classes(["ai-bubble-eonix"])
        lbl.set_halign(Gtk.Align.START)
        lbl.set_wrap(True)
        lbl.set_xalign(0)
        self._chat_box.append(lbl)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        def _do():
            adj = self._scroll.get_vadjustment()
            adj.set_value(adj.get_upper())
            return False
        GLib.idle_add(_do)

    def _on_send(self, *_):
        text = self._entry.get_text().strip()
        if not text:
            return
        self._entry.set_text("")
        self._add_user_msg(text)
        self._history.append({"role": "user", "text": text})
        GLib.timeout_add(300, lambda: self._process(text))

    def _on_voice_click(self, btn):
        """Mic button → listen for one utterance."""
        if not self._voice:
            self._add_eonix_msg("🎤 Voice engine not available.\nInstall: pip3 install SpeechRecognition pyttsx3 pyaudio")
            return
        btn.set_label("🔴")
        btn.set_sensitive(False)
        import threading
        def _listen():
            text = self._voice.listen_once()
            GLib.idle_add(self._voice_done, text, btn)
        threading.Thread(target=_listen, daemon=True).start()

    def _voice_done(self, text, btn):
        btn.set_label("🎤")
        btn.set_sensitive(True)
        if text:
            self._entry.set_text(text)
            self._on_send()
        else:
            self._add_eonix_msg("🎤 Didn't catch that. Try again or type your command.")

    def _on_voice_command(self, cmd):
        """Called by wake word listener (background)."""
        GLib.idle_add(self._add_user_msg, cmd)
        response = self._match_command(cmd)
        GLib.idle_add(self._add_eonix_msg, response)
        if self._voice:
            self._voice.speak(response[:120])

    def _process(self, text):
        lower = text.lower().strip()
        response = self._match_command(lower)
        self._add_eonix_msg(response)
        self._history.append({"role": "eonix", "text": response})
        return False

    def _match_command(self, text):
        import subprocess, socket, datetime

        try:
            import psutil
        except ImportError:
            psutil = None

        # App launchers
        if any(w in text for w in ["open terminal", "terminal", "shell", "bash"]):
            if self._desktop:
                GLib.idle_add(lambda: self._desktop._handle_dock_launch("EonixShell"))
            return "✅ Opening EonixShell terminal..."

        if any(w in text for w in ["open files", "file manager", "nautilus"]):
            if self._desktop:
                GLib.idle_add(lambda: self._desktop._handle_dock_launch("Files"))
            return "✅ Opening Files..."

        if any(w in text for w in ["open settings", "settings", "preferences"]):
            if self._desktop:
                GLib.idle_add(lambda: self._desktop._handle_dock_launch("Settings"))
            return "✅ Opening Settings..."

        if any(w in text for w in ["open mind", "mind agent", "ai agent"]):
            if self._desktop:
                GLib.idle_add(lambda: self._desktop._handle_dock_launch("MIND"))
            return "✅ Opening MIND Agent..."

        if any(w in text for w in ["open goals", "goals"]):
            if self._desktop:
                GLib.idle_add(lambda: self._desktop._handle_dock_launch("Goals"))
            return "✅ Opening Goals..."

        if any(w in text for w in ["open notes", "notes", "write note"]):
            if self._desktop:
                GLib.idle_add(lambda: self._desktop._handle_dock_launch("Notes"))
            return "📝 Opening Notes..."

        # Notes viewer
        if any(w in text for w in ["my notes", "show notes", "read notes"]):
            try:
                np = os.path.expanduser("~/.config/eonix/notes.json")
                with open(np, encoding="utf-8") as f:
                    notes = json.load(f)
                titles = "\n".join(
                    f"  📄 {n.get('title', '?')}" for n in notes[:8])
                return f"📝 Your notes ({len(notes)} total):\n{titles}"
            except Exception:
                return "📝 No notes yet. Say 'open notes' to create your first note."

        # Settings changes
        if "dark mode on" in text or "enable dark" in text:
            self._write_setting("dark_mode", True)
            gs = Gtk.Settings.get_default()
            if gs:
                gs.set_property("gtk-application-prefer-dark-theme", True)
            return "🌙 Dark mode enabled. Desktop updated."

        if "dark mode off" in text or "light mode" in text:
            self._write_setting("dark_mode", False)
            gs = Gtk.Settings.get_default()
            if gs:
                gs.set_property("gtk-application-prefer-dark-theme", False)
            return "☀️ Light mode enabled. Desktop updated."

        if "font" in text and any(c.isdigit() for c in text):
            import re
            nums = re.findall(r'\d+', text)
            size = int(nums[0]) if nums else 10
            size = max(8, min(16, size))
            gs = Gtk.Settings.get_default()
            if gs:
                gs.set_property("gtk-font-name", f"Sans {size}")
            self._write_setting("font_scale", round(size / 10, 1))
            return f"🔤 Font size set to {size}pt. Applied!"

        # System info
        if psutil and any(w in text for w in ["cpu", "processor"]):
            pct = psutil.cpu_percent(interval=0.5)
            cnt = psutil.cpu_count()
            return f"🖥️ CPU: {pct}% used across {cnt} core(s)"

        if psutil and any(w in text for w in ["ram", "memory"]):
            m = psutil.virtual_memory()
            used = m.used // (1024**2)
            total = m.total // (1024**2)
            return f"🧠 RAM: {used}MB / {total}MB ({m.percent}% used)"

        if psutil and any(w in text for w in ["disk", "storage", "space"]):
            d = psutil.disk_usage('/')
            used = d.used // (1024**3)
            total = d.total // (1024**3)
            return f"💾 Disk: {used}GB / {total}GB ({d.percent}% used)"

        if any(w in text for w in ["time", "clock"]):
            now = datetime.datetime.now()
            return f"🕐 Current time: {now.strftime('%H:%M:%S')}"

        if "date" in text:
            now = datetime.datetime.now()
            return f"📅 Today: {now.strftime('%A, %d %B %Y')}"

        if any(w in text for w in ["week", "sprint"]):
            return "📅 Current week: 49\nSprint: Week 49 — File Intelligence + Phone Bridge"

        if "version" in text:
            return ("⚡ Eonix OS v1.5.0-dev\n"
                    "AI: LightGBM v1.2\nAccuracy: 63.47%\nTests: 250+ passing")

        if any(w in text for w in ["ip", "network", "internet"]):
            try:
                ip = socket.gethostbyname(socket.gethostname())
                return f"🌐 IP address: {ip}"
            except Exception:
                return "🌐 No network detected"

        if "hostname" in text:
            return f"💻 Hostname: {socket.gethostname()}"

        # File intelligence commands
        if any(w in text for w in ["scan files", "index files", "file scan", "analyse files"]):
            def _do_scan():
                import sys as _s
                _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                if os.path.join(_root, "eonix-core") not in _s.path:
                    _s.path.insert(0, os.path.join(_root, "eonix-core"))
                from file_intelligence import EonixFileIntel
                intel = EonixFileIntel()
                idx = intel.scan()
                stats = idx["stats"]
                total = stats.get("total_count", 0)
                sz = stats.get("total_size_bytes", 0)
                sz_str = (f"{sz/(1024**3):.2f} GB" if sz > 1024**3
                          else f"{sz/(1024**2):.0f} MB")
                msg = (
                    f"🗂️ Scan complete!\n\n"
                    f"📊 {total} total files ({sz_str})\n"
                    f"📄 Docs:     {stats.get('documents', 0)}\n"
                    f"🖼️ Images:  {stats.get('images', 0)}\n"
                    f"💻 Code:    {stats.get('code', 0)}\n"
                    f"🎵 Audio:   {stats.get('audio', 0)}\n"
                    f"🎬 Video:   {stats.get('video', 0)}\n"
                    f"📦 Archives:{stats.get('archives', 0)}\n"
                    f"🗃️ Data:    {stats.get('data', 0)}")
                GLib.idle_add(self._add_eonix_msg, msg)
            import threading
            threading.Thread(target=_do_scan, daemon=True).start()
            return "🔍 Scanning your files..."

        if any(w in text for w in ["find file", "search file", "where is", "locate"]):
            import re, sys as _s
            words = text.split()
            query = " ".join(words[2:]) if len(words) > 2 else ""
            if not query:
                return "🔍 What file? Try: \"find file notes.txt\""
            _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            if os.path.join(_root, "eonix-core") not in _s.path:
                _s.path.insert(0, os.path.join(_root, "eonix-core"))
            from file_intelligence import EonixFileIntel
            intel = EonixFileIntel()
            results = intel.search(query)
            if not results:
                return f"❌ No files matching \"{query}\". Try 'scan files' first."
            lines = "\n".join(f"  {r['name']}\n  📁 {r['path']}" for r in results[:5])
            return f"🔍 Found {len(results)} match(es) for \"{query}\":\n\n{lines}"

        if any(w in text for w in ["largest files", "big files", "disk hogs"]):
            import sys as _s
            _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            if os.path.join(_root, "eonix-core") not in _s.path:
                _s.path.insert(0, os.path.join(_root, "eonix-core"))
            from file_intelligence import EonixFileIntel
            intel = EonixFileIntel()
            large = intel.get_largest(5)
            if not large:
                return "📦 No index yet. Try 'scan files' first."
            lines = "\n".join(f"  {f['name']} — {f['size']//(1024**2)} MB" for f in large)
            return f"🐘 Top 5 largest files:\n\n{lines}"

        if any(w in text for w in ["open smart files", "open file intel", "smart files"]):
            if self._desktop:
                GLib.idle_add(lambda: self._desktop._handle_dock_launch("SmartFiles"))
            return "🗂️ Opening Smart Files..."

        if any(w in text for w in ["duplicates", "duplicate files", "find duplicates"]):
            import sys as _s
            _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            if os.path.join(_root, "eonix-core") not in _s.path:
                _s.path.insert(0, os.path.join(_root, "eonix-core"))
            from file_intelligence import EonixFileIntel
            intel = EonixFileIntel()
            dupes = intel.get_duplicates()
            if not dupes:
                return "✅ No duplicate file names found!"
            lines = "\n".join(f"  {a['name']}" for a, b in dupes[:5])
            return f"⚠️ Found {len(dupes)} duplicate filename(s):\n\n{lines}"

        # File operations
        if any(w in text for w in ["list files", "show files", "ls", "what files"]):
            try:
                files = os.listdir(os.path.expanduser("~"))
                visible = sorted(f for f in files if not f.startswith("."))
                names = "\n".join(
                    f"  📁 {f}" if os.path.isdir(os.path.expanduser(f"~/{f}"))
                    else f"  📄 {f}"
                    for f in visible[:12])
                extra = f"\n  ...and {len(visible)-12} more" if len(visible) > 12 else ""
                return f"📂 Home folder ({len(visible)} items):\n{names}{extra}"
            except Exception as e:
                return f"❌ Error: {e}"

        if any(w in text for w in ["organize", "clean up", "sort files"]):
            return (
                "🗂️ Auto-organize is now live!\n\n"
                "Say 'open smart files' to preview what would be moved.\n"
                "Or try 'scan files' first to build the index.")

        # Voice / system commands
        if any(w in text for w in ["volume up", "louder"]):
            try:
                subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "+10%"],
                               capture_output=True, timeout=3)
                return "🔊 Volume up +10%"
            except Exception:
                return "🔊 Volume control not available"

        if any(w in text for w in ["volume down", "quieter", "softer"]):
            try:
                subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", "-10%"],
                               capture_output=True, timeout=3)
                return "🔉 Volume down -10%"
            except Exception:
                return "🔉 Volume control not available"

        if any(w in text for w in ["mute", "unmute"]):
            try:
                subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"],
                               capture_output=True, timeout=3)
                return "🔇 Mute toggled"
            except Exception:
                return "🔇 Mute not available"

        if "screenshot" in text:
            try:
                import datetime as _dt
                ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
                path = os.path.expanduser(f"~/Pictures/screenshot_{ts}.png")
                subprocess.run(["gnome-screenshot", "-f", path],
                               capture_output=True, timeout=5)
                return f"📸 Screenshot saved: {path}"
            except Exception:
                return "📸 Screenshot tool not available"

        if "lock screen" in text or "lock" in text:
            try:
                subprocess.Popen(["xdg-screensaver", "lock"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return "🔒 Screen locked"
            except Exception:
                return "🔒 Lock not available"

        if "shutdown" in text or "power off" in text:
            return ("⚠️ To shut down, run in terminal:\n"
                    "  sudo systemctl poweroff\n\n"
                    "Voice: say 'Hey Eonix, shutdown' then 'yes' to confirm.")

        if "restart" in text or "reboot" in text:
            return ("⚠️ To restart, run in terminal:\n"
                    "  sudo systemctl reboot")

        if any(w in text for w in ["battery", "power status"]):
            try:
                bat = psutil.sensors_battery()
                if bat:
                    plug = "🔌 Plugged in" if bat.power_plugged else "🔋 On battery"
                    return f"{plug}\n🔋 {bat.percent}% remaining"
                return "🔋 No battery detected (desktop)"
            except Exception:
                return "🔋 Battery info not available"

        # Utility
        if "clear" in text or "reset chat" in text:
            child = self._chat_box.get_first_child()
            while child:
                nxt = child.get_next_sibling()
                self._chat_box.remove(child)
                child = nxt
            self._history = []
            return "🧹 Chat cleared."

        if any(w in text for w in ["help", "what can you do", "commands"]):
            return (
                "🤖 Eonix AI Commands:\n\n"
                "📱 APPS\n"
                "  open terminal / files / settings\n"
                "  open mind / goals / notes\n\n"
                "⚙️ SETTINGS\n"
                "  dark mode on/off\n"
                "  font 12  (set font size)\n\n"
                "🖥️ SYSTEM INFO\n"
                "  show cpu / ram / disk\n"
                "  show time / date / version\n"
                "  show ip / hostname\n\n"
                "📁 FILES\n"
                "  list files / organize files\n\n"
                "📝 NOTES\n"
                "  open notes / my notes\n\n"
                "💬 OTHER\n"
                "  clear — reset chat\n"
                "  help — this message")

        # Fuzzy match
        for phrase in self.COMMANDS:
            if phrase in text:
                return self._match_command(phrase)

        # Greetings
        if any(g in text for g in [
            "hi", "hello", "hey", "how are you", "what's up",
            "good morning", "good evening", "good afternoon", "sup", "yo"]):
            import datetime as _dt
            hour = _dt.datetime.now().hour
            tod = "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"
            return (
                f"👋 Good {tod}! I'm Eonix AI — all good!\n\n"
                "Try:\n"
                "• \"open terminal\"\n"
                "• \"show cpu\"\n"
                "• \"find file notes.txt\"\n"
                "• \"scan files\"\n"
                "• \"dark mode on\"\n\n"
                "Or press Super for all apps.")

        # Thanks / farewell
        if any(w in text for w in [
            "thank", "thanks", "bye", "goodbye", "good night", "see you"]):
            return "😊 Always here! Press Super or Ctrl+Space to open me anytime."

        return (
            f"🤔 I didn't understand \"{text}\"\n\n"
            "Try: 'help' for all commands\n"
            "or: 'open terminal', 'show cpu', 'dark mode on'")

    def _write_setting(self, key, value):
        """AI writes directly to settings.json."""
        cfg_path = os.path.expanduser("~/.config/eonix/settings.json")
        try:
            cfg = {}
            if os.path.exists(cfg_path):
                with open(cfg_path, encoding="utf-8") as f:
                    cfg = json.load(f)
            cfg[key] = value
            os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        except Exception as e:
            print(f"[AI] settings write error: {e}")

    def _sys_cmd(self, t):
        """Fast system command check — returns command key or None."""
        pairs = [
            (["open terminal", "terminal", "launch terminal"], "terminal"),
            (["open files", "files", "launch files"], "files"),
            (["open notes", "my notes", "notes"], "notes"),
            (["open goals", "my goals", "show goals", "goals"], "goals"),
            (["open mind", "mind agent"], "mind"),
            (["open settings", "settings", "preferences"], "settings"),
            (["create a note", "new note", "add note", "make a note",
              "take a note", "write a note"], "create_note"),
            (["screenshot", "take screenshot"], "screenshot"),
            (["volume up", "louder"], "vol+"),
            (["volume down", "quieter"], "vol-"),
            (["mute", "unmute"], "mute"),
            (["lock screen", "lock"], "lock"),
            (["show cpu", "cpu usage", "cpu"], "cpu"),
            (["show ram", "memory", "ram"], "ram"),
        ]
        for patterns, cmd in pairs:
            if any(p in t for p in patterns):
                return cmd
        return None

    def _maybe_show_setup_banner(self):
        """Show Groq setup nudge if no API key is configured."""
        cfg_path = os.path.expanduser("~/.config/eonix/settings.json")
        has_key = False
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path) as f:
                    cfg = json.load(f)
                has_key = bool(cfg.get("groq_api_key", "").strip())
            except Exception:
                pass
        if not has_key:
            banner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            banner.set_margin_start(12)
            banner.set_margin_end(12)
            banner.set_margin_top(8)
            banner.set_margin_bottom(4)

            title = Gtk.Label(label="Unlock full AI \u2014 add a free Groq key")
            title.set_css_classes(["ai-banner-title"])
            title.set_halign(Gtk.Align.START)
            banner.append(title)

            steps = Gtk.Label(label=(
                "1. groq.com \u2192 sign up (free)\n"
                "2. API Keys \u2192 Create new key\n"
                "3. Settings \u2192 AI & Agents \u2192 paste key\n"
                "Gets you Llama 3.3 70B \u2014 best free LLM."))
            steps.set_css_classes(["settings-note"])
            steps.set_halign(Gtk.Align.START)
            steps.set_wrap(True)
            banner.append(steps)

            dismiss = Gtk.Button(label="Got it, ask away")
            dismiss.set_css_classes(["settings-action-btn"])
            dismiss.set_halign(Gtk.Align.START)
            dismiss.set_margin_top(4)
            dismiss.connect("clicked", lambda _: self._chat_box.remove(banner))
            banner.append(dismiss)
            self._chat_box.prepend(banner)

    def _llm_resp(self, text):
        """Handle LLM response."""
        if text:
            self._add_eonix_msg(text)
        self._entry.set_sensitive(True)

    def _llm_src(self, src):
        """Show source badge."""
        badge_map = {
            "groq": "Groq Llama 3.3 70B",
            "openai": "OpenAI GPT-4o-mini",
            "ollama": "Ollama (local)",
            "local": "TinyLlama (offline)",
            "offline": "Offline rules",
        }
        label = badge_map.get(src, src)
        if hasattr(self, "_src_lbl"):
            self._src_lbl.set_text(f"via {label}")
