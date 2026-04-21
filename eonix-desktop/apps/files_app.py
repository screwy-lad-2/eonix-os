import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio
import os

class EonixFiles(Gtk.Box):
    def __init__(self):
        super().__init__(
            orientation=Gtk.Orientation.HORIZONTAL)
        self.set_css_classes(["eonix-files-root"])
        self.set_vexpand(True)
        self.set_hexpand(True)
        self.current_path = os.path.expanduser("~")

        # ── Sidebar ───────────────────────────
        sidebar = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=4)
        sidebar.set_css_classes(["files-sidebar"])
        sidebar.set_size_request(160, -1)

        for label, path in [
            ("🏠  Home",      os.path.expanduser("~")),
            ("🖥️  Root",      "/"),
            ("📁  Documents", os.path.expanduser("~/Documents")),
            ("📥  Downloads", os.path.expanduser("~/Downloads")),
            ("⚙️  Eonix",     "/opt/eonix"),
        ]:
            btn = Gtk.Button(label=label)
            btn.set_css_classes(["files-nav-btn"])
            btn.connect(
                "clicked",
                lambda b, p=path: self._nav(p))
            sidebar.append(btn)

        self.append(sidebar)

        # ── Main panel ────────────────────────
        main = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL)
        main.set_hexpand(True)

        # Path bar
        self.path_bar = Gtk.Label(
            label=self.current_path)
        self.path_bar.set_css_classes(
            ["files-pathbar"])
        self.path_bar.set_halign(Gtk.Align.START)
        self.path_bar.set_margin_start(12)
        self.path_bar.set_margin_top(8)
        self.path_bar.set_margin_bottom(8)
        main.append(self.path_bar)

        # File grid
        self.flow = Gtk.FlowBox()
        self.flow.set_max_children_per_line(6)
        self.flow.set_min_children_per_line(3)
        self.flow.set_selection_mode(
            Gtk.SelectionMode.SINGLE)
        self.flow.set_css_classes(["files-grid"])
        self.flow.connect(
            "child-activated", self._on_activate)

        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.flow)
        scroll.set_vexpand(True)
        main.append(scroll)
        self.append(main)

        self._load_dir(self.current_path)

    def _nav(self, path):
        if os.path.isdir(path):
            self._load_dir(path)

    def _load_dir(self, path):
        self.current_path = path
        self.path_bar.set_label(path)
        # Clear
        while child := self.flow.get_child_at_index(0):
            self.flow.remove(child)
        # Load entries
        try:
            entries = sorted(os.scandir(path),
                key=lambda e: (
                    not e.is_dir(), e.name.lower()))
        except PermissionError:
            return
        for entry in entries[:120]:
            if entry.name.startswith("."):
                continue
            icon = "📁" if entry.is_dir() else (
                "🐍" if entry.name.endswith(".py")
                else "📄")
            box = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=4)
            box.set_css_classes(["file-item"])
            box.set_size_request(80, 80)
            lbl_i = Gtk.Label(label=icon)
            lbl_i.set_css_classes(["file-icon"])
            lbl_n = Gtk.Label(
                label=entry.name[:12] + (
                    "…" if len(entry.name)>12 else ""))
            lbl_n.set_css_classes(["file-name"])
            box.append(lbl_i)
            box.append(lbl_n)
            row = Gtk.FlowBoxChild()
            row.set_child(box)
            row._path = os.path.join(
                path, entry.name)
            row._is_dir = entry.is_dir()
            self.flow.append(row)

    def _on_activate(self, fb, child):
        if hasattr(child, "_path"):
            if child._is_dir:
                self._load_dir(child._path)
