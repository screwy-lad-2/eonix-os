"""Eonix Smart Files — file intelligence dashboard.

Stats cards, recent/largest files, live search,
and auto-organize preview. Uses EonixFileIntel.
"""
import os
import sys
import datetime
import threading

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib, Pango

# Ensure eonix-core is importable
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CORE = os.path.join(_ROOT, "eonix-core")
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)


class EonixFileIntelApp(Gtk.Box):

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.set_vexpand(True)
        self.set_hexpand(True)
        self._intel = None
        self._apply_css()
        self._build_ui()
        GLib.timeout_add(200, self._initial_scan)

    def _initial_scan(self):
        def _do():
            from file_intelligence import EonixFileIntel
            self._intel = EonixFileIntel()
            self._intel.scan()
            GLib.idle_add(self._refresh_ui)
        threading.Thread(target=_do, daemon=True).start()
        return False

    def _apply_css(self):
        css = b"""
        .fi-root { background: #080814; }
        .fi-header {
          background: #0d0d1a;
          border-bottom: 1px solid rgba(124,77,255,0.2);
          padding: 12px 16px;
        }
        .fi-title { font-size: 15px; font-weight: 700; color: #a78bfa; }
        .fi-stat-card {
          background: rgba(255,255,255,0.04);
          border: 1px solid rgba(124,77,255,0.12);
          border-radius: 12px; padding: 14px 16px;
          margin: 4px; min-width: 120px;
        }
        .fi-stat-number { font-size: 22px; font-weight: 700; color: #a78bfa; }
        .fi-stat-label { font-size: 11px; color: #666688; margin-top: 2px; }
        .fi-section-title {
          font-size: 12px; font-weight: 700; color: #555580;
          padding: 8px 16px 4px 16px; letter-spacing: 1px;
        }
        .fi-file-row {
          background: rgba(255,255,255,0.03); border-radius: 8px;
          padding: 8px 12px; margin: 2px 8px;
          border: 1px solid rgba(255,255,255,0.04);
        }
        .fi-file-row:hover { background: rgba(124,77,255,0.1); }
        .fi-file-name { font-size: 13px; color: #d0d0e8; font-weight: 500; }
        .fi-file-meta { font-size: 11px; color: #555580; }
        .fi-search {
          background: rgba(255,255,255,0.06);
          border: 1px solid rgba(124,77,255,0.3);
          border-radius: 12px; color: #e0e0e0;
          font-size: 13px; padding: 8px 16px; margin: 8px 16px;
        }
        .fi-organize-btn {
          background: rgba(124,77,255,0.3); color: #a78bfa;
          border-radius: 10px; padding: 8px 20px;
          font-size: 13px; font-weight: 700; margin: 8px 16px;
        }
        .fi-organize-btn:hover { background: rgba(124,77,255,0.5); }
        .fi-scanning { font-size: 13px; color: #555580; padding: 32px; }
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
            print(f"[SMART FILES] CSS failed: {e}")

    def _build_ui(self):
        self.set_css_classes(["fi-root"])

        # Header
        hdr = Gtk.Box(spacing=8)
        hdr.set_css_classes(["fi-header"])
        t = Gtk.Label(label="🗂️ Smart Files")
        t.set_css_classes(["fi-title"])
        t.set_hexpand(True)
        t.set_halign(Gtk.Align.START)
        hdr.append(t)

        scan_btn = Gtk.Button(label="🔄 Rescan")
        scan_btn.connect("clicked", lambda _: self._initial_scan())
        hdr.append(scan_btn)
        self.append(hdr)

        # Search
        self._search = Gtk.SearchEntry()
        self._search.set_css_classes(["fi-search"])
        self._search.set_placeholder_text("Search files...")
        self._search.connect("search-changed", self._on_search)
        self.append(self._search)

        # Stats row
        self._stats_row = Gtk.Box(spacing=0)
        self._stats_row.set_margin_start(8)
        self._stats_row.set_margin_end(8)
        self._stats_row.set_margin_top(8)
        self.append(self._stats_row)

        # Main scroll
        self._scroll = Gtk.ScrolledWindow()
        self._scroll.set_vexpand(True)
        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._scroll.set_child(self._content)
        self.append(self._scroll)

        # Organize button
        org_btn = Gtk.Button(label="✨ Auto-Organize Files")
        org_btn.set_css_classes(["fi-organize-btn"])
        org_btn.connect("clicked", self._on_organize)
        self.append(org_btn)

        # Placeholder
        lbl = Gtk.Label(label="⏳ Scanning files...")
        lbl.set_css_classes(["fi-scanning"])
        self._content.append(lbl)

    def _clear_box(self, box):
        child = box.get_first_child()
        while child:
            n = child.get_next_sibling()
            box.remove(child)
            child = n

    def _refresh_ui(self):
        if not self._intel:
            return
        stats = self._intel.get_stats()
        recent = self._intel.get_recent(8)
        largest = self._intel.get_largest(5)

        self._clear_box(self._stats_row)

        total = stats.get("total_count", 0)
        size_gb = stats.get("total_size_bytes", 0) / (1024**3)

        for val, lbl in [
            (str(total), "Total Files"),
            (f"{size_gb:.1f} GB", "Used Space"),
            (str(stats.get("documents", 0)), "Docs"),
            (str(stats.get("images", 0)), "Images"),
            (str(stats.get("code", 0)), "Code"),
            (str(stats.get("video", 0) + stats.get("audio", 0)), "Media"),
        ]:
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            card.set_css_classes(["fi-stat-card"])
            num = Gtk.Label(label=val)
            num.set_css_classes(["fi-stat-number"])
            lab = Gtk.Label(label=lbl)
            lab.set_css_classes(["fi-stat-label"])
            card.append(num)
            card.append(lab)
            self._stats_row.append(card)

        self._clear_box(self._content)

        self._add_section("RECENTLY MODIFIED")
        for f in recent:
            self._add_file_row(f)

        self._add_section("LARGEST FILES")
        for f in largest:
            self._add_file_row(f, show_size=True)

    def _add_section(self, title):
        lbl = Gtk.Label(label=title)
        lbl.set_css_classes(["fi-section-title"])
        lbl.set_halign(Gtk.Align.START)
        self._content.append(lbl)

    _CAT_ICONS = {
        "documents": "📄", "images": "🖼️", "audio": "🎵",
        "video": "🎬", "code": "💻", "archives": "📦",
        "data": "🗃️", "other": "📁",
    }

    def _add_file_row(self, f, show_size=False):
        row = Gtk.Box(spacing=8)
        row.set_css_classes(["fi-file-row"])
        ico = Gtk.Label(label=self._CAT_ICONS.get(f["cat"], "📄"))
        row.append(ico)
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        vbox.set_hexpand(True)
        name = Gtk.Label(label=f["name"])
        name.set_css_classes(["fi-file-name"])
        name.set_halign(Gtk.Align.START)
        name.set_ellipsize(Pango.EllipsizeMode.END)
        vbox.append(name)
        if show_size:
            sz = f["size"]
            sz_str = (f"{sz/(1024**2):.1f} MB" if sz > 1024**2
                      else f"{sz/1024:.1f} KB" if sz > 1024
                      else f"{sz} B")
            meta = Gtk.Label(label=f"{f['cat']} • {sz_str}")
        else:
            dt = datetime.datetime.fromtimestamp(f["mtime"])
            meta = Gtk.Label(label=f"{f['cat']} • {dt.strftime('%d %b %H:%M')}")
        meta.set_css_classes(["fi-file-meta"])
        meta.set_halign(Gtk.Align.START)
        vbox.append(meta)
        row.append(vbox)
        self._content.append(row)

    def _on_search(self, entry):
        if not self._intel:
            return
        q = entry.get_text().strip()
        if not q:
            self._refresh_ui()
            return
        results = self._intel.search(q)
        self._clear_box(self._content)
        self._add_section(f"SEARCH: \"{q}\" — {len(results)} results")
        for f in results[:20]:
            self._add_file_row(f)
        if not results:
            lbl = Gtk.Label(label="No files found.")
            lbl.set_css_classes(["fi-scanning"])
            self._content.append(lbl)

    def _on_organize(self, _):
        if not self._intel:
            return
        moves = self._intel.auto_organize(dry_run=True)
        self._clear_box(self._content)
        if not moves:
            self._add_section("✅ FILES ALREADY ORGANIZED")
            lbl = Gtk.Label(label="No files need to be moved.")
            lbl.set_css_classes(["fi-scanning"])
            self._content.append(lbl)
        else:
            self._add_section(f"📦 {len(moves)} FILES WOULD BE MOVED")
            cats = {}
            for m in moves:
                cats[m["cat"]] = cats.get(m["cat"], 0) + 1
            for cat, cnt in sorted(cats.items()):
                lbl = Gtk.Label(
                    label=f"  📁 organized/{cat}/ ← {cnt} files")
                lbl.set_halign(Gtk.Align.START)
                lbl.set_margin_start(16)
                lbl.set_margin_top(4)
                self._content.append(lbl)

            confirm = Gtk.Button(label="✅ Confirm Move")
            confirm.set_css_classes(["fi-organize-btn"])
            confirm.set_halign(Gtk.Align.CENTER)
            confirm.set_margin_top(12)
            confirm.connect("clicked", self._do_organize)
            self._content.append(confirm)

    def _do_organize(self, _):
        def _run():
            self._intel.auto_organize(dry_run=False)
            GLib.idle_add(self._initial_scan)
        threading.Thread(target=_run, daemon=True).start()
