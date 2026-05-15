# -*- coding: utf-8 -*-
"""Eonix Phone App — contacts list, detail view, dialpad."""
import os
import json

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib

CONTACTS_FILE = os.path.expanduser("~/.config/eonix/contacts.json")

DEMO_CONTACTS = [
    {"name": "Alice Chen", "number": "+91 98765 43210", "last": "Yesterday"},
    {"name": "Bob Kumar", "number": "+91 87654 32109", "last": "Monday"},
    {"name": "Carol Singh", "number": "+91 76543 21098", "last": "2 days ago"},
    {"name": "MIND Agent", "number": "localhost:7750", "last": "Always online"},
]


class PhoneApp(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL)
        self.set_vexpand(True)
        self.set_hexpand(True)
        self._contacts = self._load()
        self._apply_css()
        self._build()

    def _load(self):
        if os.path.exists(CONTACTS_FILE):
            try:
                with open(CONTACTS_FILE, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return [c.copy() for c in DEMO_CONTACTS]

    def _save(self):
        os.makedirs(os.path.dirname(CONTACTS_FILE), exist_ok=True)
        with open(CONTACTS_FILE, "w", encoding="utf-8") as f:
            json.dump(self._contacts, f, indent=2)

    def _build(self):
        # Left sidebar: contacts list
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        left.set_css_classes(["phone-sidebar"])
        left.set_size_request(185, -1)

        hdr = Gtk.Label(label="CONTACTS")
        hdr.set_css_classes(["phone-section-title"])
        hdr.set_margin_start(14)
        hdr.set_margin_top(14)
        hdr.set_margin_bottom(8)
        hdr.set_halign(Gtk.Align.START)
        left.append(hdr)

        self._lb = Gtk.ListBox()
        self._lb.set_css_classes(["phone-list"])
        self._lb.set_vexpand(True)
        self._lb.connect("row-selected", self._on_select)

        sw = Gtk.ScrolledWindow()
        sw.set_vexpand(True)
        sw.set_child(self._lb)
        left.append(sw)

        add_btn = Gtk.Button(label="+ Add Contact")
        add_btn.set_css_classes(["phone-add-btn"])
        add_btn.set_margin_start(8)
        add_btn.set_margin_end(8)
        add_btn.set_margin_bottom(8)
        add_btn.connect("clicked", self._add_dialog)
        left.append(add_btn)

        self._fill_list()

        # Right side: detail + dialpad
        self._right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self._right.set_css_classes(["phone-detail"])
        self._right.set_vexpand(True)
        self._right.set_hexpand(True)
        self._right.set_margin_start(12)
        self._right.set_margin_end(12)
        self._right.set_margin_top(12)
        self._right.set_margin_bottom(12)
        self._show_dialpad()

        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        self.append(left)
        self.append(sep)
        self.append(self._right)

    def _fill_list(self):
        while True:
            row = self._lb.get_row_at_index(0)
            if row is None:
                break
            self._lb.remove(row)
        for c in self._contacts:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            box.set_margin_start(12)
            box.set_margin_end(8)
            box.set_margin_top(8)
            box.set_margin_bottom(8)
            nl = Gtk.Label(label=c["name"])
            nl.set_css_classes(["phone-contact-name"])
            nl.set_halign(Gtk.Align.START)
            ll = Gtk.Label(label=c.get("last", ""))
            ll.set_css_classes(["phone-contact-last"])
            ll.set_halign(Gtk.Align.START)
            box.append(nl)
            box.append(ll)
            row.set_child(box)
            row._contact = c
            self._lb.append(row)

    def _on_select(self, lb, row):
        if row and hasattr(row, "_contact"):
            self._show_detail(row._contact)

    def _clear_right(self):
        while True:
            ch = self._right.get_first_child()
            if ch is None:
                break
            self._right.remove(ch)

    def _show_detail(self, c):
        self._clear_right()

        av = Gtk.Label(label=c["name"][0].upper())
        av.set_css_classes(["phone-avatar"])
        av.set_size_request(64, 64)
        av.set_margin_top(16)
        av.set_halign(Gtk.Align.CENTER)
        self._right.append(av)

        nl = Gtk.Label(label=c["name"])
        nl.set_css_classes(["phone-detail-name"])
        nl.set_halign(Gtk.Align.CENTER)
        self._right.append(nl)

        num = Gtk.Label(label=c.get("number", ""))
        num.set_css_classes(["phone-detail-num"])
        num.set_halign(Gtk.Align.CENTER)
        self._right.append(num)

        btn_row = Gtk.Box(spacing=8)
        btn_row.set_halign(Gtk.Align.CENTER)
        btn_row.set_margin_top(14)
        for lbl, cls in [("Call", "phone-call-btn"), ("SMS", "phone-msg-btn"), ("Del", "phone-del-btn")]:
            b = Gtk.Button(label=lbl)
            b.set_css_classes([cls])
            _l, _c = lbl, c
            b.connect("clicked", lambda w, l=_l, ct=_c: self._action(l, ct))
            btn_row.append(b)
        self._right.append(btn_row)

    def _action(self, act, c):
        if act == "Del":
            self._contacts = [x for x in self._contacts if x["name"] != c["name"]]
            self._save()
            self._fill_list()
            self._show_dialpad()
            return
        # Show info dialog for Call/SMS
        info = Gtk.Label(label=f"{act}: {c['name']}\nNumber: {c.get('number', '')}\n(VoIP not connected yet)")
        info.set_css_classes(["phone-dial-hint"])
        info.set_halign(Gtk.Align.CENTER)
        info.set_margin_top(20)
        self._clear_right()
        self._right.append(info)
        GLib.timeout_add(2500, lambda: self._show_detail(c) or False)

    def _show_dialpad(self):
        self._clear_right()

        hint = Gtk.Label(label="Select a contact\nor dial a number")
        hint.set_css_classes(["phone-dial-hint"])
        hint.set_halign(Gtk.Align.CENTER)
        hint.set_margin_top(20)
        hint.set_margin_bottom(12)
        self._right.append(hint)

        self._dial_entry = Gtk.Entry()
        self._dial_entry.set_placeholder_text("Enter number...")
        self._dial_entry.set_css_classes(["phone-dial-entry"])
        self._dial_entry.set_hexpand(True)
        self._dial_entry.set_margin_start(12)
        self._dial_entry.set_margin_end(12)
        self._right.append(self._dial_entry)

        grid = Gtk.Grid()
        grid.set_column_spacing(8)
        grid.set_row_spacing(8)
        grid.set_halign(Gtk.Align.CENTER)
        grid.set_margin_top(10)
        keys = [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"], ["*", "0", "#"]]
        for r, row in enumerate(keys):
            for col, k in enumerate(row):
                b = Gtk.Button(label=k)
                b.set_css_classes(["phone-dialpad-btn"])
                b.set_size_request(52, 44)
                b.connect("clicked", lambda w, k=k: self._dial_entry.set_text(
                    self._dial_entry.get_text() + k))
                grid.attach(b, col, r, 1, 1)
        self._right.append(grid)

        call = Gtk.Button(label="CALL")
        call.set_css_classes(["phone-call-btn"])
        call.set_margin_top(10)
        call.set_halign(Gtk.Align.CENTER)
        call.set_size_request(100, 40)
        self._right.append(call)

    def _add_dialog(self, _):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_start(16)
        box.set_margin_end(16)
        box.set_margin_top(12)

        lbl = Gtk.Label(label="ADD CONTACT")
        lbl.set_css_classes(["phone-section-title"])
        lbl.set_halign(Gtk.Align.START)
        box.append(lbl)

        ne = Gtk.Entry()
        ne.set_placeholder_text("Name")
        ne.set_css_classes(["phone-dial-entry"])
        box.append(ne)

        pe = Gtk.Entry()
        pe.set_placeholder_text("Number")
        pe.set_css_classes(["phone-dial-entry"])
        box.append(pe)

        sv = Gtk.Button(label="Save Contact")
        sv.set_css_classes(["phone-call-btn"])

        def _save(_):
            nm = ne.get_text().strip()
            if nm:
                self._contacts.append({"name": nm, "number": pe.get_text().strip(), "last": "Just added"})
                self._save()
                self._fill_list()
                self._clear_right()
                self._show_dialpad()

        sv.connect("clicked", _save)
        box.append(sv)

        self._clear_right()
        self._right.append(box)

    def _apply_css(self):
        css = b"""
        .phone-sidebar { background: rgba(10,10,20,0.6); min-width: 185px; }
        .phone-section-title { font-size: 11px; font-weight: 700; color: #444488; letter-spacing: 1.5px; }
        .phone-list { background: transparent; border: none; }
        .phone-contact-name { font-size: 13px; font-weight: 600; color: #d0d0e8; }
        .phone-contact-last { font-size: 11px; color: #555577; }
        .phone-add-btn { background: rgba(124,77,255,0.12); color: #a78bfa; border: 1px solid rgba(124,77,255,0.2); border-radius: 8px; font-size: 12px; padding: 6px; }
        .phone-avatar { background: rgba(124,77,255,0.2); color: #a78bfa; font-size: 26px; font-weight: 700; border-radius: 9999px; border: 2px solid rgba(124,77,255,0.3); }
        .phone-detail-name { font-size: 17px; font-weight: 700; color: #e0e0f0; margin-top: 4px; }
        .phone-detail-num { font-size: 12px; color: #6060a0; }
        .phone-call-btn { background: rgba(80,250,123,0.15); color: #50fa7b; border: 1px solid rgba(80,250,123,0.25); border-radius: 8px; padding: 6px 14px; font-size: 12px; font-weight: 700; }
        .phone-msg-btn { background: rgba(139,233,253,0.1); color: #8be9fd; border: 1px solid rgba(139,233,253,0.2); border-radius: 8px; padding: 6px 14px; font-size: 12px; }
        .phone-del-btn { background: rgba(255,85,85,0.1); color: #ff5555; border: 1px solid rgba(255,85,85,0.2); border-radius: 8px; padding: 6px 14px; font-size: 12px; }
        .phone-dial-hint { font-size: 13px; color: #444466; }
        .phone-dial-entry { font-size: 18px; font-weight: 700; color: #c0c0e0; background: rgba(255,255,255,0.04); border: 1px solid rgba(124,77,255,0.2); border-radius: 8px; padding: 8px 12px; }
        .phone-dialpad-btn { background: rgba(255,255,255,0.04); color: #b0b0d0; border: 1px solid rgba(255,255,255,0.06); border-radius: 8px; font-size: 14px; font-weight: 600; }
        .phone-detail { background: transparent; }
        """
        pr = Gtk.CssProvider()
        pr.load_from_data(css)
        from gi.repository import Gdk
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(display, pr, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
