#!/usr/bin/env python3
"""Eonix MIND system reader for full subsystem context."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Dict, List

import psutil


REPO_ROOT = Path(__file__).resolve().parents[1]
MODEL_META = REPO_ROOT / "models" / "onnx" / "model_metadata.json"
SCHED_DB = Path.home() / ".eonix" / "scheduler_data.db"


class EonixSystemReader:
    def read_all(self) -> dict:
        return {
            "processes": self._top_processes(n=5),
            "ram": self._ram_stats(),
            "cpu": self._cpu_stats(),
            "disk": self._disk_stats(),
            "uptime_hours": self._uptime(),
            "deadlock_log": self._read_proc("/proc/eonix/deadlock_log"),
            "rag_state": self._read_proc("/proc/eonix/rag_state"),
            "security_alerts": self._tail_file("~/.eonix/security_alerts.log", n=3),
            "scheduler_stats": self._read_proc("/proc/eonix/scheduler_stats"),
            "model_version": self._model_metadata(),
            "retrain_eta": self._retrain_eta(),
            "git_context": self._git_context(),
            "active_goal": self._read_file("~/.eonix/active_goal.txt"),
        }

    def _top_processes(self, n: int) -> List[dict]:
        procs = []
        for p in psutil.process_iter(["name", "pid", "memory_percent", "cpu_percent", "memory_info"]):
            try:
                rss = p.info["memory_info"].rss if p.info.get("memory_info") else 0
                procs.append({
                    "name": p.info.get("name") or "unknown",
                    "pid": int(p.info.get("pid") or 0),
                    "ram_mb": round(rss / (1024 * 1024), 2),
                    "cpu_percent": float(p.info.get("cpu_percent") or 0.0),
                    "memory_percent": float(p.info.get("memory_percent") or 0.0),
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        procs.sort(key=lambda x: x["memory_percent"], reverse=True)
        return procs[:n]

    def _ram_stats(self) -> dict:
        vm = psutil.virtual_memory()
        return {
            "used_gb": round(vm.used / (1024**3), 2),
            "total_gb": round(vm.total / (1024**3), 2),
            "percent": float(vm.percent),
        }

    def _cpu_stats(self) -> dict:
        freq = psutil.cpu_freq()
        return {
            "percent_1s": float(psutil.cpu_percent(interval=1)),
            "core_count": int(psutil.cpu_count(logical=True) or 0),
            "freq_mhz": float(freq.current if freq else 0.0),
        }

    def _disk_stats(self) -> dict:
        du = psutil.disk_usage("/")
        return {
            "used_gb": round(du.used / (1024**3), 2),
            "total_gb": round(du.total / (1024**3), 2),
            "percent": float(du.percent),
            "path": "/",
        }

    def _uptime(self) -> float:
        return round((time.time() - psutil.boot_time()) / 3600.0, 2)

    def _read_proc(self, path: str) -> str:
        p = Path(path)
        try:
            if not p.exists():
                return "unavailable"
            lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
            if not lines:
                return "unavailable"
            return " | ".join(lines[-3:])
        except Exception:
            return "unavailable"

    def _tail_file(self, path: str, n: int = 3) -> List[str]:
        p = Path(os.path.expanduser(path))
        try:
            if not p.exists():
                return []
            lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
            return lines[-n:]
        except Exception:
            return []

    def _model_metadata(self) -> dict:
        if not MODEL_META.exists():
            return {}
        try:
            data = json.loads(MODEL_META.read_text(encoding="utf-8"))
            return {
                "version": data.get("version"),
                "top3": data.get("top3"),
                "trained_on": data.get("trained_date"),
                "auto_retrain_at": data.get("auto_retrain_at"),
            }
        except Exception:
            return {}

    def _current_row_count(self) -> int:
        if not SCHED_DB.exists():
            return 0
        conn = sqlite3.connect(SCHED_DB)
        try:
            return int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])
        except Exception:
            return 0
        finally:
            conn.close()

    def _retrain_eta(self) -> str:
        meta = self._model_metadata()
        rows = self._current_row_count()

        version = str(meta.get("version") or "v1.0")
        thresholds = {
            "v1.0": ("v1.1", 60000),
            "v1.1": ("v1.2", 120000),
            "v1.2": ("v1.3", 200000),
            "v1.3": ("v1.4", 320000),
            "v1.4": ("v1.5", 473000),
        }
        next_ver, needed = thresholds.get(version, ("v1.1", int(meta.get("auto_retrain_at") or 60000)))
        if version == "v1.0" and meta.get("auto_retrain_at"):
            needed = int(meta["auto_retrain_at"])

        remaining = max(0, needed - rows)
        rows_per_day = 5000.0
        eta_days = round(remaining / rows_per_day, 1)
        return f"{next_ver} in ~{eta_days} days ({needed:,} rows needed)"

    def _git_context(self) -> dict:
        try:
            out = subprocess.check_output(
                ["git", "-C", str(REPO_ROOT), "log", "-1", "--pretty=%H|%s|%ai"],
                text=True,
            ).strip()
            h, msg, dt = out.split("|", 2)
            return {
                "hash": h,
                "message": msg,
                "date": dt,
                "repo_name": REPO_ROOT.name,
            }
        except Exception:
            return {}

    def _read_file(self, path: str) -> str:
        p = Path(os.path.expanduser(path))
        try:
            return p.read_text(encoding="utf-8", errors="ignore").strip() if p.exists() else ""
        except Exception:
            return ""

    def format_for_llm(self, data: dict) -> str:
        ram = data.get("ram", {})
        cpu = data.get("cpu", {})
        disk = data.get("disk", {})
        model = data.get("model_version", {})
        gctx = data.get("git_context", {})
        goal = data.get("active_goal") or "none"
        deadlock = data.get("deadlock_log") or "none today"
        alerts = data.get("security_alerts") or ["none today"]

        top = data.get("processes", [])[:3]
        top_str = " ".join([f"{p['name']}({p['ram_mb']:.0f}MB)" for p in top]) or "none"

        s = (
            f"RAM: {ram.get('used_gb',0)}/{ram.get('total_gb',0)}GB ({ram.get('percent',0):.0f}%) | "
            f"CPU: {cpu.get('percent_1s',0):.0f}% | "
            f"Disk: {disk.get('used_gb',0)}/{disk.get('total_gb',0)}GB ({disk.get('percent',0):.0f}%)\n"
            f"Top procs: {top_str}\n"
            f"Uptime: {data.get('uptime_hours',0)}h | "
            f"Git: {gctx.get('repo_name','unknown')} - {gctx.get('message','n/a')}\n"
            f"Scheduler: {model.get('version','n/a')} ({(model.get('top3') or 0)*100:.2f}% Top-3) | "
            f"Retrain {data.get('retrain_eta','unknown')}\n"
            f"Goal: {goal}\n"
            f"Last deadlock: {deadlock}\n"
            f"Last alert: {alerts[-1] if alerts else 'none today'}"
        )
        words = s.split()
        if len(words) > 400:
            s = " ".join(words[:400])
        return s


def test_read_all_returns_all_13_keys():
    r = EonixSystemReader()
    d = r.read_all()
    assert len(d.keys()) == 13


def test_format_for_llm_under_400_tokens():
    r = EonixSystemReader()
    s = r.format_for_llm(r.read_all())
    assert len(s.split()) <= 400


def test_graceful_when_proc_files_missing():
    r = EonixSystemReader()
    assert isinstance(r._read_proc("/proc/eonix/does_not_exist"), str)


def test_retrain_eta_string_format_correct():
    r = EonixSystemReader()
    eta = r._retrain_eta()
    assert "in ~" in eta and "rows needed" in eta


def test_git_context_returns_dict():
    r = EonixSystemReader()
    assert isinstance(r._git_context(), dict)
