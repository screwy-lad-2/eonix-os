"""Eonix Files — custom GTK4 file manager.

Replaces Nautilus for UI consistency.
Runs inside EonixWM (traffic-light window chrome).
Supports navigation, bookmarks, hidden file toggle,
file-type icons, and xdg-open for file launching.
"""
import os
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib, Pango


class EonixFilesApp(Gtk.Box):
    """Eonix Files — custom file manager inside EonixWM."""

    HIDDEN_SHOW = False

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_vexpand(True)
        self.set_hexpand(True)
        self._history = []
        self._hist_pos = -1
        self._current = os.path.expanduser("~")
        self._apply_css()
        self._build_ui()
        self._navigate(self._current)

    def _apply_css(self):
        css = b"""
        .ef-root { background: #0d0d1a; color: #d0d0e8; }
        .ef-toolbar {
          background: #0a0a16;
          border-bottom: 1px solid rgba(124,77,255,0.18);
          padding: 6px 10px; min-height: 40px;
        }
        .ef-nav-btn {
          background: rgba(255,255,255,0.06); border-radius: 8px;
          color: #a0a0c0; padding: 4px 8px;
          min-width: 28px; min-height: 28px; border: none;
        }
        .ef-nav-btn:hover {
          background: rgba(124,77,255,0.25); color: #e0e0ff;
        }
        .ef-nav-btn:disabled {
          color: rgba(160,160,192,0.3); background: transparent;
        }
        .ef-path-bar {
          background: rgba(255,255,255,0.05);
          border: 1px solid rgba(124,77,255,0.2);
          border-radius: 10px; color: #c0c0d8;
          font-size: 12px; padding: 4px 12px; caret-color: #a78bfa;
        }
        .ef-path-bar:focus { border-color: #7c4dff; }
        .ef-sidebar {
          background: #0a0a16;
          border-right: 1px solid rgba(124,77,255,0.12);
          min-width: 160px; max-width: 160px;
        }
        .ef-sidebar-item {
          background: transparent; border-radius: 8px;
          padding: 7px 12px; margin: 2px 6px;
          color: #8888a8; font-size: 12px; text-align: left; border: none;
        }
        .ef-sidebar-item:hover {
          background: rgba(124,77,255,0.15); color: #d0d0f0;
        }
        .ef-sidebar-item-active {
          background: rgba(124,77,255,0.25); color: #e0e0ff; font-weight: 600;
        }
        .ef-file-icon { font-size: 22px; margin-bottom: 4px; }
        .ef-file-label { font-size: 11px; color: #c0c0d8; }
        .ef-grid-item {
          background: transparent; border-radius: 10px;
          padding: 8px 4px; margin: 2px;
          min-width: 80px; max-width: 80px; border: none;
        }
        .ef-grid-item:hover { background: rgba(124,77,255,0.18); }
        .ef-statusbar {
          background: #0a0a16;
          border-top: 1px solid rgba(124,77,255,0.12);
          padding: 4px 12px; font-size: 11px;
          color: #555580; min-height: 24px;
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
            print(f"[EONIX FILES] CSS failed: {e}")

    def _build_ui(self):
        self.set_css_classes(["ef-root"])

        # ── Toolbar
        toolbar = Gtk.Box(spacing=6)
        toolbar.set_css_classes(["ef-toolbar"])

        self._btn_back = Gtk.Button(label="‹")
        self._btn_back.set_css_classes(["ef-nav-btn"])
        self._btn_back.connect("clicked", self._go_back)
        self._btn_back.set_sensitive(False)
        toolbar.append(self._btn_back)

        self._btn_fwd = Gtk.Button(label="›")
        self._btn_fwd.set_css_classes(["ef-nav-btn"])
        self._btn_fwd.connect("clicked", self._go_forward)
        self._btn_fwd.set_sensitive(False)
        toolbar.append(self._btn_fwd)

        btn_up = Gtk.Button(label="↑")
        btn_up.set_css_classes(["ef-nav-btn"])
        btn_up.set_tooltip_text("Go up one level")
        btn_up.connect("clicked", self._go_up)
        toolbar.append(btn_up)

        btn_home = Gtk.Button(label="⌂")
        btn_home.set_css_classes(["ef-nav-btn"])
        btn_home.set_tooltip_text("Home folder")
        btn_home.connect("clicked",
                         lambda _: self._navigate(os.path.expanduser("~")))
        toolbar.append(btn_home)

        self._path_entry = Gtk.Entry()
        self._path_entry.set_css_classes(["ef-path-bar"])
        self._path_entry.set_hexpand(True)
        self._path_entry.connect("activate", self._on_path_activate)
        toolbar.append(self._path_entry)

        btn_dotfiles = Gtk.Button(label="·/·")
        btn_dotfiles.set_css_classes(["ef-nav-btn"])
        btn_dotfiles.set_tooltip_text("Toggle hidden files")
        btn_dotfiles.connect("clicked", self._toggle_hidden)
        toolbar.append(btn_dotfiles)

        self.append(toolbar)

        # ── Body: sidebar + grid
        body = Gtk.Box(spacing=0)
        body.set_vexpand(True)

        # Sidebar
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        sidebar.set_css_classes(["ef-sidebar"])
        sidebar.set_margin_top(8)

        bookmarks = [
            ("⌂",  "Home",      os.path.expanduser("~")),
            ("🖥️", "Desktop",   os.path.expanduser("~/Desktop")),
            ("📄",  "Documents", os.path.expanduser("~/Documents")),
            ("⬇️",  "Downloads", os.path.expanduser("~/Downloads")),
            ("🖼️",  "Pictures",  os.path.expanduser("~/Pictures")),
            ("🎵",  "Music",     os.path.expanduser("~/Music")),
            ("📹",  "Videos",    os.path.expanduser("~/Videos")),
            ("🗑️",  "Trash",     os.path.expanduser("~/.local/share/Trash/files")),
            ("💻",  "Root",      "/"),
        ]
        self._sidebar_btns = []
        for icon, name, path in bookmarks:
            btn = Gtk.Button(label=f"{icon}  {name}")
            btn.set_css_classes(["ef-sidebar-item"])
            btn.set_halign(Gtk.Align.FILL)
            btn.connect("clicked", lambda _, p=path: self._navigate(p))
            sidebar.append(btn)
            self._sidebar_btns.append((btn, path))
        body.append(sidebar)

        # File grid
        self._file_scroll = Gtk.ScrolledWindow()
        self._file_scroll.set_vexpand(True)
        self._file_scroll.set_hexpand(True)
        self._file_grid = Gtk.FlowBox()
        self._file_grid.set_max_children_per_line(20)
        self._file_grid.set_min_children_per_line(4)
        self._file_grid.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._file_grid.set_column_spacing(0)
        self._file_grid.set_row_spacing(0)
        self._file_grid.set_margin_top(8)
        self._file_grid.set_margin_start(8)
        self._file_scroll.set_child(self._file_grid)
        body.append(self._file_scroll)
        self.append(body)

        # Statusbar
        self._statusbar = Gtk.Label(label="Ready")
        self._statusbar.set_css_classes(["ef-statusbar"])
        self._statusbar.set_halign(Gtk.Align.START)
        self.append(self._statusbar)

    # ── Navigation ──────────────────────────────────────

    def _navigate(self, path):
        if not os.path.isdir(path):
            self._open_file(path)
            return
        if self._hist_pos < len(self._history) - 1:
            self._history = self._history[:self._hist_pos + 1]
        self._history.append(path)
        self._hist_pos = len(self._history) - 1
        self._current = path
        self._refresh()

    def _refresh(self):
        path = self._current
        self._path_entry.set_text(path)
        self._btn_back.set_sensitive(self._hist_pos > 0)
        self._btn_fwd.set_sensitive(self._hist_pos < len(self._history) - 1)

        # Clear grid
        child = self._file_grid.get_first_child()
        while child:
            n = child.get_next_sibling()
            self._file_grid.remove(child)
            child = n

        try:
            entries = os.listdir(path)
        except PermissionError:
            self._statusbar.set_text("⛔ Permission denied")
            return

        if not self.HIDDEN_SHOW:
            entries = [e for e in entries if not e.startswith(".")]

        entries.sort(key=lambda e: (
            0 if os.path.isdir(os.path.join(path, e)) else 1, e.lower()))

        for name in entries:
            full = os.path.join(path, name)
            is_dir = os.path.isdir(full)
            icon = self._get_icon(name, is_dir)

            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            box.set_valign(Gtk.Align.START)

            ico_lbl = Gtk.Label(label=icon)
            ico_lbl.set_css_classes(["ef-file-icon"])
            box.append(ico_lbl)

            name_lbl = Gtk.Label(label=name)
            name_lbl.set_css_classes(["ef-file-label"])
            name_lbl.set_max_width_chars(9)
            name_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            name_lbl.set_justify(Gtk.Justification.CENTER)
            box.append(name_lbl)

            btn = Gtk.Button()
            btn.set_child(box)
            btn.set_css_classes(["ef-grid-item"])
            btn.connect("clicked", lambda _, p=full: self._navigate(p))
            self._file_grid.append(btn)

        self._statusbar.set_text(f"  {len(entries)} items  —  {path}")

    # ── File icons ──────────────────────────────────────

    def _get_icon(self, name, is_dir):
        if is_dir:
            special = {
                "Desktop": "🖥️", "Documents": "📄", "Downloads": "⬇️",
                "Pictures": "🖼️", "Music": "🎵", "Videos": "📹",
                "Trash": "🗑️",
            }
            return special.get(name, "📁")
        ext = os.path.splitext(name)[1].lower()
        return {
            ".py": "🐍", ".js": "📜", ".ts": "📘", ".html": "🌐",
            ".css": "🎨", ".json": "📋", ".md": "📝", ".txt": "📄",
            ".pdf": "📕", ".zip": "📦", ".tar": "📦", ".gz": "📦",
            ".jpg": "🖼️", ".jpeg": "🖼️", ".png": "🖼️", ".gif": "🖼️",
            ".svg": "🎨", ".mp3": "🎵", ".wav": "🎵", ".mp4": "🎬",
            ".mkv": "🎬", ".sh": "⚡", ".db": "🗃️", ".sqlite": "🗃️",
            ".iso": "💿", ".deb": "📦", ".csv": "📊", ".xlsx": "📊",
        }.get(ext, "📄")

    # ── Navigation handlers ─────────────────────────────

    def _go_back(self, _):
        if self._hist_pos > 0:
            self._hist_pos -= 1
            self._current = self._history[self._hist_pos]
            self._refresh()

    def _go_forward(self, _):
        if self._hist_pos < len(self._history) - 1:
            self._hist_pos += 1
            self._current = self._history[self._hist_pos]
            self._refresh()

    def _go_up(self, _):
        parent = os.path.dirname(self._current)
        if parent != self._current:
            self._navigate(parent)

    def _toggle_hidden(self, _):
        self.HIDDEN_SHOW = not self.HIDDEN_SHOW
        self._refresh()

    def _on_path_activate(self, entry):
        path = os.path.expanduser(entry.get_text().strip())
        if os.path.exists(path):
            self._navigate(path)
        else:
            self._statusbar.set_text(f"⚠️ Path not found: {path}")

    def _open_file(self, path):
        """Open file with xdg-open."""
        try:
            import subprocess
            subprocess.Popen(["xdg-open", path],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            self._statusbar.set_text(
                f"📂 Opening {os.path.basename(path)}")
        except Exception as e:
            self._statusbar.set_text(f"⚠️ Cannot open: {e}")
