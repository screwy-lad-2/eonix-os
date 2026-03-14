#!/usr/bin/env python3
"""Eonix SyncDaemon: LAN discovery and cross-device brain sync."""

from __future__ import annotations

import argparse
import json
import os
import socket
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import psutil

try:
    from fastapi import FastAPI
    from pydantic import BaseModel
except Exception:
    FastAPI = None  # type: ignore
    BaseModel = object  # type: ignore

try:
    import uvicorn
except Exception:
    uvicorn = None

try:
    from zeroconf import IPVersion, ServiceBrowser, ServiceInfo, Zeroconf
except Exception:
    Zeroconf = None  # type: ignore
    ServiceInfo = None  # type: ignore
    ServiceBrowser = None  # type: ignore
    IPVersion = None  # type: ignore

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from state_store import StateStore


EONIX_DIR = Path.home() / ".eonix"
DEVICE_ID_PATH = EONIX_DIR / "device_id.txt"
KNOWN_DEVICES_PATH = EONIX_DIR / "known_devices.json"
SYNC_STATE_PATH = EONIX_DIR / "sync_state.json"
SERVICE_TYPE = "_eonix._tcp.local."

GOAL_BASE = "http://127.0.0.1:7735"
CONTEXT_BASE = "http://127.0.0.1:7736"
RESOURCE_BASE = "http://127.0.0.1:7737"


@dataclass
class BrainState:
    device_id: str
    timestamp: str
    active_goal: Dict
    memory_summary: List[Dict]
    context_summary: str
    scheduler_info: Dict
    system_snapshot: Dict

    @classmethod
    def from_dict(cls, payload: Dict) -> "BrainState":
        return cls(
            device_id=str(payload.get("device_id", "")),
            timestamp=str(payload.get("timestamp", "")),
            active_goal=payload.get("active_goal") if isinstance(payload.get("active_goal"), dict) else {},
            memory_summary=payload.get("memory_summary") if isinstance(payload.get("memory_summary"), list) else [],
            context_summary=str(payload.get("context_summary", "")),
            scheduler_info=payload.get("scheduler_info") if isinstance(payload.get("scheduler_info"), dict) else {},
            system_snapshot=payload.get("system_snapshot") if isinstance(payload.get("system_snapshot"), dict) else {},
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(ts: str) -> datetime:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return datetime.fromtimestamp(0, tz=timezone.utc)


def _short_hash(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()[:16]


def _http_json(url: str, timeout: float = 2.5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return None


def _http_post_json(url: str, payload: Dict, timeout: float = 3.0):
    try:
        request = urllib.request.Request(
            url,
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return None


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value
    except Exception:
        return default


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


class _PeerListener:
    def __init__(self, daemon: "SyncDaemon"):
        self.daemon = daemon

    def add_service(self, zc, service_type: str, name: str) -> None:
        self._handle(zc, service_type, name)

    def update_service(self, zc, service_type: str, name: str) -> None:
        self._handle(zc, service_type, name)

    def remove_service(self, _zc, _service_type: str, _name: str) -> None:
        return

    def _handle(self, zc, service_type: str, name: str) -> None:
        try:
            info = zc.get_service_info(service_type, name)
            if info is None:
                return
            props = {k.decode("utf-8"): v.decode("utf-8") for k, v in (info.properties or {}).items()}
            peer_id = str(props.get("device_id") or "")
            if not peer_id or peer_id == self.daemon.device_id:
                return
            addresses = info.parsed_addresses()
            if not addresses:
                return
            ip = str(addresses[0])
            port = int(info.port)
            self.daemon.register_peer(peer_id=peer_id, ip=ip, port=port)
        except Exception:
            return


class SyncDaemon:
    SYNC_INTERVAL = 60

    def __init__(
        self,
        port: Optional[int] = None,
        device_id: Optional[str] = None,
        device_id_path: Path = DEVICE_ID_PATH,
        known_devices_path: Path = KNOWN_DEVICES_PATH,
        sync_state_path: Path = SYNC_STATE_PATH,
        goal_base: str = GOAL_BASE,
        context_base: str = CONTEXT_BASE,
        resource_base: str = RESOURCE_BASE,
    ):
        self.port = int(port if port is not None else int(os.environ.get("EONIX_SYNC_PORT", "7740")))
        self.goal_base = goal_base
        self.context_base = context_base
        self.resource_base = resource_base

        self.device_id_path = device_id_path
        self.known_devices_path = known_devices_path
        self.sync_state_path = sync_state_path
        self.device_id_path.parent.mkdir(parents=True, exist_ok=True)
        self.known_devices_path.parent.mkdir(parents=True, exist_ok=True)

        self.device_id = self._ensure_device_id(explicit=device_id)
        self.store = StateStore(state_path=self.sync_state_path, device_id_path=self.device_id_path)

        self.last_sync = ""
        self.last_state_timestamp = ""

        self._running = False
        self._sync_thread: Optional[threading.Thread] = None
        self._zc = None
        self._browser = None
        self._service_info = None
        self._lock = threading.Lock()

    def _ensure_device_id(self, explicit: Optional[str] = None) -> str:
        env_id = os.environ.get("EONIX_DEVICE_ID", "").strip()
        if explicit:
            return explicit.strip()
        if env_id:
            return env_id
        if self.device_id_path.exists():
            current = self.device_id_path.read_text(encoding="utf-8").strip()
            if current:
                return current

        host = socket.gethostname().strip().lower().replace(" ", "-")
        generated = f"eonix-{host}-{str(uuid.uuid4())[:4]}"
        self.device_id_path.write_text(generated, encoding="utf-8")
        return generated

    def _load_known_devices(self) -> List[Dict]:
        payload = _read_json(self.known_devices_path, [])
        return payload if isinstance(payload, list) else []

    def _save_known_devices(self, devices: List[Dict]) -> None:
        _write_json(self.known_devices_path, devices)

    def register_peer(self, peer_id: str, ip: str, port: int) -> None:
        if not peer_id or peer_id == self.device_id:
            return

        with self._lock:
            peers = self._load_known_devices()
            now = _utc_now()
            updated = False
            for peer in peers:
                if str(peer.get("device_id")) == peer_id:
                    peer["ip"] = ip
                    peer["port"] = int(port)
                    peer["last_seen"] = now
                    peer["online"] = True
                    updated = True
                    break
            if not updated:
                print(f"Found Eonix device: {peer_id} at {ip}")
                peers.append(
                    {
                        "device_id": peer_id,
                        "ip": ip,
                        "port": int(port),
                        "last_seen": now,
                        "online": True,
                    }
                )
            self._save_known_devices(peers)

        # Immediate exchange on discovery.
        state = self.get_brain_state()
        self.push_to_peer(ip=ip, port=port, state=state)
        pulled = _http_json(f"http://{ip}:{port}/sync/state", timeout=2.0)
        if isinstance(pulled, dict):
            self.receive_from_peer(BrainState.from_dict(pulled))

    def _memory_summary(self) -> List[Dict]:
        path = Path.home() / ".eonix" / "mind_memory" / "memory_fallback.db"
        if not path.exists():
            return []

        try:
            conn = sqlite3.connect(path)
            rows = conn.execute(
                "SELECT text,category,importance,timestamp FROM memories ORDER BY importance DESC, timestamp DESC LIMIT 5"
            ).fetchall()
            conn.close()
        except Exception:
            return []

        out = []
        for text, category, importance, _ts in rows:
            normalized = str(text).strip()
            out.append(
                {
                    "text": normalized,
                    "category": str(category),
                    "importance": int(importance),
                    "text_hash": _short_hash(normalized),
                }
            )
        return out

    def _scheduler_info(self) -> Dict:
        try:
            if str(Path(__file__).resolve().parents[1] / "eonix-mind") not in sys.path:
                sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eonix-mind"))
            from system_reader import EonixSystemReader  # type: ignore

            model = EonixSystemReader().read_all().get("model_version", {})
            if isinstance(model, dict):
                return model
        except Exception:
            pass
        return {}

    def get_brain_state(self) -> BrainState:
        active_goal = _http_json(f"{self.goal_base}/goal/active", timeout=0.8)
        active_goal = active_goal if isinstance(active_goal, dict) else {}

        summary_payload = _http_json(f"{self.context_base}/context/summary?hours=2", timeout=0.8)
        context_summary = str(summary_payload.get("summary", "")) if isinstance(summary_payload, dict) else ""

        vm = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        snapshot = {
            "ram_percent": float(vm.percent),
            "cpu_percent": float(psutil.cpu_percent(interval=0.1)),
            "disk_percent": float(disk.percent),
        }

        state = BrainState(
            device_id=self.device_id,
            timestamp=_utc_now(),
            active_goal=active_goal,
            memory_summary=self._memory_summary(),
            context_summary=context_summary,
            scheduler_info=self._scheduler_info(),
            system_snapshot=snapshot,
        )
        self.last_state_timestamp = state.timestamp
        return state

    def push_to_peer(self, peer_ip: str, port: int, state: BrainState) -> bool:
        payload = asdict(state)
        payload["_source_port"] = int(self.port)
        response = _http_post_json(f"http://{peer_ip}:{port}/sync/receive", payload=payload, timeout=3.0)
        ok = isinstance(response, dict) and bool(response.get("ok", False))
        status = "ok" if ok else "failed"
        print(f"Sync push to {peer_ip}:{port}: {status}")
        return ok

    def receive_from_peer(self, state: BrainState) -> Dict:
        before = self.store.read()
        local_state = self.get_brain_state()

        incoming = asdict(state)
        incoming["context_summary"] = local_state.context_summary

        merged = self.store.write(incoming, source_device=state.device_id)
        self.last_sync = _utc_now()

        prev_goal = str((before.get("active_goal") or {}).get("name") or "")
        new_goal = str((merged.get("active_goal") or {}).get("name") or "")
        if new_goal and new_goal != prev_goal:
            print(f"Synced from {state.device_id}: goal updated to {new_goal}")

        return merged

    def list_peers(self) -> List[Dict]:
        peers = self._load_known_devices()
        now = _parse_iso(_utc_now())
        for peer in peers:
            seen = _parse_iso(str(peer.get("last_seen", "")))
            peer["online"] = (now - seen).total_seconds() <= 180
        return peers

    def push_all(self) -> Dict:
        state = self.get_brain_state()
        peers = self.list_peers()
        pushed = 0
        for peer in peers:
            if not peer.get("online", True):
                continue
            ip = str(peer.get("ip", "")).strip()
            port = int(peer.get("port", 7740))
            if ip and self.push_to_peer(ip, port, state):
                pushed += 1
        self.last_sync = _utc_now()
        return {"ok": True, "pushed": pushed, "peers_total": len(peers)}

    def _probe_local_ports(self) -> None:
        # Fallback discovery for local multi-instance smoke tests.
        candidates = [p for p in range(7740, 7751) if p != int(self.port)]
        for port in candidates:
            payload = _http_json(f"http://127.0.0.1:{port}/sync/status", timeout=0.25)
            if not isinstance(payload, dict):
                continue
            peer_id = str(payload.get("device_id", "")).strip()
            if peer_id and peer_id != self.device_id:
                self.register_peer(peer_id=peer_id, ip="127.0.0.1", port=port)

    def _sync_loop(self) -> None:
        last_push = 0.0
        while self._running:
            try:
                self._probe_local_ports()
                now = time.time()
                if now - last_push >= float(self.SYNC_INTERVAL):
                    self.push_all()
                    last_push = now
            except Exception:
                pass
            time.sleep(5)

    def _register_mdns(self) -> None:
        if Zeroconf is None or ServiceInfo is None:
            return
        try:
            host_ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            host_ip = "127.0.0.1"

        props = {
            b"device_id": self.device_id.encode("utf-8"),
            b"device_type": b"desktop",
            b"eonix_version": b"0.5.0",
        }
        service_name = f"{self.device_id}.{SERVICE_TYPE}"

        try:
            self._zc = Zeroconf(ip_version=IPVersion.V4Only if IPVersion else None)
        except Exception:
            self._zc = Zeroconf() if Zeroconf else None
        if self._zc is None:
            return

        self._service_info = ServiceInfo(
            SERVICE_TYPE,
            service_name,
            addresses=[socket.inet_aton(host_ip)],
            port=int(self.port),
            properties=props,
            server=f"{self.device_id}.local.",
        )
        self._zc.register_service(self._service_info)
        self._browser = ServiceBrowser(self._zc, SERVICE_TYPE, handlers=[_PeerListener(self)])

    def _unregister_mdns(self) -> None:
        try:
            if self._zc and self._service_info:
                self._zc.unregister_service(self._service_info)
            if self._zc:
                self._zc.close()
        except Exception:
            pass

    def status(self) -> Dict:
        peers = self.list_peers()
        online_count = len([p for p in peers if p.get("online", False)])
        age = 0
        if self.last_state_timestamp:
            age = int((_parse_iso(_utc_now()) - _parse_iso(self.last_state_timestamp)).total_seconds())

        return {
            "device_id": self.device_id,
            "peers_found": online_count,
            "last_sync": self.last_sync,
            "brain_state_age": age,
        }

    def start(self) -> None:
        if FastAPI is None or uvicorn is None:
            raise RuntimeError("fastapi + uvicorn are required to start SyncDaemon")

        self._register_mdns()
        self._running = True
        self._sync_thread = threading.Thread(target=self._sync_loop, name="EonixSyncLoop", daemon=True)
        self._sync_thread.start()

        app = create_app(self)
        print(f"SyncDaemon online - {self.device_id}")
        try:
            uvicorn.run(app, host="0.0.0.0", port=int(self.port), log_level="warning")
        finally:
            self._running = False
            self._unregister_mdns()


if FastAPI is not None and BaseModel is not object:
    class BrainStatePayload(BaseModel):
        device_id: str
        timestamp: str
        active_goal: Dict = {}
        memory_summary: List[Dict] = []
        context_summary: str = ""
        scheduler_info: Dict = {}
        system_snapshot: Dict = {}



def create_app(daemon: SyncDaemon):
    if FastAPI is None:
        raise RuntimeError("fastapi is not available")

    app = FastAPI(title="Eonix SyncDaemon", version="0.5.0-alpha")

    @app.get("/sync/status")
    def sync_status():
        return daemon.status()

    @app.get("/sync/peers")
    def sync_peers():
        return daemon.list_peers()

    @app.get("/sync/state")
    def sync_state():
        return asdict(daemon.get_brain_state())

    @app.post("/sync/receive")
    def sync_receive(payload: Dict):
        peer_id = str(payload.get("device_id", "")).strip()
        peer_port = int(payload.get("_source_port", 7740) or 7740)
        if peer_id:
            daemon.register_peer(peer_id=peer_id, ip="127.0.0.1", port=peer_port)
        state = BrainState.from_dict(payload)
        daemon.receive_from_peer(state)
        return {"ok": True}

    @app.post("/sync/push")
    def sync_push():
        return daemon.push_all()

    return app


def _cli_fetch(url: str, payload: Optional[Dict] = None):
    if payload is None:
        out = _http_json(url)
    else:
        out = _http_post_json(url, payload)
    print(json.dumps(out if out is not None else {"ok": False}, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Eonix SyncDaemon")
    parser.add_argument("--start", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--peers", action="store_true")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--port", type=int, default=int(os.environ.get("EONIX_SYNC_PORT", "7740")))
    args = parser.parse_args()

    daemon = SyncDaemon(port=args.port)
    base = f"http://127.0.0.1:{daemon.port}"

    if args.start:
        daemon.start()
        return
    if args.status:
        _cli_fetch(f"{base}/sync/status")
        return
    if args.peers:
        _cli_fetch(f"{base}/sync/peers")
        return
    if args.push:
        _cli_fetch(f"{base}/sync/push", payload={})
        return

    parser.print_help()


if __name__ == "__main__":
    main()


# --------------------------- tests ---------------------------


def _new_daemon(tmp_path, monkeypatch):
    monkeypatch.setenv("EONIX_SYNC_PORT", "7740")
    return SyncDaemon(
        port=7740,
        device_id_path=tmp_path / "device_id.txt",
        known_devices_path=tmp_path / "known_devices.json",
        sync_state_path=tmp_path / "sync_state.json",
    )


def test_device_id_generated_and_persisted(tmp_path, monkeypatch):
    monkeypatch.delenv("EONIX_DEVICE_ID", raising=False)
    daemon = _new_daemon(tmp_path, monkeypatch)
    first = daemon.device_id
    daemon2 = SyncDaemon(
        port=7740,
        device_id_path=tmp_path / "device_id.txt",
        known_devices_path=tmp_path / "known_devices.json",
        sync_state_path=tmp_path / "sync_state.json",
    )
    assert first.startswith("eonix-")
    assert daemon2.device_id == first


def test_brain_state_collects_all_fields(tmp_path, monkeypatch):
    daemon = _new_daemon(tmp_path, monkeypatch)
    monkeypatch.setattr("sync_daemon._http_json", lambda *_a, **_k: {"summary": "context"} if "summary" in _a[0] else {"id": "g1"})
    monkeypatch.setattr(daemon, "_memory_summary", lambda: [{"text": "deadline", "importance": 3}])
    monkeypatch.setattr(daemon, "_scheduler_info", lambda: {"version": "v1.1", "top3": 0.6})

    state = daemon.get_brain_state()
    payload = asdict(state)
    for key in [
        "device_id",
        "timestamp",
        "active_goal",
        "memory_summary",
        "context_summary",
        "scheduler_info",
        "system_snapshot",
    ]:
        assert key in payload


def test_conflict_resolution_goal_latest_wins(tmp_path, monkeypatch):
    daemon = _new_daemon(tmp_path, monkeypatch)
    daemon.store.write(
        {
            "timestamp": "2026-03-21T10:00:00+00:00",
            "active_goal": {"id": "old", "name": "Old Goal"},
            "memory_summary": [],
            "scheduler_info": {"top3": 0.5},
        },
        source_device="device-old",
    )

    monkeypatch.setattr(daemon, "get_brain_state", lambda: BrainState(daemon.device_id, _utc_now(), {}, [], "local", {}, {}))
    incoming = BrainState(
        device_id="device-new",
        timestamp="2026-03-21T10:01:00+00:00",
        active_goal={"id": "new", "name": "New Goal"},
        memory_summary=[],
        context_summary="peer",
        scheduler_info={"top3": 0.6},
        system_snapshot={},
    )
    daemon.receive_from_peer(incoming)
    assert daemon.store.get_active_goal()["name"] == "New Goal"


def test_conflict_resolution_memory_union(tmp_path, monkeypatch):
    daemon = _new_daemon(tmp_path, monkeypatch)
    daemon.store.write(
        {
            "timestamp": "2026-03-21T10:00:00+00:00",
            "active_goal": {},
            "memory_summary": [{"text": "A", "importance": 1, "text_hash": _short_hash("A")}],
            "scheduler_info": {},
        },
        source_device="device-A",
    )

    monkeypatch.setattr(daemon, "get_brain_state", lambda: BrainState(daemon.device_id, _utc_now(), {}, [], "local", {}, {}))
    daemon.receive_from_peer(
        BrainState(
            device_id="device-B",
            timestamp="2026-03-21T10:00:30+00:00",
            active_goal={},
            memory_summary=[
                {"text": "B", "importance": 2, "text_hash": _short_hash("B")},
                {"text": "A", "importance": 3, "text_hash": _short_hash("A")},
            ],
            context_summary="peer",
            scheduler_info={},
            system_snapshot={},
        )
    )

    memories = daemon.store.get_memory_summary()
    texts = {m["text"] for m in memories}
    assert texts == {"A", "B"}


def test_receive_updates_sync_state_json(tmp_path, monkeypatch):
    daemon = _new_daemon(tmp_path, monkeypatch)
    monkeypatch.setattr(daemon, "get_brain_state", lambda: BrainState(daemon.device_id, _utc_now(), {}, [], "local", {}, {}))

    daemon.receive_from_peer(
        BrainState(
            device_id="device-x",
            timestamp="2026-03-21T10:00:00+00:00",
            active_goal={"id": "g1", "name": "Goal X"},
            memory_summary=[],
            context_summary="peer",
            scheduler_info={"version": "v1", "top3": 0.7},
            system_snapshot={},
        )
    )

    data = _read_json(tmp_path / "sync_state.json", {})
    assert data.get("source_device") == "device-x"
    assert data.get("active_goal", {}).get("name") == "Goal X"


def test_status_endpoint_returns_correct_keys(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    daemon = _new_daemon(tmp_path, monkeypatch)
    app = create_app(daemon)
    client = TestClient(app)

    res = client.get("/sync/status")
    assert res.status_code == 200
    payload = res.json()
    for key in ["device_id", "peers_found", "last_sync", "brain_state_age"]:
        assert key in payload
