#!/usr/bin/env python3
"""Persistent multi-device state store for Eonix SyncDaemon."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


EONIX_DIR = Path.home() / ".eonix"
SYNC_STATE_PATH = EONIX_DIR / "sync_state.json"
DEVICE_ID_PATH = EONIX_DIR / "device_id.txt"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(ts: str) -> datetime:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return datetime.fromtimestamp(0, tz=timezone.utc)


def _text_hash(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()[:16]


class StateStore:
    def __init__(self, state_path: Path = SYNC_STATE_PATH, device_id_path: Path = DEVICE_ID_PATH):
        self.state_path = state_path
        self.device_id_path = device_id_path
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.device_id_path.parent.mkdir(parents=True, exist_ok=True)

    def _default_state(self) -> Dict:
        source_device = self._read_device_id()
        return {
            "last_updated": "",
            "source_device": source_device,
            "active_goal": {},
            "active_goal_timestamp": "",
            "memory_summary": [],
            "scheduler_info": {},
            "known_devices": [],
            "sync_history": [],
        }

    def _read_device_id(self) -> str:
        if self.device_id_path.exists():
            return self.device_id_path.read_text(encoding="utf-8").strip() or ""
        return ""

    def _atomic_write_json(self, payload: Dict) -> None:
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.state_path)

    def _merge_memory(self, existing: List[Dict], incoming: List[Dict]) -> List[Dict]:
        merged: Dict[str, Dict] = {}
        for item in existing + incoming:
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            key = str(item.get("text_hash") or _text_hash(text))
            normalized = {
                "text": text,
                "importance": int(item.get("importance", 1)),
                "category": str(item.get("category", "general")),
                "text_hash": key,
            }
            prev = merged.get(key)
            if prev is None or int(normalized["importance"]) > int(prev.get("importance", 1)):
                merged[key] = normalized

        values = list(merged.values())
        values.sort(key=lambda x: int(x.get("importance", 1)), reverse=True)
        return values[:50]

    def _merge_scheduler(self, existing: Dict, incoming: Dict) -> Dict:
        if not incoming:
            return existing or {}
        cur_acc = float(existing.get("top3", 0.0) or 0.0)
        new_acc = float(incoming.get("top3", 0.0) or 0.0)
        if new_acc >= cur_acc:
            return incoming
        return existing

    def _append_history(self, state: Dict, source_device: str, fields_updated: List[str]) -> None:
        history = list(state.get("sync_history", []))
        history.append(
            {
                "timestamp": _utc_now(),
                "from_device": source_device,
                "fields_updated": fields_updated,
            }
        )
        state["sync_history"] = history[-20:]

    def write(self, brain_state: Dict, source_device: str) -> Dict:
        state = self.read()
        fields_updated: List[str] = []

        incoming_ts = str(brain_state.get("timestamp") or "")
        incoming_goal = brain_state.get("active_goal") if isinstance(brain_state.get("active_goal"), dict) else {}

        existing_goal_ts = str(state.get("active_goal_timestamp") or "")
        if incoming_goal and _parse_iso(incoming_ts) >= _parse_iso(existing_goal_ts):
            state["active_goal"] = incoming_goal
            state["active_goal_timestamp"] = incoming_ts
            fields_updated.append("active_goal")

        incoming_memory = brain_state.get("memory_summary") if isinstance(brain_state.get("memory_summary"), list) else []
        merged_memory = self._merge_memory(list(state.get("memory_summary", [])), incoming_memory)
        if merged_memory != list(state.get("memory_summary", [])):
            state["memory_summary"] = merged_memory
            fields_updated.append("memory_summary")

        incoming_sched = brain_state.get("scheduler_info") if isinstance(brain_state.get("scheduler_info"), dict) else {}
        merged_sched = self._merge_scheduler(dict(state.get("scheduler_info", {})), incoming_sched)
        if merged_sched != dict(state.get("scheduler_info", {})):
            state["scheduler_info"] = merged_sched
            fields_updated.append("scheduler_info")

        incoming_devices = brain_state.get("known_devices") if isinstance(brain_state.get("known_devices"), list) else []
        if incoming_devices:
            existing_devices = {str(d.get("device_id")): d for d in state.get("known_devices", []) if isinstance(d, dict)}
            for dev in incoming_devices:
                if isinstance(dev, dict) and dev.get("device_id"):
                    existing_devices[str(dev["device_id"])] = dev
            state["known_devices"] = list(existing_devices.values())
            fields_updated.append("known_devices")

        state["source_device"] = source_device
        state["last_updated"] = _utc_now()
        self._append_history(state, source_device=source_device, fields_updated=fields_updated)
        self._atomic_write_json(state)
        return state

    def read(self) -> Dict:
        if not self.state_path.exists():
            return self._default_state()
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return self._default_state()
        except Exception:
            return self._default_state()

        base = self._default_state()
        base.update(data)
        if not base.get("source_device"):
            base["source_device"] = self._read_device_id()
        return base

    def get_active_goal(self) -> Optional[Dict]:
        state = self.read()
        goal = state.get("active_goal")
        return goal if isinstance(goal, dict) and goal else None

    def get_memory_summary(self) -> List[Dict]:
        state = self.read()
        memory = state.get("memory_summary")
        return memory if isinstance(memory, list) else []

    def get_sync_history(self) -> List[Dict]:
        state = self.read()
        history = state.get("sync_history")
        if not isinstance(history, list):
            return []
        return history[-20:]

    def clear(self) -> None:
        state = self.read()
        preserved_device = str(state.get("source_device") or self._read_device_id())
        cleared = self._default_state()
        cleared["source_device"] = preserved_device
        cleared["last_updated"] = _utc_now()
        self._atomic_write_json(cleared)


# --------------------------- tests ---------------------------


def test_write_and_read_round_trip(tmp_path):
    store = StateStore(state_path=tmp_path / "sync_state.json", device_id_path=tmp_path / "device_id.txt")
    store.device_id_path.write_text("device-A", encoding="utf-8")

    payload = {
        "timestamp": "2026-03-21T10:00:00+00:00",
        "active_goal": {"id": "g1", "name": "Ship Week 15"},
        "memory_summary": [{"text": "deadline Apr 1", "importance": 3, "category": "deadline"}],
        "scheduler_info": {"version": "v1.1", "top3": 0.61},
    }
    store.write(payload, source_device="device-A")

    out = store.read()
    assert out["active_goal"]["name"] == "Ship Week 15"
    assert out["scheduler_info"]["version"] == "v1.1"
    assert out["source_device"] == "device-A"


def test_atomic_write_no_corruption(tmp_path):
    store = StateStore(state_path=tmp_path / "sync_state.json", device_id_path=tmp_path / "device_id.txt")
    for i in range(5):
        payload = {
            "timestamp": f"2026-03-21T10:00:0{i}+00:00",
            "active_goal": {"id": "g1", "name": f"Goal {i}"},
            "memory_summary": [{"text": f"m-{i}", "importance": i + 1}],
            "scheduler_info": {"version": f"v{i}", "top3": 0.5 + (i * 0.01)},
        }
        store.write(payload, source_device="device-A")

    parsed = json.loads((tmp_path / "sync_state.json").read_text(encoding="utf-8"))
    assert parsed["active_goal"]["name"].startswith("Goal")


def test_sync_history_capped_at_20(tmp_path):
    store = StateStore(state_path=tmp_path / "sync_state.json", device_id_path=tmp_path / "device_id.txt")
    for i in range(35):
        payload = {
            "timestamp": f"2026-03-21T10:00:{i:02d}+00:00",
            "active_goal": {"id": "g1", "name": f"Goal {i}"},
            "memory_summary": [{"text": f"mem-{i}", "importance": 1}],
            "scheduler_info": {"version": "v1", "top3": 0.1},
        }
        store.write(payload, source_device=f"device-{i}")

    assert len(store.get_sync_history()) == 20


def test_clear_preserves_device_id(tmp_path):
    store = StateStore(state_path=tmp_path / "sync_state.json", device_id_path=tmp_path / "device_id.txt")
    store.device_id_path.write_text("device-preserved", encoding="utf-8")
    store.write(
        {
            "timestamp": "2026-03-21T10:00:00+00:00",
            "active_goal": {"id": "g1", "name": "Goal"},
            "memory_summary": [{"text": "m", "importance": 2}],
            "scheduler_info": {"version": "v1", "top3": 0.66},
        },
        source_device="device-preserved",
    )

    store.clear()
    out = store.read()
    assert out["source_device"] == "device-preserved"
    assert out["active_goal"] == {}
    assert out["memory_summary"] == []
