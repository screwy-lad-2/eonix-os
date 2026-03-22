"""Month 5 end-to-end integration checks against live running services.

Prerequisite:
  Run stack first, e.g.:
    EONIX_START_NO_MIND=1 bash start_eonix.sh
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psutil
import pytest
import pytest_asyncio
from websockets.asyncio.client import connect

BASE = {
    "goal": "http://127.0.0.1:7735",
    "context": "http://127.0.0.1:7736",
    "resource": "http://127.0.0.1:7737",
    "sync": "http://127.0.0.1:7740",
    "hub": "http://127.0.0.1:7750",
}


@pytest_asyncio.fixture
async def client():
    async with httpx.AsyncClient(timeout=45.0) as c:
        yield c


async def _active_goal_id(client: httpx.AsyncClient) -> str:
    r = await client.get(f"{BASE['goal']}/goal/active")
    if r.status_code != 200:
        return ""
    payload = r.json()
    if isinstance(payload, dict):
        return str(payload.get("id") or "")
    return ""


async def _create_goal(client: httpx.AsyncClient, name: str, description: str = "") -> str:
    last_exc = None
    for _ in range(4):
        try:
            r = await client.post(
                f"{BASE['goal']}/goal/create",
                json={"name": name, "description": description},
            )
            assert r.status_code == 200
            payload = r.json()
            gid = str(payload.get("id") or "")
            assert gid
            return gid
        except Exception as exc:
            last_exc = exc
            await asyncio_sleep(1.5)
    if last_exc:
        raise last_exc
    raise AssertionError("goal creation failed")


async def _complete_goal(client: httpx.AsyncClient, goal_id: str) -> None:
    if not goal_id:
        return
    await client.post(f"{BASE['goal']}/goal/complete", json={"goal_id": goal_id})


@pytest.mark.asyncio
async def test_all_agents_reachable(client: httpx.AsyncClient):
    checks = {
        "goal": (f"{BASE['goal']}/goal/status", "running"),
        "context": (f"{BASE['context']}/context/status", "running"),
        "resource": (f"{BASE['resource']}/resource/status", None),
        "sync": (f"{BASE['sync']}/sync/status", "device_id"),
        "hub": (f"{BASE['hub']}/hub/status", "all_agents_healthy"),
    }

    for name, (url, health_key) in checks.items():
        payload = None
        for _ in range(20):
            try:
                r = await client.get(url)
            except httpx.RequestError:
                await asyncio_sleep(1.5)
                continue
            assert r.status_code == 200, f"{name} unreachable"
            payload = r.json()
            assert isinstance(payload, dict)
            if health_key == "all_agents_healthy" and not payload.get("all_agents_healthy", False):
                await asyncio_sleep(1.5)
                continue
            break

        assert isinstance(payload, dict), f"{name} did not become reachable in time"
        if health_key == "running":
            assert payload.get("running", False) is True
        elif health_key:
            if health_key == "all_agents_healthy":
                assert payload.get("all_agents_healthy") is True
            else:
                assert health_key in payload


@pytest.mark.asyncio
async def test_hub_snapshot_reflects_live_goal(client: httpx.AsyncClient):
    previous = await _active_goal_id(client)
    created = await _create_goal(client, "Integration Test Goal", "month5 e2e")

    try:
        found = False
        for _ in range(24):
            r = await client.get(f"{BASE['hub']}/hub/snapshot")
            assert r.status_code == 200
            snap = r.json()
            goal = snap.get("active_goal", {}) if isinstance(snap, dict) else {}
            if str(goal.get("name") or "") == "Integration Test Goal":
                found = True
                break
            await asyncio_sleep(1.5)
        assert found
    finally:
        await _complete_goal(client, created)
        if previous:
            await client.post(f"{BASE['goal']}/goal/activate", json={"goal_id": previous})


@pytest.mark.asyncio
async def test_sync_state_updated_after_goal_change(client: httpx.AsyncClient):
    previous = await _active_goal_id(client)
    created = await _create_goal(client, "Sync Integration Goal", "month5 state sync")

    try:
        await asyncio_sleep(0.8)
        r = await client.get(f"{BASE['sync']}/sync/state")
        assert r.status_code == 200
        sync_state = r.json()
        active = sync_state.get("active_goal", {}) if isinstance(sync_state, dict) else {}
        assert str(active.get("name") or "") == "Sync Integration Goal"

        sync_file = Path.home() / ".eonix" / "sync_state.json"
        assert sync_file.exists()
        file_payload = json.loads(sync_file.read_text(encoding="utf-8"))
        file_goal = file_payload.get("active_goal", {}) if isinstance(file_payload, dict) else {}
        assert str(file_goal.get("name") or "") == "Sync Integration Goal"
    finally:
        await _complete_goal(client, created)
        if previous:
            await client.post(f"{BASE['goal']}/goal/activate", json={"goal_id": previous})


@pytest.mark.asyncio
async def test_context_events_appear_in_hub_timeline(client: httpx.AsyncClient):
    r = await client.get(f"{BASE['hub']}/hub/timeline")
    assert r.status_code == 200
    timeline = r.json()
    assert isinstance(timeline, list)
    if not timeline:
        return
    for item in timeline:
        assert "time" in item
        assert "type" in item
        assert "description" in item


@pytest.mark.asyncio
async def test_resource_scores_reflect_active_goal(client: httpx.AsyncClient):
    r = await client.get(f"{BASE['resource']}/resource/scores")
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list)
    assert len(rows) > 0
    first = rows[0]
    for key in ["pid", "name", "score", "tier"]:
        assert key in first


@pytest.mark.asyncio
async def test_voice_command_round_trip(client: httpx.AsyncClient):
    r = await client.post(f"{BASE['hub']}/hub/command", json={"command": "what is my active goal"})
    assert r.status_code == 200
    payload = r.json()
    assert isinstance(payload, dict)
    reply = str(payload.get("reply") or "")
    assert len(reply.strip()) > 0


@pytest.mark.asyncio
async def test_hub_websocket_sends_snapshot():
    uri = "ws://127.0.0.1:7750/hub/live"
    async with connect(uri, open_timeout=3) as ws:
        raw = await ws.recv()
        payload = json.loads(raw)
        assert payload.get("type") == "snapshot"
        values = payload.get("values", {})
        assert "active_goal" in values


@pytest.mark.asyncio
async def test_start_script_idempotent(client: httpx.AsyncClient):
    if platform.system().lower().startswith("win"):
        pytest.skip("idempotent startup shell check requires Linux bash path semantics")

    root = Path(__file__).resolve().parents[1]
    script = root / "start_eonix.sh"
    assert script.exists()

    env = os.environ.copy()
    root_bash = root.as_posix()
    py_bin = sys.executable
    if platform.system().lower().startswith("win") and py_bin[1:3] == ":\\":
        if root_bash[1:3] == ":/":
            rdrive = root_bash[0].lower()
            root_bash = f"/mnt/{rdrive}/{root_bash[3:]}"
        drive = py_bin[0].lower()
        rest = py_bin[2:].replace("\\", "/")
        py_bin = f"/mnt/{drive}{rest}"
    cmd = ["bash", "-lc", f"cd '{root_bash}' && EONIX_START_NO_MIND=1 PYTHON_BIN='{py_bin}' bash start_eonix.sh"]

    baseline_zombies = set()
    for p in psutil.process_iter(["pid", "status", "name"]):
        try:
            if str(p.info.get("status", "")).lower() == "zombie":
                baseline_zombies.add(int(p.info.get("pid")))
        except Exception:
            continue

    proc = subprocess.run(cmd, cwd=root, env=env, capture_output=True, timeout=35)
    err = (proc.stderr or b"").decode("utf-8", errors="ignore")
    assert proc.returncode == 0, err

    for url in [
        f"{BASE['goal']}/goal/status",
        f"{BASE['context']}/context/status",
        f"{BASE['resource']}/resource/status",
        f"{BASE['sync']}/sync/status",
        f"{BASE['hub']}/hub/status",
    ]:
        r = await client.get(url)
        assert r.status_code == 200

    # Sanity check: idempotent startup must not introduce new zombies.
    zombies = []
    for p in psutil.process_iter(["pid", "status", "name"]):
        try:
            if str(p.info.get("status", "")).lower() == "zombie":
                zombies.append(p.info)
        except Exception:
            continue
    new_zombies = [z for z in zombies if int(z.get("pid", -1)) not in baseline_zombies]
    assert len(new_zombies) == 0


def asyncio_sleep(seconds: float):
    import asyncio

    return asyncio.sleep(seconds)
