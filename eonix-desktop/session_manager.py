"""Desktop session save/restore per-goal for Eonix OS."""
from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import httpx

try:
    from window_manager import EonixWindowManager
except Exception:  # pragma: no cover
    EonixWindowManager = None  # type: ignore


class SessionManager:
    def __init__(
        self,
        wm: Optional[Any] = None,
        sessions_dir: Optional[Path] = None,
        launcher: Optional[Callable[[str], subprocess.Popen]] = None,
        sleeper: Optional[Callable[[float], None]] = None,
        goal_client: Optional[httpx.Client] = None,
    ):
        self.wm = wm or EonixWindowManager()
        self.sessions_dir = sessions_dir or (Path.home() / ".eonix" / "sessions")
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.launcher = launcher or (lambda cmd: subprocess.Popen(cmd, shell=True))
        self.sleeper = sleeper or time.sleep
        self.goal_client = goal_client or httpx.Client(timeout=1.0)

    def _session_path(self, goal_id: str) -> Path:
        return self.sessions_dir / f"{goal_id}.json"

    def _resolve_cmd_from_pid(self, pid: int) -> str:
        if pid <= 0:
            return ""
        proc_path = Path(f"/proc/{pid}/cmdline")
        if proc_path.exists():
            try:
                parts = [p for p in proc_path.read_text(encoding="utf-8", errors="ignore").split("\x00") if p]
                return " ".join(parts).strip()
            except Exception:
                return ""
        return ""

    def save_session(self, goal_id: str, goal_name: str = "") -> Path:
        windows = self.wm.scan_windows()
        data = {
            "goal_id": goal_id,
            "goal_name": goal_name,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "windows": [],
        }
        for w in windows:
            cmd = self._resolve_cmd_from_pid(w.pid)
            data["windows"].append(
                {
                    "title": w.title,
                    "cmd": cmd,
                    "pid": w.pid,
                    "position": list(w.position),
                    "snap_zone": w.snap_zone,
                }
            )

        path = self._session_path(goal_id)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path

    def restore_session(self, goal_id: str) -> dict:
        path = self._session_path(goal_id)
        if not path.exists():
            return {"ok": False, "error": "session not found", "goal_id": goal_id}

        payload = json.loads(path.read_text(encoding="utf-8"))
        restored = 0
        for item in payload.get("windows", []):
            cmd = str(item.get("cmd") or "").strip()
            title = str(item.get("title") or "Window")
            if cmd:
                self.launcher(cmd)
            self.sleeper(0.05)
            xid = self.wm.register_virtual_window(title=title)
            pos = item.get("position") or [0, 40, 800, 600]
            x, y, w, h = [int(v) for v in pos]
            self.wm.move(xid, x, y)
            self.wm.resize(xid, w, h)
            snap_zone = item.get("snap_zone")
            if isinstance(snap_zone, str) and snap_zone:
                self.wm.snap(xid, snap_zone)
            restored += 1

        return {
            "ok": True,
            "goal_id": goal_id,
            "goal_name": str(payload.get("goal_name", "")),
            "restored": restored,
            "message": f"Session restored for: {payload.get('goal_name', goal_id)}",
        }

    def list_sessions(self) -> list[dict]:
        out: list[dict] = []
        for file in sorted(self.sessions_dir.glob("*.json")):
            try:
                payload = json.loads(file.read_text(encoding="utf-8"))
            except Exception:
                continue
            out.append(
                {
                    "goal_id": str(payload.get("goal_id") or file.stem),
                    "goal_name": str(payload.get("goal_name") or ""),
                    "saved_at": str(payload.get("saved_at") or ""),
                    "count": len(payload.get("windows", [])),
                }
            )
        return out

    def _active_goal(self) -> dict:
        try:
            res = self.goal_client.get("http://127.0.0.1:7735/goal/active")
            if res.status_code == 200 and isinstance(res.json(), dict):
                return res.json()
        except Exception:
            pass
        return {}

    def auto_save(self) -> Optional[Path]:
        goal = self._active_goal()
        goal_id = str(goal.get("id") or "").strip()
        if not goal_id:
            return None
        goal_name = str(goal.get("name") or "")
        return self.save_session(goal_id, goal_name)


# ---------------------------
# Inline unit tests (pytest)
# ---------------------------


def test_save_session_creates_json_file(tmp_path):
    wm = EonixWindowManager()
    wm.register_virtual_window("VS Code", pid=101, position=(0, 40, 960, 700))
    sm = SessionManager(wm=wm, sessions_dir=tmp_path)
    path = sm.save_session("goal-a", "Build Desktop")
    assert path.exists()


def test_restore_session_reads_correct_file(tmp_path):
    wm = EonixWindowManager()
    sm = SessionManager(wm=wm, sessions_dir=tmp_path, launcher=lambda _cmd: None, sleeper=lambda _s: None)
    file = tmp_path / "goal-b.json"
    file.write_text(
        json.dumps(
            {
                "goal_id": "goal-b",
                "goal_name": "Goal B",
                "saved_at": "2026-01-01T00:00:00Z",
                "windows": [{"title": "Editor", "cmd": "", "position": [10, 50, 600, 400], "snap_zone": "left"}],
            }
        ),
        encoding="utf-8",
    )
    out = sm.restore_session("goal-b")
    assert out["ok"] is True
    assert out["restored"] == 1


def test_list_sessions_returns_all_goals(tmp_path):
    wm = EonixWindowManager()
    sm = SessionManager(wm=wm, sessions_dir=tmp_path)
    (tmp_path / "g1.json").write_text(json.dumps({"goal_id": "g1", "goal_name": "A", "windows": []}), encoding="utf-8")
    (tmp_path / "g2.json").write_text(json.dumps({"goal_id": "g2", "goal_name": "B", "windows": [{"x": 1}]}), encoding="utf-8")
    out = sm.list_sessions()
    assert len(out) == 2


def test_auto_save_updates_existing_session(tmp_path):
    class FakeGoalClient:
        def get(self, _url):
            class Resp:
                status_code = 200

                @staticmethod
                def json():
                    return {"id": "goal-c", "name": "Goal C"}

            return Resp()

    wm = EonixWindowManager()
    wm.register_virtual_window("Terminal", pid=777)
    sm = SessionManager(wm=wm, sessions_dir=tmp_path, goal_client=FakeGoalClient())
    first = sm.auto_save()
    second = sm.auto_save()
    assert first == second
    assert first is not None and first.exists()
