"""Memory browser widget for GoalPanel and standalone desktop usage."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import httpx

GTK_AVAILABLE = False
try:  # pragma: no cover
    import gi  # type: ignore

    gi.require_version("Gtk", "4.0")
    gi.require_version("GLib", "2.0")
    from gi.repository import GLib, Gtk  # type: ignore

    GTK_AVAILABLE = True
except Exception:  # pragma: no cover
    GLib = Gtk = None  # type: ignore

HEADLESS_DEFAULT = not GTK_AVAILABLE or os.environ.get("EONIX_HEADLESS", "0") == "1" or not os.environ.get("DISPLAY")


def _load_memory_class():
    # eonix-mind has a hyphen in its folder name, so import by file path.
    root = Path(__file__).resolve().parents[1]
    target = root / "eonix-mind" / "memory.py"
    if not target.exists():
        raise RuntimeError("Memory backend not found")

    import importlib.util

    spec = importlib.util.spec_from_file_location("eonix_memory_module", target)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load memory backend")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.EonixMemory


EonixMemory = _load_memory_class()


@dataclass
class MemoryItem:
    memory_id: str
    text: str
    category: str
    timestamp: str
    importance: int


class _StubDialog:
    def __init__(self):
        self.opened = False

    def present(self):
        self.opened = True


class _StubWindow:
    def __init__(self):
        self.visible = False

    def present(self):
        self.visible = True


class MemoryWidget:
    CATEGORIES = ["All", "deadline", "preference", "project", "person", "fact", "command"]

    def __init__(
        self,
        headless: bool = HEADLESS_DEFAULT,
        memory_backend: Any | None = None,
        http_client: Optional[httpx.Client] = None,
    ):
        self.headless = headless
        self.memory = memory_backend or EonixMemory()
        self.http = http_client or httpx.Client(timeout=3.0)
        self.items: list[MemoryItem] = []
        self.filtered_items: list[MemoryItem] = []
        self.selected_category = "All"
        self.last_query = ""
        self.add_dialog = _StubDialog()
        self.container = _StubWindow()
        self.standalone_window = _StubWindow()
        if GTK_AVAILABLE and not headless:
            self._build_ui()
        self.load_memories()
        if GTK_AVAILABLE and not headless:
            GLib.timeout_add_seconds(60, self._periodic_refresh)  # type: ignore

    def _build_ui(self) -> None:  # pragma: no cover
        self.container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)  # type: ignore
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)  # type: ignore
        title = Gtk.Label(label="🧠 Memory")  # type: ignore
        add_btn = Gtk.Button(label="+ Add")  # type: ignore
        add_btn.connect("clicked", lambda _: self.open_add_dialog())  # type: ignore
        self.search_entry = Gtk.SearchEntry()  # type: ignore
        self.search_entry.connect("search-changed", lambda entry: self.search(entry.get_text()))  # type: ignore
        header.append(title)  # type: ignore
        header.append(add_btn)  # type: ignore
        header.append(self.search_entry)  # type: ignore
        self.container.append(header)  # type: ignore

    def _periodic_refresh(self) -> bool:
        self.load_memories()
        return True

    def _item_from_dict(self, data: dict[str, Any], idx: int) -> MemoryItem:
        text = str(data.get("text", ""))
        category = str(data.get("category", "fact"))
        timestamp = str(data.get("timestamp", ""))
        memory_id = str(data.get("memory_id", f"mem-{idx}"))
        score = float(data.get("score", 1.0))
        importance = int(round(max(1.0, min(3.0, score * 3.0))))
        return MemoryItem(memory_id=memory_id, text=text, category=category, timestamp=timestamp, importance=importance)

    def load_memories(self) -> None:
        raw = self.memory.recall("", n=50)
        self.items = [self._item_from_dict(item, idx) for idx, item in enumerate(raw)]
        self.apply_category_filter(self.selected_category)

    def memory_count(self) -> int:
        try:
            stats = self.memory.stats()
            return int(stats.get("total_memories", len(self.items)))
        except Exception:
            return len(self.items)

    def apply_category_filter(self, category: str) -> list[MemoryItem]:
        self.selected_category = category
        if category == "All":
            self.filtered_items = list(self.items)
            return self.filtered_items

        raw = self.memory.recall_by_category(category)
        self.filtered_items = [self._item_from_dict(item, idx) for idx, item in enumerate(raw)]
        return self.filtered_items

    def open_add_dialog(self) -> None:
        self.add_dialog.present()

    def add_memory(self, text: str, category: str, importance: int) -> str:
        mem_id = self.memory.remember(text=text, category=category, importance=int(importance))
        self.load_memories()
        return mem_id

    def delete_memory(self, memory_id: str) -> None:
        self.memory.forget(memory_id)
        self.load_memories()

    def search(self, query: str) -> list[MemoryItem]:
        self.last_query = query
        q = query.strip()
        if not q:
            self.apply_category_filter(self.selected_category)
            return self.filtered_items

        try:
            res = self.http.get("http://127.0.0.1:7736/context/search", params={"q": q})
            if res.status_code == 200 and isinstance(res.json(), list):
                payload = res.json()
                self.filtered_items = [
                    MemoryItem(
                        memory_id=f"ctx-{i}",
                        text=str(item.get("text") or item.get("payload") or item),
                        category=str(item.get("type", "context")),
                        timestamp=str(item.get("timestamp", "")),
                        importance=1,
                    )
                    for i, item in enumerate(payload)
                ]
                return self.filtered_items
        except Exception:
            pass

        # Fallback local search if ContextAgent is down.
        ql = q.lower()
        self.filtered_items = [x for x in self.items if ql in x.text.lower()]
        return self.filtered_items

    def open_standalone(self) -> None:
        if GTK_AVAILABLE and not self.headless:  # pragma: no cover
            win = Gtk.Window(title="Eonix Memory")  # type: ignore
            win.set_default_size(400, 600)
            win.set_child(self.container)
            win.present()
            self.standalone_window = win  # type: ignore
            return
        self.standalone_window.present()


class MemoryWidgetApp:
    def __init__(self, headless: bool = HEADLESS_DEFAULT):
        self.widget = MemoryWidget(headless=headless)

    def run(self) -> int:
        self.widget.open_standalone()
        if GTK_AVAILABLE and not self.widget.headless:  # pragma: no cover
            Gtk.main()  # type: ignore
        return 0


def main(argv: list[str] | None = None) -> int:
    app = MemoryWidgetApp()
    return app.run()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))


# ---------------------------
# Inline unit tests (pytest)
# ---------------------------


def test_memory_widget_loads_without_crash(tmp_path):
    backend = EonixMemory(db_path=str(tmp_path / "mem"), collection_name="mem_widget_t1")
    w = MemoryWidget(headless=True, memory_backend=backend)
    assert w.memory_count() >= 0


def test_add_memory_dialog_opens(tmp_path):
    backend = EonixMemory(db_path=str(tmp_path / "mem"), collection_name="mem_widget_t2")
    w = MemoryWidget(headless=True, memory_backend=backend)
    w.open_add_dialog()
    assert w.add_dialog.opened is True


def test_category_filter_returns_subset(tmp_path):
    backend = EonixMemory(db_path=str(tmp_path / "mem"), collection_name="mem_widget_t3")
    w = MemoryWidget(headless=True, memory_backend=backend)
    w.add_memory("deadline next week", "deadline", 3)
    w.add_memory("prefers concise", "preference", 2)
    out = w.apply_category_filter("deadline")
    assert out
    assert all(item.category == "deadline" for item in out)


def test_search_calls_context_api(tmp_path):
    class FakeClient:
        def __init__(self):
            self.called = False

        def get(self, url, params):
            self.called = True

            class Resp:
                status_code = 200

                @staticmethod
                def json():
                    return [{"text": "context hit", "type": "context"}]

            return Resp()

    backend = EonixMemory(db_path=str(tmp_path / "mem"), collection_name="mem_widget_t4")
    client = FakeClient()
    w = MemoryWidget(headless=True, memory_backend=backend, http_client=client)  # type: ignore[arg-type]
    out = w.search("context")
    assert client.called is True
    assert out and out[0].text == "context hit"


def test_memory_widget_delete_memory(tmp_path):
    backend = EonixMemory(db_path=str(tmp_path / "mem"), collection_name="mem_widget_t5")
    w = MemoryWidget(headless=True, memory_backend=backend)
    mem_id = w.add_memory("delete me", "fact", 1)
    w.delete_memory(mem_id)
    assert all("delete me" not in x.text for x in w.items)


def test_memory_widget_standalone_flag(tmp_path):
    backend = EonixMemory(db_path=str(tmp_path / "mem"), collection_name="mem_widget_t6")
    w = MemoryWidget(headless=True, memory_backend=backend)
    w.open_standalone()
    assert w.standalone_window.visible is True
