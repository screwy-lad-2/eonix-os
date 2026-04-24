#!/usr/bin/env python3
"""Eonix Hub: unified backend for dashboard REST + live websocket updates."""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import aiohttp
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = Path(__file__).resolve().parent / "static"
AUTO_RETRAIN_SCRIPT = ROOT / "eonix-core" / "scheduler" / "auto_retrain.py"

HUB_PORT = 7750
CACHE_TTL_SECONDS = 30
REFRESH_INTERVAL_SECONDS = 10


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_equal(a: Any, b: Any) -> bool:
    try:
        return json.dumps(a, sort_keys=True, default=str) == json.dumps(b, sort_keys=True, default=str)
    except Exception:
        return a == b


def _parse_model_status(text: str) -> Dict[str, Any]:
    model_version = "unknown"
    top3 = 0.0
    rows = 0
    threshold = 0
    eta_days = None
    model_ready = False

    m_model = re.search(r"Current model:\s*(v[0-9.]+)\s*\|\s*Top-3:\s*([0-9.]+)%", text)
    if m_model:
        model_version = m_model.group(1)
        top3 = float(m_model.group(2)) / 100.0

    m_rows = re.search(r"Rows:\s*([0-9,]+)\s*/\s*([0-9,]+)\s*threshold", text)
    if m_rows:
        rows = int(m_rows.group(1).replace(",", ""))
        threshold = int(m_rows.group(2).replace(",", ""))

    m_eta = re.search(r"Next retrain ETA:\s*~([0-9.]+)\s*days", text)
    if m_eta:
        eta_days = float(m_eta.group(1))

    m_ready = re.search(r"Model ready:\s*(true|false)", text, flags=re.IGNORECASE)
    if m_ready:
        model_ready = m_ready.group(1).lower() == "true"
    elif model_version != "unknown":
        model_ready = True

    m_active = re.search(r"Active model:\s*(v[0-9.]+)", text)
    if m_active:
        model_version = m_active.group(1)

    return {
        "model_version": model_version,
        "top3": top3,
        "rows": rows,
        "threshold": threshold,
        "eta_days": eta_days,
        "model_ready": model_ready,
        "raw": text.strip(),
    }


class CommandBody(BaseModel):
    command: str


class HubState:
    def __init__(self):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.snapshot: Dict[str, Any] = {}
        self.last_updated: str = ""
        self.clients: Set[WebSocket] = set()
        self._task: Optional[asyncio.Task] = None
        self._running = False

        self.urls = {
            "goal": "http://127.0.0.1:7735/goal/active",
            "all_goals": "http://127.0.0.1:7735/goal/list",
            "context_summary": "http://127.0.0.1:7736/context/summary?hours=2",
            "recent_events": "http://127.0.0.1:7736/context/recent?n=10",
            "process_scores": "http://127.0.0.1:7737/resource/scores",
            "resource_status": "http://127.0.0.1:7737/resource/status",
            "sync_status": "http://127.0.0.1:7740/sync/status",
            "peers": "http://127.0.0.1:7740/sync/peers",
            "sync_state": "http://127.0.0.1:7740/sync/state",
        }

    async def _fetch_json(self, url: str, timeout: float = 3.0) -> Optional[Any]:
        try:
            t = aiohttp.ClientTimeout(total=timeout)
            async with aiohttp.ClientSession(timeout=t) as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return None
                    return await resp.json()
        except Exception:
            return None

    async def _forward_command(self, command: str) -> Dict[str, Any]:
        payload = {"command": command, "source": "hub"}
        try:
            t = aiohttp.ClientTimeout(total=5.0)
            async with aiohttp.ClientSession(timeout=t) as session:
                async with session.post("http://127.0.0.1:7740/sync/voice", json=payload) as resp:
                    if resp.status != 200:
                        return {"ok": False, "reply": "Sync daemon unreachable"}
                    out = await resp.json()
                    if not isinstance(out, dict):
                        return {"ok": False, "reply": "Invalid response"}
                    return out
        except Exception:
            return {"ok": False, "reply": "Sync daemon unreachable"}

    def _cache_set(self, key: str, value: Any) -> None:
        self.cache[key] = {
            "value": value,
            "fetched_at": time.time(),
        }

    def _cache_get(self, key: str, default: Any = None) -> Any:
        hit = self.cache.get(key)
        if not hit:
            return default
        return hit.get("value", default)

    def _is_stale(self, key: str, now_ts: Optional[float] = None) -> bool:
        now_ts = now_ts if now_ts is not None else time.time()
        hit = self.cache.get(key)
        if not hit:
            return True
        fetched_at = float(hit.get("fetched_at", 0))
        return (now_ts - fetched_at) > CACHE_TTL_SECONDS

    def _stale_agents(self) -> List[str]:
        now_ts = time.time()
        stale = []

        if self._is_stale("goal", now_ts) or self._is_stale("all_goals", now_ts):
            stale.append("goal")
        if self._is_stale("context_summary", now_ts) or self._is_stale("recent_events", now_ts):
            stale.append("context")
        if self._is_stale("process_scores", now_ts) or self._is_stale("resource_status", now_ts):
            stale.append("resource")
        if self._is_stale("sync_status", now_ts) or self._is_stale("peers", now_ts) or self._is_stale("sync_state", now_ts):
            stale.append("sync")
        if self._is_stale("model_info", now_ts):
            stale.append("model")

        return stale

    async def _fetch_model_info(self) -> Optional[Dict[str, Any]]:
        if not AUTO_RETRAIN_SCRIPT.exists():
            return None
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                str(AUTO_RETRAIN_SCRIPT),
                "--status",
                "--json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=8)
            text = (stdout or b"").decode("utf-8", errors="ignore")
            if not text.strip() and stderr:
                text = stderr.decode("utf-8", errors="ignore")
            if not text.strip():
                return None
            return json.loads(text)
        except Exception:
            return None

    def _build_timeline(self, events: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        out = []
        icon_map = {
            "file": "📁",
            "git": "🔧",
            "browser": "🌐",
            "app": "⌨️",
            "shell": "⌨️",
        }

        for row in events[-50:]:
            if not isinstance(row, dict):
                continue
            ts = str(row.get("timestamp") or row.get("time") or "")
            desc = str(
                row.get("description")
                or row.get("text")
                or row.get("event")
                or row.get("command")
                or row.get("cmd")
                or row.get("path")
                or ""
            )
            kind = str(row.get("type") or row.get("category") or "app").lower().strip()

            if not desc:
                desc = "activity"

            inferred = kind
            if inferred not in icon_map:
                low = desc.lower()
                if "git" in low:
                    inferred = "git"
                elif "http" in low or "browser" in low:
                    inferred = "browser"
                elif "file" in low or "." in low:
                    inferred = "file"
                else:
                    inferred = "app"

            short_time = ts[11:16] if len(ts) >= 16 else "--:--"
            out.append(
                {
                    "time": short_time,
                    "type": inferred,
                    "description": desc,
                    "icon": icon_map.get(inferred, "⌨️"),
                }
            )
        return out[-50:]

    def _build_snapshot(self) -> Dict[str, Any]:
        sync_state = self._cache_get("sync_state", {})
        system_snapshot = sync_state.get("system_snapshot", {}) if isinstance(sync_state, dict) else {}
        recent_events = self._cache_get("recent_events", [])
        if not isinstance(recent_events, list):
            recent_events = []
        goal = self._cache_get("goal", {})

        stale = self._stale_agents()

        return {
            "goal": goal,
            "active_goal": goal,
            "all_goals": self._cache_get("all_goals", []),
            "context_summary": self._cache_get("context_summary", {}),
            "recent_events": recent_events,
            "process_scores": self._cache_get("process_scores", []),
            "resource_status": self._cache_get("resource_status", {}),
            "sync_status": self._cache_get("sync_status", {}),
            "peers": self._cache_get("peers", []),
            "model_info": self._cache_get("model_info", {}),
            "system_snapshot": system_snapshot if isinstance(system_snapshot, dict) else {},
            "stale_agents": stale,
            "timeline": self._build_timeline(recent_events),
            "last_updated": self.last_updated,
        }

    @staticmethod
    def _changed_fields(old: Dict[str, Any], new: Dict[str, Any]) -> List[str]:
        changed: List[str] = []
        for key in sorted(set(old.keys()).union(set(new.keys()))):
            if not _json_equal(old.get(key), new.get(key)):
                changed.append(key)
        return changed

    @staticmethod
    def _significant_change(old: Dict[str, Any], new: Dict[str, Any]) -> bool:
        old_goal = old.get("goal", {}) if isinstance(old.get("goal"), dict) else {}
        new_goal = new.get("goal", {}) if isinstance(new.get("goal"), dict) else {}
        op = float(old_goal.get("progress", 0.0) or 0.0)
        np = float(new_goal.get("progress", 0.0) or 0.0)
        if abs(np - op) >= 0.05:
            return True

        old_sys = old.get("system_snapshot", {}) if isinstance(old.get("system_snapshot"), dict) else {}
        new_sys = new.get("system_snapshot", {}) if isinstance(new.get("system_snapshot"), dict) else {}
        for key in ["ram_percent", "cpu_percent", "disk_percent"]:
            if abs(float(new_sys.get(key, 0.0) or 0.0) - float(old_sys.get(key, 0.0) or 0.0)) >= 5.0:
                return True

        old_peers = len(old.get("peers", []) if isinstance(old.get("peers"), list) else [])
        new_peers = len(new.get("peers", []) if isinstance(new.get("peers"), list) else [])
        return old_peers != new_peers

    async def refresh_once(self) -> Dict[str, Any]:
        fetch_tasks = {k: asyncio.create_task(self._fetch_json(url)) for k, url in self.urls.items()}
        model_task = asyncio.create_task(self._fetch_model_info())

        for key, task in fetch_tasks.items():
            value = await task
            if value is not None:
                self._cache_set(key, value)

        model = await model_task
        if model is not None:
            self._cache_set("model_info", model)

        old = self.snapshot
        self.last_updated = _now_iso()
        new = self._build_snapshot()
        new["last_updated"] = self.last_updated
        self.snapshot = new

        changed = self._changed_fields(old, new)
        return {
            "snapshot": new,
            "changed_fields": changed,
            "significant": self._significant_change(old, new),
        }

    async def _broadcast(self, payload: Dict[str, Any]) -> None:
        stale_clients: List[WebSocket] = []
        for ws in list(self.clients):
            try:
                await ws.send_json(payload)
            except Exception:
                stale_clients.append(ws)
        for ws in stale_clients:
            self.clients.discard(ws)

    async def _loop(self) -> None:
        while self._running:
            info = await self.refresh_once()
            changed_fields = info.get("changed_fields", [])
            if changed_fields:
                values = {k: self.snapshot.get(k) for k in changed_fields}
                await self._broadcast(
                    {
                        "type": "delta",
                        "changed_fields": changed_fields,
                        "values": values,
                        "significant": bool(info.get("significant", False)),
                    }
                )
            await asyncio.sleep(REFRESH_INTERVAL_SECONDS)

    async def start(self) -> None:
        if os.environ.get("EONIX_HUB_DISABLE_BG", "0") == "1":
            return
        if self._running:
            return
        self._running = True
        await self.refresh_once()
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except Exception:
                pass
            self._task = None


hub = HubState()

app = FastAPI(title="Eonix Hub", version="0.5.2")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
async def on_startup() -> None:
    await hub.start()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    await hub.stop()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/hub/status")
async def hub_status() -> Dict[str, Any]:
    if not hub.snapshot:
        await hub.refresh_once()

    stale = hub.snapshot.get("stale_agents", []) if isinstance(hub.snapshot, dict) else []
    agents = {
        "goal": "goal" not in stale,
        "context": "context" not in stale,
        "resource": "resource" not in stale,
        "sync": "sync" not in stale,
    }
    model_info = hub.snapshot.get("model_info", {}) if isinstance(hub.snapshot, dict) else {}
    return {
        "all_agents_healthy": all(agents.values()),
        "agents": agents,
        "last_updated": hub.snapshot.get("last_updated", ""),
        "model_version": model_info.get("model_version", "unknown"),
        "model_ready": bool(model_info.get("model_ready", False)),
        "next_retrain_eta": model_info.get("eta_days"),
    }


@app.get("/hub/snapshot")
async def hub_snapshot() -> Dict[str, Any]:
    if not hub.snapshot:
        await hub.refresh_once()
    return hub.snapshot


@app.get("/hub/timeline")
async def hub_timeline() -> List[Dict[str, str]]:
    if not hub.snapshot:
        await hub.refresh_once()
    timeline = hub.snapshot.get("timeline", []) if isinstance(hub.snapshot, dict) else []
    return timeline[-50:] if isinstance(timeline, list) else []


@app.post("/hub/command")
async def hub_command(body: CommandBody) -> Dict[str, Any]:
    return await hub._forward_command(body.command)


@app.websocket("/hub/live")
async def hub_live(websocket: WebSocket) -> None:
    await websocket.accept()
    hub.clients.add(websocket)

    if not hub.snapshot:
        await hub.refresh_once()

    await websocket.send_json(
        {
            "type": "snapshot",
            "values": hub.snapshot,
        }
    )

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        hub.clients.discard(websocket)


# ── AI Settings API (Iron Man mode) ─────────────────────

_EONIX_CONFIG = Path.home() / ".config" / "eonix" / "settings.json"


def _read_eonix_settings() -> dict:
    try:
        with open(_EONIX_CONFIG, encoding="utf-8") as f:
            return json.loads(f.read())
    except Exception:
        return {}


@app.get("/api/settings")
async def api_get_settings():
    return JSONResponse(_read_eonix_settings())


@app.post("/api/settings/{key}")
async def api_set_setting(key: str, body: dict):
    cfg = _read_eonix_settings()
    cfg[key] = body.get("value")
    _EONIX_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    with open(_EONIX_CONFIG, "w", encoding="utf-8") as f:
        f.write(json.dumps(cfg, indent=2))
    return JSONResponse({"ok": True, "key": key, "value": cfg[key]})


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=HUB_PORT, log_level="warning")


if __name__ == "__main__":
    main()


# --------------------------- tests ---------------------------


def _reset_hub() -> None:
    hub.cache = {}
    hub.snapshot = {}
    hub.last_updated = ""


def test_snapshot_contains_all_required_keys(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("EONIX_HUB_DISABLE_BG", "1")
    _reset_hub()

    now = time.time()
    keys = [
        "goal",
        "all_goals",
        "context_summary",
        "recent_events",
        "process_scores",
        "resource_status",
        "sync_status",
        "peers",
        "sync_state",
        "model_info",
    ]
    for k in keys:
        hub.cache[k] = {"value": {} if k != "recent_events" and k != "peers" and k != "process_scores" and k != "all_goals" else [], "fetched_at": now}

    hub.last_updated = _now_iso()
    hub.snapshot = hub._build_snapshot()
    hub.snapshot["last_updated"] = hub.last_updated

    client = TestClient(app)
    res = client.get("/hub/snapshot")
    assert res.status_code == 200
    payload = res.json()
    for key in [
        "goal",
        "all_goals",
        "context_summary",
        "recent_events",
        "process_scores",
        "sync_status",
        "peers",
        "model_info",
        "system_snapshot",
        "stale_agents",
    ]:
        assert key in payload


def test_stale_agent_marked_when_unreachable(monkeypatch):
    monkeypatch.setenv("EONIX_HUB_DISABLE_BG", "1")
    _reset_hub()
    now = time.time()

    hub.cache["goal"] = {"value": {}, "fetched_at": now - (CACHE_TTL_SECONDS + 5)}
    hub.cache["all_goals"] = {"value": [], "fetched_at": now - (CACHE_TTL_SECONDS + 5)}
    hub.cache["context_summary"] = {"value": {}, "fetched_at": now}
    hub.cache["recent_events"] = {"value": [], "fetched_at": now}
    hub.cache["process_scores"] = {"value": [], "fetched_at": now}
    hub.cache["resource_status"] = {"value": {}, "fetched_at": now}
    hub.cache["sync_status"] = {"value": {}, "fetched_at": now}
    hub.cache["peers"] = {"value": [], "fetched_at": now}
    hub.cache["sync_state"] = {"value": {}, "fetched_at": now}
    hub.cache["model_info"] = {"value": {}, "fetched_at": now}

    snap = hub._build_snapshot()
    assert "goal" in snap.get("stale_agents", [])


def test_timeline_returns_50_or_fewer_events(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("EONIX_HUB_DISABLE_BG", "1")
    _reset_hub()
    now = time.time()

    events = []
    for i in range(80):
        events.append({"timestamp": f"2026-03-14T10:{i%60:02d}:00+00:00", "description": f"event {i}", "type": "app"})

    hub.cache["recent_events"] = {"value": events, "fetched_at": now}
    hub.cache["goal"] = {"value": {}, "fetched_at": now}
    hub.cache["all_goals"] = {"value": [], "fetched_at": now}
    hub.cache["context_summary"] = {"value": {}, "fetched_at": now}
    hub.cache["process_scores"] = {"value": [], "fetched_at": now}
    hub.cache["resource_status"] = {"value": {}, "fetched_at": now}
    hub.cache["sync_status"] = {"value": {}, "fetched_at": now}
    hub.cache["peers"] = {"value": [], "fetched_at": now}
    hub.cache["sync_state"] = {"value": {}, "fetched_at": now}
    hub.cache["model_info"] = {"value": {}, "fetched_at": now}

    hub.last_updated = _now_iso()
    hub.snapshot = hub._build_snapshot()
    hub.snapshot["last_updated"] = hub.last_updated

    client = TestClient(app)
    res = client.get("/hub/timeline")
    assert res.status_code == 200
    assert len(res.json()) <= 50


def test_command_forwarded_to_sync_daemon(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("EONIX_HUB_DISABLE_BG", "1")

    async def _fake_forward(command: str) -> Dict[str, Any]:
        assert command == "sync now"
        return {"ok": True, "reply": "Command received by Eonix"}

    monkeypatch.setattr(hub, "_forward_command", _fake_forward)

    client = TestClient(app)
    res = client.post("/hub/command", json={"command": "sync now"})
    assert res.status_code == 200
    payload = res.json()
    assert payload.get("ok") is True


def test_websocket_sends_snapshot_on_connect(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("EONIX_HUB_DISABLE_BG", "1")
    _reset_hub()
    now = time.time()

    hub.cache["goal"] = {"value": {"name": "Build Hub"}, "fetched_at": now}
    hub.cache["all_goals"] = {"value": [{"name": "Build Hub"}], "fetched_at": now}
    hub.cache["context_summary"] = {"value": {"summary": "coding"}, "fetched_at": now}
    hub.cache["recent_events"] = {"value": [], "fetched_at": now}
    hub.cache["process_scores"] = {"value": [], "fetched_at": now}
    hub.cache["resource_status"] = {"value": {}, "fetched_at": now}
    hub.cache["sync_status"] = {"value": {"device_id": "d1"}, "fetched_at": now}
    hub.cache["peers"] = {"value": [], "fetched_at": now}
    hub.cache["sync_state"] = {"value": {"system_snapshot": {}}, "fetched_at": now}
    hub.cache["model_info"] = {"value": {"model_version": "v1.1"}, "fetched_at": now}
    hub.last_updated = _now_iso()
    hub.snapshot = hub._build_snapshot()
    hub.snapshot["last_updated"] = hub.last_updated

    client = TestClient(app)
    with client.websocket_connect("/hub/live") as ws:
        msg = ws.receive_json()
        assert msg.get("type") == "snapshot"
        assert "values" in msg
        assert "goal" in msg["values"]
