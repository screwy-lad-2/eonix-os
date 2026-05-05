"""Eonix App Launcher — Spotlight-style.

Floating overlay triggered by Super key or ⚡ topbar button.
Search + app grid with fuzzy filtering.
"""
import gi
import os

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib


class EonixLauncher(Gtk.Window):
    """Eonix App Launcher — press Super key."""

    ALL_APPS = [
        ("⚡", "Terminal",  "EonixShell",  "Shell, bash, command line"),
        ("📁", "Files",     "Files",       "File manager, browse, folders"),
        ("🧠", "Goals",     "Goals",       "Goals, tasks, productivity"),
        ("⚙️", "Settings", "Settings",    "Preferences, appearance, theme"),
        ("📊", "Hub",       "Hub",         "AI Hub, model, accuracy"),
        ("🤖", "MIND",      "MIND",        "AI agent, mind, assistant"),
        ("💬", "AI Chat",   "AIChat",      "Chat, ask, assistant, help"),
        ("📝", "Notes",     "Notes",       "Notes, write, text, memo"),
        ("🖥️", "System",   "System",      "System info, hardware, kernel"),
    ]

    def __init__(self, desktop_ref=None):
        super().__init__()
        self._desktop = desktop_ref
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_default_size(560, 400)
        self.set_css_classes(["launcher-root"])
        self._apply_css()
        self._build_ui()

        # Close on Escape
        esc = Gtk.EventControllerKey()
        esc.connect("key-pressed", self._on_key)
        self.add_controller(esc)

    def _apply_css(self):
        css = b"""
        .launcher-root {
          background: rgba(8, 8, 20, 0.97);
          border: 1px solid rgba(124,77,255,0.4);
          border-radius: 20px;
        }
        .launcher-search {
          background: rgba(255,255,255,0.07);
          border: 1px solid rgba(124,77,255,0.35);
          border-radius: 14px;
          color: #e0e0e0;
          font-size: 16px;
          padding: 12px 20px;
          caret-color: #a78bfa;
        }
        .launcher-search:focus {
          border-color: #7c4dff;
        }
        .launcher-app-btn {
          background: rgba(255,255,255,0.04);
          border: 1px solid rgba(255,255,255,0.06);
          border-radius: 14px;
          padding: 14px 10px;
          color: #c0c0d8;
          font-size: 11px;
          min-width: 80px;
          min-height: 80px;
        }
        .launcher-app-btn:hover {
          background: rgba(124,77,255,0.25);
          border-color: rgba(124,77,255,0.5);
          color: #e0e0ff;
        }
        .launcher-icon {
          font-size: 28px;
          margin-bottom: 6px;
        }
        .launcher-hint {
          font-size: 11px;
          color: rgba(160,160,192,0.5);
          margin-top: 8px;
        }
        """
        try:
            provider = Gtk.CssProvider()
            provider.load_from_data(css)
            display = Gdk.Display.get_default()
            if display:
                Gtk.StyleContext.add_provider_for_display(
                    display, provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_USER)
        except Exception as e:
            print(f"[LAUNCHER] CSS failed: {e}")

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        root.set_margin_top(20)
        root.set_margin_bottom(20)
        root.set_margin_start(20)
        root.set_margin_end(20)

        # Search bar
        self._search = Gtk.SearchEntry()
        self._search.set_css_classes(["launcher-search"])
        self._search.set_placeholder_text("🔍  Search apps...")
        self._search.connect("search-changed", self._on_search)
        self._search.connect("activate", self._on_search_activate)
        root.append(self._search)

        # App grid
        self._grid = Gtk.FlowBox()
        self._grid.set_max_children_per_line(5)
        self._grid.set_min_children_per_line(3)
        self._grid.set_selection_mode(Gtk.SelectionMode.NONE)
        self._grid.set_column_spacing(8)
        self._grid.set_row_spacing(8)
        root.append(self._grid)

        # Hint
        hint = Gtk.Label(
            label="Press Esc to close  •  Enter to launch first result")
        hint.set_css_classes(["launcher-hint"])
        root.append(hint)

        self.set_child(root)
        self._populate(self.ALL_APPS)

        # Auto-focus search
        GLib.idle_add(self._search.grab_focus)

    def _populate(self, apps):
        # Clear grid
        child = self._grid.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._grid.remove(child)
            child = nxt
        # Add app buttons
        for icon, name, cmd, _ in apps:
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            box.set_halign(Gtk.Align.CENTER)
            ico = Gtk.Label(label=icon)
            ico.set_css_classes(["launcher-icon"])
            lbl = Gtk.Label(label=name)
            box.append(ico)
            box.append(lbl)
            btn = Gtk.Button()
            btn.set_child(box)
            btn.set_css_classes(["launcher-app-btn"])
            btn.connect("clicked", lambda _, c=cmd: self._launch(c))
            self._grid.append(btn)

    def _on_search(self, entry):
        query = entry.get_text().lower().strip()
        if not query:
            self._populate(self.ALL_APPS)
            return
        filtered = [
            app for app in self.ALL_APPS
            if query in app[1].lower() or query in app[3].lower()
        ]
        self._populate(filtered or self.ALL_APPS)

    def _on_search_activate(self, entry):
        # Launch first visible app
        first = self._grid.get_first_child()
        if first:
            child = first.get_child()
            if child:
                child.activate()

    def _launch(self, cmd):
        self.close()
        if self._desktop:
            GLib.idle_add(lambda: self._desktop._handle_dock_launch(cmd))

    def _on_key(self, ctrl, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False
