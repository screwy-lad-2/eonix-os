"""Eonix Notes — Persistent notes app.

Notes stored in ~/.config/eonix/notes.json.
AI can read and search notes via commands.
"""
import gi
import os
import json
import datetime

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk, GLib


class EonixNotes(Gtk.Box):

    NOTES_PATH = os.path.expanduser("~/.config/eonix/notes.json")

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.set_vexpand(True)
        self.set_hexpand(True)
        self._notes = self._load()
        self._current_idx = None
        self._apply_css()
        self._build_ui()

    def _load(self):
        try:
            with open(self.NOTES_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return [
                {"title": "Welcome",
                 "body": "This is your first Eonix note.\n"
                         "AI can read these and help you find information.",
                 "created": "2026-04-26"}
            ]

    def _save(self):
        os.makedirs(os.path.dirname(self.NOTES_PATH), exist_ok=True)
        with open(self.NOTES_PATH, "w", encoding="utf-8") as f:
            json.dump(self._notes, f, indent=2)

    def _apply_css(self):
        css = b"""
        .notes-sidebar {
          background: #0a0a16;
          border-right: 1px solid rgba(124,77,255,0.15);
          min-width: 180px;
        }
        .notes-item {
          background: transparent;
          border-radius: 8px;
          padding: 8px 12px;
          margin: 2px 6px;
          font-size: 12px;
          color: #a0a0c0;
        }
        .notes-item:hover {
          background: rgba(124,77,255,0.12);
          color: #e0e0e0;
        }
        .notes-item-active {
          background: rgba(124,77,255,0.25);
          color: #e0e0e0;
          font-weight: 600;
        }
        .notes-editor {
          background: #080814;
          color: #e0e0e0;
          font-family: monospace;
          font-size: 13px;
          padding: 16px;
        }
        .notes-toolbar {
          background: #0d0d1a;
          border-bottom: 1px solid rgba(124,77,255,0.15);
          padding: 6px 10px;
        }
        .notes-add-btn {
          background: rgba(124,77,255,0.3);
          color: #a78bfa;
          border-radius: 8px;
          padding: 4px 10px;
          font-size: 12px;
          font-weight: 700;
        }
        .notes-del-btn {
          background: rgba(161,44,123,0.2);
          color: #d163a7;
          border-radius: 8px;
          padding: 4px 10px;
          font-size: 12px;
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
            print(f"[NOTES] CSS failed: {e}")

    def _build_ui(self):
        # Sidebar
        sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        sidebar.set_css_classes(["notes-sidebar"])

        toolbar = Gtk.Box(spacing=6)
        toolbar.set_css_classes(["notes-toolbar"])
        toolbar.set_margin_start(6)
        toolbar.set_margin_end(6)

        lbl = Gtk.Label(label="📝 Notes")
        lbl.set_hexpand(True)
        lbl.set_halign(Gtk.Align.START)
        lbl.set_css_classes(["ai-title"])
        toolbar.append(lbl)

        add_btn = Gtk.Button(label="+")
        add_btn.set_css_classes(["notes-add-btn"])
        add_btn.connect("clicked", self._add_note)
        toolbar.append(add_btn)
        sidebar.append(toolbar)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        self._list_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self._list_box.set_margin_top(4)
        scroll.set_child(self._list_box)
        sidebar.append(scroll)
        self.append(sidebar)

        # Editor
        editor_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        editor_box.set_hexpand(True)
        editor_box.set_vexpand(True)

        # Title entry
        self._title_entry = Gtk.Entry()
        self._title_entry.set_placeholder_text("Note title...")
        self._title_entry.set_css_classes(["ai-input"])
        self._title_entry.set_margin_start(16)
        self._title_entry.set_margin_end(16)
        self._title_entry.set_margin_top(12)
        self._title_entry.set_margin_bottom(8)
        self._title_entry.connect("changed", self._on_title_changed)
        editor_box.append(self._title_entry)

        # Body text view
        scroll2 = Gtk.ScrolledWindow()
        scroll2.set_vexpand(True)
        self._text_view = Gtk.TextView()
        self._text_view.set_css_classes(["notes-editor"])
        self._text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self._text_view.set_left_margin(16)
        self._text_view.set_right_margin(16)
        self._text_view.set_top_margin(8)
        self._text_view.get_buffer().connect("changed", self._on_body_changed)
        scroll2.set_child(self._text_view)
        editor_box.append(scroll2)

        # Delete button
        del_btn = Gtk.Button(label="🗑 Delete note")
        del_btn.set_css_classes(["notes-del-btn"])
        del_btn.set_halign(Gtk.Align.CENTER)
        del_btn.set_margin_top(8)
        del_btn.set_margin_bottom(10)
        del_btn.connect("clicked", self._delete_note)
        editor_box.append(del_btn)

        self.append(editor_box)
        self._refresh_list()
        if self._notes:
            self._load_note(0)

    def _refresh_list(self):
        child = self._list_box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self._list_box.remove(child)
            child = nxt
        for i, note in enumerate(self._notes):
            btn = Gtk.Button(label=note.get("title", "Untitled"))
            css = ["notes-item"]
            if i == self._current_idx:
                css.append("notes-item-active")
            btn.set_css_classes(css)
            btn.set_halign(Gtk.Align.FILL)
            btn.connect("clicked", lambda _, idx=i: self._load_note(idx))
            self._list_box.append(btn)

    def _load_note(self, idx):
        if 0 <= idx < len(self._notes):
            self._current_idx = idx
            note = self._notes[idx]
            self._title_entry.set_text(note.get("title", ""))
            buf = self._text_view.get_buffer()
            buf.set_text(note.get("body", ""))
            self._refresh_list()

    def _on_title_changed(self, entry):
        if self._current_idx is not None and self._current_idx < len(self._notes):
            self._notes[self._current_idx]["title"] = entry.get_text()
            self._save()
            self._refresh_list()

    def _on_body_changed(self, buf):
        if self._current_idx is not None and self._current_idx < len(self._notes):
            start = buf.get_start_iter()
            end = buf.get_end_iter()
            self._notes[self._current_idx]["body"] = buf.get_text(start, end, True)
            self._save()

    def _add_note(self, *_):
        self._notes.append({
            "title": "New Note",
            "body": "",
            "created": datetime.date.today().isoformat()
        })
        self._save()
        self._refresh_list()
        self._load_note(len(self._notes) - 1)

    def _delete_note(self, *_):
        if self._current_idx is not None and self._notes:
            self._notes.pop(self._current_idx)
            self._save()
            self._refresh_list()
            if self._notes:
                self._load_note(0)
            else:
                self._current_idx = None
                self._title_entry.set_text("")
                self._text_view.get_buffer().set_text("")
