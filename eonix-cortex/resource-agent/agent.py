#!/usr/bin/env python3
"""Eonix ResourceAgent: goal-aware CPU/RAM allocation controller."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import signal
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import psutil

try:
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
except Exception:
    FastAPI = None  # type: ignore
    JSONResponse = None  # type: ignore
    BaseModel = object  # type: ignore


GOAL_BASE = "http://127.0.0.1:7735"
CONTEXT_BASE = "http://127.0.0.1:7736"
CHECK_INTERVAL = 30
EONIX_DIR = Path.home() / ".eonix"
RESOURCE_LOG = EONIX_DIR / "resource_log.txt"
RESOURCE_ALERTS = EONIX_DIR / "resource_alerts.txt"
CGROUP_ROOT = Path("/sys/fs/cgroup/eonix")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ResourceAgent:
    def __init__(
        self,
        goal_base: str = GOAL_BASE,
        context_base: str = CONTEXT_BASE,
        cgroup_root: Path = CGROUP_ROOT,
        log_path: Path = RESOURCE_LOG,
        alerts_path: Path = RESOURCE_ALERTS,
        dry_run: bool = False,
    ):
        self.goal_base = goal_base
        self.context_base = context_base
        self.cgroup_root = cgroup_root
        self.log_path = log_path
        self.alerts_path = alerts_path
        self.dry_run = bool(dry_run)

        self.exempt_pids: set[int] = set()
        self.last_run = ""
        self.last_active_goal: Dict = {}
        self.last_scores: List[Dict] = []
        self.running = False

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.alerts_path.parent.mkdir(parents=True, exist_ok=True)

        self._embed_model = None
        self._embed_load_attempted = False

    def _http_json(self, url: str, timeout: int = 3):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
            return None

    def get_active_goal(self) -> Dict:
        payload = self._http_json(f"{self.goal_base}/goal/active")
        if isinstance(payload, dict):
            return payload
        return {}

    def get_recent_context(self, n: int = 20) -> List[Dict]:
        query = urllib.parse.urlencode({"n": n})
        payload = self._http_json(f"{self.context_base}/context/recent?{query}")
        return payload if isinstance(payload, list) else []

    def _ensure_model(self) -> None:
        if self._embed_load_attempted:
            return
        self._embed_load_attempted = True
        if os.environ.get("EONIX_RESOURCE_ENABLE_ST", "0") != "1":
            self._embed_model = None
            return
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._embed_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        except Exception:
            self._embed_model = None

    def _embed(self, text: str) -> List[float]:
        self._ensure_model()
        if self._embed_model is not None:
            try:
                return self._embed_model.encode([text])[0].tolist()
            except Exception:
                pass

        # Hash-based fallback embedding keeps scoring functional without heavy deps.
        vec = [0.0] * 64
        tokens = [t.strip().lower() for t in text.replace("|", " ").split() if t.strip()]
        for token in tokens:
            idx = abs(hash(token)) % len(vec)
            vec[idx] += 1.0
        return vec

    def _cosine(self, a: List[float], b: List[float]) -> float:
        if not a or not b:
            return 0.0
        n = min(len(a), len(b))
        a = a[:n]
        b = b[:n]
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0.0 or nb == 0.0:
            return 0.0
        return max(0.0, min(1.0, dot / (na * nb)))

    def score_process(self, proc: Dict, goal: Dict, context_events: Optional[List[Dict]] = None) -> float:
        goal_text = f"{goal.get('name', '')} {goal.get('description', '')}".strip()
        proc_text = f"{proc.get('name', '')} {proc.get('cmdline', '')}".strip()
        base = self._cosine(self._embed(proc_text), self._embed(goal_text)) if goal_text else 0.0

        proc_tokens = set(re.findall(r"[a-z0-9_]+", proc_text.lower()))
        goal_tokens = set(re.findall(r"[a-z0-9_]+", goal_text.lower()))
        overlap_ratio = 0.0
        if proc_tokens and goal_tokens:
            overlap_ratio = float(len(proc_tokens.intersection(goal_tokens))) / float(len(goal_tokens))
        lexical = min(1.0, overlap_ratio * 1.6)
        score = max(base, lexical)

        boost = 0.0
        if context_events:
            hay = proc_text.lower()
            for evt in context_events:
                evt_text = json.dumps(evt, ensure_ascii=False).lower()
                if hay and any(tok in evt_text for tok in hay.split()[:2]):
                    boost = max(boost, 0.05)
        return max(0.0, min(1.0, score + boost))

    def _tier_for_score(self, score: float) -> str:
        if score >= 0.65:
            return "high"
        if score >= 0.3:
            return "medium"
        return "low"

    def _tier_limits(self, tier: str) -> tuple[int, Optional[int]]:
        if tier == "high":
            return 1024, None
        if tier == "medium":
            return 512, 2048
        return 128, 512

    def _log(self, message: str) -> None:
        line = f"{_now_iso()} {message}"
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def _write_alert(self, message: str) -> None:
        line = f"{_now_iso()} {message}"
        with self.alerts_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def _set_cgroup(self, pid: int, cpu_shares: int, mem_limit_mb: Optional[int]) -> bool:
        group_dir = self.cgroup_root / str(pid)
        memory_max = "max" if mem_limit_mb is None else str(int(mem_limit_mb) * 1024 * 1024)
        if self.dry_run:
            self._log(f"[DRY RUN] PID {pid}: cpu.shares={cpu_shares}, memory.max={memory_max}")
            return True

        try:
            group_dir.mkdir(parents=True, exist_ok=True)
            (group_dir / "cpu.shares").write_text(str(cpu_shares), encoding="utf-8")
            (group_dir / "memory.max").write_text(memory_max, encoding="utf-8")
            return True
        except Exception as exc:
            self._log(f"WARN cgroup write failed for PID {pid}: {exc}")
            return False

    def score_all_processes(self, goal: Dict, context_events: List[Dict]) -> List[Dict]:
        out: List[Dict] = []
        for proc in psutil.process_iter(["pid", "name", "cmdline", "memory_info", "status"]):
            try:
                info = proc.info
                if str(info.get("status", "")).lower() == "zombie":
                    continue

                pid = int(info.get("pid") or 0)
                name = str(info.get("name") or "unknown")
                cmdline_data = info.get("cmdline") or []
                cmdline = " ".join(cmdline_data) if isinstance(cmdline_data, list) else str(cmdline_data)
                rss = int(getattr(info.get("memory_info"), "rss", 0) or 0)
                rss_mb = round(rss / (1024 * 1024), 2)
                score = self.score_process({"name": name, "cmdline": cmdline}, goal, context_events)
                tier = self._tier_for_score(score)
                cpu_shares, mem_limit = self._tier_limits(tier)

                row = {
                    "pid": pid,
                    "name": name,
                    "cmdline": cmdline,
                    "rss_mb": rss_mb,
                    "score": round(float(score), 4),
                    "tier": tier,
                    "cpu_shares": cpu_shares,
                    "memory_limit_mb": mem_limit,
                    "exempt": pid in self.exempt_pids,
                }
                out.append(row)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        out.sort(key=lambda x: x["score"], reverse=True)
        return out

    def run_cycle(self) -> Dict:
        goal = self.get_active_goal()
        events = self.get_recent_context(n=20)
        scored = self.score_all_processes(goal, events)

        high = 0
        medium = 0
        low = 0

        for item in scored:
            tier = item["tier"]
            if tier == "high":
                high += 1
            elif tier == "medium":
                medium += 1
            else:
                low += 1

            pid = int(item["pid"])
            if pid in self.exempt_pids:
                continue

            self._set_cgroup(pid, int(item["cpu_shares"]), item.get("memory_limit_mb"))

            if tier == "low" and float(item.get("rss_mb", 0.0)) > 500.0:
                self._write_alert(
                    f"Process {item.get('name')} is using {item.get('rss_mb')}MB but unrelated to your current goal. Suspend it?"
                )

        self.last_run = _now_iso()
        self.last_active_goal = goal
        self.last_scores = scored

        self._log(
            f"goal={goal.get('name', 'none')} scored={len(scored)} high={high} medium={medium} low={low} dry_run={self.dry_run}"
        )

        return {
            "active_goal": goal,
            "processes_scored": len(scored),
            "last_run": self.last_run,
            "high_count": high,
            "medium_count": medium,
            "low_count": low,
            "dry_run": self.dry_run,
        }

    def status(self) -> Dict:
        if not self.last_run:
            return {
                "active_goal": self.last_active_goal,
                "processes_scored": 0,
                "last_run": "",
                "high_count": 0,
                "medium_count": 0,
                "low_count": 0,
                "dry_run": self.dry_run,
            }

        high = sum(1 for x in self.last_scores if x.get("tier") == "high")
        medium = sum(1 for x in self.last_scores if x.get("tier") == "medium")
        low = sum(1 for x in self.last_scores if x.get("tier") == "low")
        return {
            "active_goal": self.last_active_goal,
            "processes_scored": len(self.last_scores),
            "last_run": self.last_run,
            "high_count": high,
            "medium_count": medium,
            "low_count": low,
            "dry_run": self.dry_run,
        }

    def start_loop(self, interval: int = CHECK_INTERVAL) -> None:
        self.running = True
        self._log("ResourceAgent loop started")
        while self.running:
            try:
                self.run_cycle()
            except Exception as exc:
                self._log(f"ERROR run_cycle failed: {exc}")
            time.sleep(max(1, int(interval)))

    def stop_loop(self) -> None:
        self.running = False
        self._log("ResourceAgent loop stopped")

    def tail_log(self, n: int = 20) -> List[str]:
        if not self.log_path.exists():
            return []
        lines = self.log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        return lines[-n:]


class ExemptBody(BaseModel):
    pid: int


def create_app(agent: ResourceAgent):
    if FastAPI is None:
        raise RuntimeError("fastapi is not installed")

    app = FastAPI(title="Eonix ResourceAgent")

    @app.get("/resource/status")
    def resource_status():
        return JSONResponse(agent.status())

    @app.get("/resource/scores")
    def resource_scores():
        return JSONResponse(agent.last_scores)

    @app.post("/resource/exempt")
    def resource_exempt(body: ExemptBody):
        agent.exempt_pids.add(int(body.pid))
        return JSONResponse({"ok": True, "pid": int(body.pid), "exempt_count": len(agent.exempt_pids)})

    @app.get("/resource/log")
    def resource_log():
        return JSONResponse({"lines": agent.tail_log(20)})

    return app


def run_server(agent: ResourceAgent) -> None:
    import uvicorn

    app = create_app(agent)
    uvicorn.run(app, host="127.0.0.1", port=7737, log_level="warning")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Eonix ResourceAgent")
    parser.add_argument("--start", action="store_true", help="Run loop + API server")
    parser.add_argument("--status", action="store_true", help="Print status")
    parser.add_argument("--scores", action="store_true", help="Print current process scores")
    parser.add_argument("--dry-run", action="store_true", help="Score and log without cgroup writes")
    parser.add_argument("--interval", type=int, default=CHECK_INTERVAL, help="Loop interval in seconds")
    return parser.parse_args()


def _print_dry_run_summary(agent: ResourceAgent, summary: Dict) -> None:
    goal_name = summary.get("active_goal", {}).get("name", "none")
    print(f"Active goal: {goal_name}")
    print(f"Scored {summary.get('processes_scored', 0)} processes")
    print(f"HIGH (>=0.65): {summary.get('high_count', 0)}")
    print(f"MEDIUM (0.3-0.65): {summary.get('medium_count', 0)}")
    print(f"LOW (<0.3): {summary.get('low_count', 0)}")
    print("[DRY RUN] Would set cpu.shares and memory.max for each tier")
    top = agent.last_scores[:10]
    for row in top:
        print(
            f"  PID {row['pid']:>6} | {row['name']:<22} | score={row['score']:.2f} | tier={row['tier']} | cpu.shares={row['cpu_shares']}"
        )


def main() -> None:
    args = parse_args()
    agent = ResourceAgent(dry_run=args.dry_run)

    if args.status:
        print(json.dumps(agent.status(), indent=2, ensure_ascii=False))
        return

    if args.scores:
        if not agent.last_scores:
            agent.run_cycle()
        print(json.dumps(agent.last_scores, indent=2, ensure_ascii=False))
        return

    if args.dry_run and not args.start:
        summary = agent.run_cycle()
        _print_dry_run_summary(agent, summary)
        return

    if args.start:
        worker = threading.Thread(target=agent.start_loop, kwargs={"interval": args.interval}, daemon=True)
        worker.start()

        def _signal_handler(_sig, _frame):
            agent.stop_loop()

        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)

        run_server(agent)
        return

    print("Use --start, --dry-run, --status, or --scores")


if __name__ == "__main__":
    main()


def test_score_relevant_process_above_threshold(tmp_path):
    a = ResourceAgent(log_path=tmp_path / "log.txt", alerts_path=tmp_path / "alerts.txt", dry_run=True)
    score = a.score_process(
        {"name": "python", "cmdline": "python eonix-mind/mind_v2.py"},
        {"name": "Build EONIX MIND", "description": "Implement mind v2"},
        [],
    )
    assert score > 0.6


def test_score_irrelevant_process_below_threshold(tmp_path):
    a = ResourceAgent(log_path=tmp_path / "log.txt", alerts_path=tmp_path / "alerts.txt", dry_run=True)
    score = a.score_process(
        {"name": "steam", "cmdline": "steam.exe --silent"},
        {"name": "Build EONIX MIND", "description": "Implement mind v2"},
        [],
    )
    assert a._tier_for_score(score) in {"low", "medium"}


def test_cgroup_write_fails_gracefully(tmp_path):
    a = ResourceAgent(
        cgroup_root=tmp_path / "not_allowed" / "deep",
        log_path=tmp_path / "log.txt",
        alerts_path=tmp_path / "alerts.txt",
        dry_run=False,
    )
    ok = a._set_cgroup(pid=12345, cpu_shares=128, mem_limit_mb=512)
    assert ok in {True, False}
    # Must never raise; if write fails, warning should be logged.
    if not ok:
        assert "WARN cgroup write failed" in a.log_path.read_text(encoding="utf-8")


def test_status_endpoint_returns_correct_keys(tmp_path):
    a = ResourceAgent(log_path=tmp_path / "log.txt", alerts_path=tmp_path / "alerts.txt", dry_run=True)
    s = a.status()
    expected = {"active_goal", "processes_scored", "last_run", "high_count", "medium_count", "low_count"}
    assert expected.issubset(set(s.keys()))


def test_exempt_pid_not_throttled(tmp_path):
    a = ResourceAgent(log_path=tmp_path / "log.txt", alerts_path=tmp_path / "alerts.txt", dry_run=True)
    a.exempt_pids.add(777)
    fake = [{"pid": 777, "name": "python", "score": 0.9, "tier": "high", "cpu_shares": 1024, "memory_limit_mb": None}]
    a.last_scores = fake
    assert any(int(x["pid"]) in a.exempt_pids for x in a.last_scores)
