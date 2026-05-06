"""Eonix Files — unified file manager with AI intelligence.

3 tabs: Browse, AI Scan, Search. Replaces both old Files + SmartFiles.
"""
import os
import sys
import threading
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib, Pango

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CORE = os.path.join(_ROOT, "eonix-core")
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)


class EonixFilesApp(Gtk.Box):
    HIDDEN_SHOW = False

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_vexpand(True)
        self.set_hexpand(True)
        self._history = []
        self._hist_pos = -1
        self._current = os.path.expanduser("~")
        self._intel = None
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
        .ef-nav-btn:hover { background: rgba(124,77,255,0.25); color: #e0e0ff; }
        .ef-nav-btn:disabled { color: rgba(160,160,192,0.3); background: transparent; }
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
        .ef-sidebar-item:hover { background: rgba(124,77,255,0.15); color: #d0d0f0; }
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
        .ef-tab-switcher button {
          background: rgba(255,255,255,0.04); color: #8888a8;
          border: none; border-radius: 8px;
          padding: 4px 14px; font-size: 12px; margin: 0 3px;
        }
        .ef-tab-switcher button:checked {
          background: rgba(124,77,255,0.25); color: #d0b0ff; font-weight: 600;
        }
        .ef-list-row {
          background: rgba(255,255,255,0.03); border-radius: 8px;
          padding: 6px 10px; margin: 1px 0;
        }
        .ef-list-row:hover { background: rgba(124,77,255,0.12); }
        .fi-stat-chip {
          background: rgba(255,255,255,0.04);
          border: 1px solid rgba(124,77,255,0.12);
          border-radius: 10px; padding: 8px 14px;
          font-size: 13px; color: #a78bfa;
        }
        .fi-section-title {
          font-size: 12px; font-weight: 700; color: #555580;
          padding: 8px 0 4px 0; letter-spacing: 1px;
        }
        """
        try:
            provider = Gtk.CssProvider()
            provider.load_from_data(css)
            display = Gdk.Display.get_default()
            if display:
                Gtk.StyleContext.add_provider_for_display(
                    display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        except Exception as e:
            print(f"[EONIX FILES] CSS failed: {e}")

    def _build_ui(self):
        self.set_css_classes(["ef-root"])

        # Toolbar
        toolbar = Gtk.Box(spacing=6)
        toolbar.set_css_classes(["ef-toolbar"])
        self._btn_back = Gtk.Button(label="\u2039")
        self._btn_back.set_css_classes(["ef-nav-btn"])
        self._btn_back.connect("clicked", self._go_back)
        self._btn_back.set_sensitive(False)
        toolbar.append(self._btn_back)
        self._btn_fwd = Gtk.Button(label="\u203a")
        self._btn_fwd.set_css_classes(["ef-nav-btn"])
        self._btn_fwd.connect("clicked", self._go_forward)
        self._btn_fwd.set_sensitive(False)
        toolbar.append(self._btn_fwd)
        btn_up = Gtk.Button(label="\u2191")
        btn_up.set_css_classes(["ef-nav-btn"])
        btn_up.connect("clicked", self._go_up)
        toolbar.append(btn_up)
        btn_home = Gtk.Button(label="\u2302")
        btn_home.set_css_classes(["ef-nav-btn"])
        btn_home.connect("clicked", lambda _: self._navigate(os.path.expanduser("~")))
        toolbar.append(btn_home)
        self._path_entry = Gtk.Entry()
        self._path_entry.set_css_classes(["ef-path-bar"])
        self._path_entry.set_hexpand(True)
        self._path_entry.connect("activate", self._on_path_activate)
        toolbar.append(self._path_entry)
        btn_dot = Gtk.Button(label="\u00b7/\u00b7")
        btn_dot.set_css_classes(["ef-nav-btn"])
        btn_dot.connect("clicked", self._toggle_hidden)
        toolbar.append(btn_dot)
        self.append(toolbar)

        # Body: sidebar + tabbed right panel
        body = Gtk.Box(spacing=0)
        body.set_vexpand(True)

        # Sidebar
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        sidebar.set_css_classes(["ef-sidebar"])
        sidebar.set_margin_top(8)
        for icon, name, path in [
            ("\u2302", "Home", os.path.expanduser("~")),
            ("\U0001f5a5\ufe0f", "Desktop", os.path.expanduser("~/Desktop")),
            ("\U0001f4c4", "Documents", os.path.expanduser("~/Documents")),
            ("\u2b07\ufe0f", "Downloads", os.path.expanduser("~/Downloads")),
            ("\U0001f5bc\ufe0f", "Pictures", os.path.expanduser("~/Pictures")),
            ("\U0001f3b5", "Music", os.path.expanduser("~/Music")),
            ("\U0001f4f9", "Videos", os.path.expanduser("~/Videos")),
            ("\U0001f5d1\ufe0f", "Trash", os.path.expanduser("~/.local/share/Trash/files")),
            ("\U0001f4bb", "Root", "/"),
        ]:
            btn = Gtk.Button(label=f"{icon}  {name}")
            btn.set_css_classes(["ef-sidebar-item"])
            btn.set_halign(Gtk.Align.FILL)
            btn.connect("clicked", lambda _, p=path: self._navigate(p))
            sidebar.append(btn)
        body.append(sidebar)

        # Right panel with tabs
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        right.set_hexpand(True)
        right.set_vexpand(True)

        switcher = Gtk.StackSwitcher()
        switcher.set_css_classes(["ef-tab-switcher"])
        switcher.set_margin_start(12)
        switcher.set_margin_top(6)
        switcher.set_margin_bottom(4)

        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self._stack.set_transition_duration(180)
        self._stack.set_vexpand(True)

        # Tab 1: Browse
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
        self._stack.add_titled(self._file_scroll, "browse", "\U0001f4c1 Browse")

        # Tab 2: AI Scan
        self._stack.add_titled(self._build_ai_panel(), "ai", "\U0001f916 AI Scan")

        # Tab 3: Search
        self._stack.add_titled(self._build_search_panel(), "search", "\U0001f50d Search")

        switcher.set_stack(self._stack)
        right.append(switcher)
        right.append(self._stack)
        body.append(right)
        self.append(body)

        # Statusbar
        self._statusbar = Gtk.Label(label="Ready")
        self._statusbar.set_css_classes(["ef-statusbar"])
        self._statusbar.set_halign(Gtk.Align.START)
        self.append(self._statusbar)

    # ── AI Panel ────────────────────────────────────
    def _build_ai_panel(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_vexpand(True)

        stats_row = Gtk.Box(spacing=8)
        stats_row.set_margin_start(14)
        stats_row.set_margin_end(14)
        stats_row.set_margin_top(12)
        stats_row.set_margin_bottom(8)
        self._stat_total = Gtk.Label(label="\U0001f4e6 \u2014 files")
        self._stat_size = Gtk.Label(label="\U0001f4be \u2014 MB")
        self._stat_types = Gtk.Label(label="\U0001f5c2\ufe0f \u2014 types")
        for lbl in [self._stat_total, self._stat_size, self._stat_types]:
            lbl.set_css_classes(["fi-stat-chip"])
            lbl.set_hexpand(True)
            stats_row.append(lbl)
        box.append(stats_row)

        btn_row = Gtk.Box(spacing=8)
        btn_row.set_margin_start(14)
        btn_row.set_margin_end(14)
        btn_row.set_margin_bottom(8)
        for label, cb in [
            ("\U0001f504 Rescan", self._ai_rescan),
            ("\U0001f4ca Largest", self._ai_show_largest),
            ("\U0001f501 Duplicates", self._ai_show_dupes),
            ("\u2728 Auto-Organize", self._ai_organize),
        ]:
            b = Gtk.Button(label=label)
            b.set_css_classes(["ef-nav-btn"])
            b.connect("clicked", cb)
            btn_row.append(b)
        box.append(btn_row)

        self._ai_scroll = Gtk.ScrolledWindow()
        self._ai_scroll.set_vexpand(True)
        self._ai_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._ai_content.set_margin_start(14)
        self._ai_content.set_margin_end(14)
        self._ai_scroll.set_child(self._ai_content)
        box.append(self._ai_scroll)

        self._ai_status = Gtk.Label(label="  Click Rescan to index your files.")
        self._ai_status.set_css_classes(["ef-statusbar"])
        self._ai_status.set_halign(Gtk.Align.START)
        box.append(self._ai_status)
        return box

    # ── Search Panel ────────────────────────────────
    def _build_search_panel(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_vexpand(True)
        bar = Gtk.Box(spacing=8)
        bar.set_margin_start(14)
        bar.set_margin_end(14)
        bar.set_margin_top(10)
        bar.set_margin_bottom(8)
        self._global_search = Gtk.Entry()
        self._global_search.set_css_classes(["ef-path-bar"])
        self._global_search.set_placeholder_text("\U0001f50d  Search all files...")
        self._global_search.set_hexpand(True)
        self._global_search.connect("activate", self._on_global_search)
        bar.append(self._global_search)
        box.append(bar)
        self._search_scroll = Gtk.ScrolledWindow()
        self._search_scroll.set_vexpand(True)
        self._search_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._search_content.set_margin_start(14)
        self._search_content.set_margin_end(14)
        self._search_scroll.set_child(self._search_content)
        box.append(self._search_scroll)
        hint = Gtk.Label(label="  Press Enter to search all files.")
        hint.set_css_classes(["ef-statusbar"])
        hint.set_halign(Gtk.Align.START)
        box.append(hint)
        return box

    def _on_global_search(self, entry):
        q = entry.get_text().strip()
        self._clear_box(self._search_content)
        if not q or len(q) < 2:
            return
        import subprocess
        try:
            r = subprocess.run(
                ["find", os.path.expanduser("~"), "-iname", f"*{q}*",
                 "-not", "-path", "*/.*", "-maxdepth", "6"],
                capture_output=True, text=True, timeout=5)
            hits = [l.strip() for l in r.stdout.split("\n") if l.strip()][:30]
        except Exception:
            hits = []
        if not hits:
            lbl = Gtk.Label(label=f'  No files found for "{q}"')
            lbl.set_css_classes(["ef-statusbar"])
            lbl.set_halign(Gtk.Align.START)
            self._search_content.append(lbl)
            return
        for path in hits:
            row = Gtk.Box(spacing=8)
            row.set_css_classes(["ef-list-row"])
            row.set_margin_bottom(2)
            name = os.path.basename(path)
            ico = Gtk.Label(label="\U0001f4c1" if os.path.isdir(path) else "\U0001f4c4")
            ico.set_margin_start(4)
            nlbl = Gtk.Label(label=name)
            nlbl.set_css_classes(["ef-file-label"])
            nlbl.set_hexpand(True)
            nlbl.set_halign(Gtk.Align.START)
            nlbl.set_ellipsize(Pango.EllipsizeMode.END)
            plbl = Gtk.Label(label=os.path.dirname(path))
            plbl.set_css_classes(["ef-statusbar"])
            plbl.set_halign(Gtk.Align.END)
            plbl.set_ellipsize(Pango.EllipsizeMode.START)
            plbl.set_size_request(200, -1)
            row.append(ico)
            row.append(nlbl)
            row.append(plbl)
            _p = path
            ctrl = Gtk.GestureClick()
            ctrl.connect("pressed", lambda g, n, x, y, p=_p:
                         self._navigate(os.path.dirname(p) if not os.path.isdir(p) else p))
            row.add_controller(ctrl)
            self._search_content.append(row)

    # ── AI methods ──────────────────────────────────
    def _get_intel(self):
        if not self._intel:
            from file_intelligence import EonixFileIntel
            self._intel = EonixFileIntel()
        return self._intel

    def _ai_rescan(self, btn=None):
        self._ai_status.set_text("  \U0001f504 Scanning files...")
        def _scan():
            try:
                intel = self._get_intel()
                intel.scan(os.path.expanduser("~"))
                stats = intel.get_stats()
                GLib.idle_add(self._update_ai_stats, stats)
            except Exception as e:
                GLib.idle_add(self._ai_status.set_text, f"  \u274c Scan error: {e}")
        threading.Thread(target=_scan, daemon=True).start()

    def _update_ai_stats(self, stats):
        total = stats.get("total_count", 0)
        sz = stats.get("total_size_bytes", 0) / (1024**2)
        cats = sum(1 for k in ["documents","images","audio","video","code","archives","data"]
                   if stats.get(k, 0) > 0)
        self._stat_total.set_text(f"\U0001f4e6 {total:,} files")
        self._stat_size.set_text(f"\U0001f4be {sz:.1f} MB")
        self._stat_types.set_text(f"\U0001f5c2\ufe0f {cats} types")
        self._ai_status.set_text(f"  \u2705 Scan complete \u2014 {total:,} files indexed.")

    def _ai_show_largest(self, btn=None):
        intel = self._get_intel()
        files = intel.get_largest(n=15)
        self._clear_box(self._ai_content)
        h = Gtk.Label(label="\U0001f4ca LARGEST FILES")
        h.set_css_classes(["fi-section-title"])
        h.set_halign(Gtk.Align.START)
        self._ai_content.append(h)
        for f in files:
            row = Gtk.Box(spacing=6)
            row.set_css_classes(["ef-list-row"])
            lbl = Gtk.Label(label=f["name"])
            lbl.set_hexpand(True)
            lbl.set_halign(Gtk.Align.START)
            lbl.set_css_classes(["ef-file-label"])
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            sz = Gtk.Label(label=f'{f["size"]//(1024**2)} MB')
            sz.set_css_classes(["ef-statusbar"])
            row.append(Gtk.Label(label="\U0001f4c4"))
            row.append(lbl)
            row.append(sz)
            self._ai_content.append(row)

    def _ai_show_dupes(self, btn=None):
        intel = self._get_intel()
        dupes = intel.get_duplicates()
        self._clear_box(self._ai_content)
        h = Gtk.Label(label=f"\U0001f501 DUPLICATES ({len(dupes)} groups)")
        h.set_css_classes(["fi-section-title"])
        h.set_halign(Gtk.Align.START)
        self._ai_content.append(h)
        for a, b in dupes[:15]:
            row = Gtk.Box(spacing=6)
            row.set_css_classes(["ef-list-row"])
            lbl = Gtk.Label(label=a["name"])
            lbl.set_hexpand(True)
            lbl.set_halign(Gtk.Align.START)
            lbl.set_css_classes(["ef-file-label"])
            row.append(Gtk.Label(label="\u26a0\ufe0f"))
            row.append(lbl)
            self._ai_content.append(row)

    def _ai_organize(self, btn=None):
        intel = self._get_intel()
        moves = intel.auto_organize(dry_run=True)
        self._ai_status.set_text(f"  \u2728 {len(moves)} files would be moved to ~/organized/")

    # ── Browse navigation ───────────────────────────
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
        self._clear_box(self._file_grid)
        try:
            entries = os.listdir(path)
        except PermissionError:
            self._statusbar.set_text("\u26d4 Permission denied")
            return
        if not self.HIDDEN_SHOW:
            entries = [e for e in entries if not e.startswith(".")]
        entries.sort(key=lambda e: (0 if os.path.isdir(os.path.join(path, e)) else 1, e.lower()))
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
        self._statusbar.set_text(f"  {len(entries)} items  \u2014  {path}")

    def _get_icon(self, name, is_dir):
        if is_dir:
            return {"Desktop":"\U0001f5a5\ufe0f","Documents":"\U0001f4c4","Downloads":"\u2b07\ufe0f",
                    "Pictures":"\U0001f5bc\ufe0f","Music":"\U0001f3b5","Videos":"\U0001f4f9"}.get(name,"\U0001f4c1")
        ext = os.path.splitext(name)[1].lower()
        return {".py":"\U0001f40d",".js":"\U0001f4dc",".html":"\U0001f310",".css":"\U0001f3a8",
                ".json":"\U0001f4cb",".md":"\U0001f4dd",".txt":"\U0001f4c4",".pdf":"\U0001f4d5",
                ".zip":"\U0001f4e6",".tar":"\U0001f4e6",".jpg":"\U0001f5bc\ufe0f",".jpeg":"\U0001f5bc\ufe0f",
                ".png":"\U0001f5bc\ufe0f",".mp3":"\U0001f3b5",".mp4":"\U0001f3ac",".sh":"\u26a1",
                ".db":"\U0001f5c3\ufe0f",".iso":"\U0001f4bf"}.get(ext,"\U0001f4c4")

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
            self._statusbar.set_text(f"\u26a0\ufe0f Path not found: {path}")

    def _open_file(self, path):
        try:
            import subprocess
            subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._statusbar.set_text(f"\U0001f4c2 Opening {os.path.basename(path)}")
        except Exception as e:
            self._statusbar.set_text(f"\u26a0\ufe0f Cannot open: {e}")

    def _clear_box(self, box):
        child = box.get_first_child()
        while child:
            n = child.get_next_sibling()
            box.remove(child)
            child = n
