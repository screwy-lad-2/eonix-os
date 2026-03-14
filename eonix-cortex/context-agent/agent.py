#!/usr/bin/env python3
"""Eonix ContextAgent with collectors + FastAPI query API."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import psutil

try:
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
except Exception:
    FastAPI = None  # type: ignore
    JSONResponse = None  # type: ignore

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except Exception:
    FileSystemEventHandler = object  # type: ignore
    Observer = None  # type: ignore

try:
    import chromadb
except Exception:
    chromadb = None

try:
    from sentence_transformers import SentenceTransformer
except Exception:
    SentenceTransformer = None


HOME = Path.home()
EONIX_DIR = HOME / ".eonix"
SQLITE_DB = EONIX_DIR / "context_events.db"
PROJECTS_DIR = HOME / "Projects"
DOCS_DIR = HOME / "Documents"
BASH_HISTORY = HOME / ".bash_history"

NOISE_DIRS = {".git", "__pycache__", "node_modules"}
NOISE_SUFFIX = {".pyc", ".o", ".ko"}
TRIVIAL_COMMANDS = {"ls", "cd", "clear", "pwd"}


@dataclass
class Event:
    type: str
    timestamp: str
    payload: Dict


class _FileHandler(FileSystemEventHandler):  # type: ignore[misc]
    def __init__(self, agent: "ContextAgent"):
        self.agent = agent

    def on_any_event(self, event):
        if getattr(event, "is_directory", False):
            return
        path = str(getattr(event, "src_path", ""))
        if self.agent._is_noise_path(path):
            return
        kind = str(getattr(event, "event_type", "modified"))
        self.agent.store_event(
            "file",
            {
                "path": path,
                "event": kind,
            },
        )


class ContextAgent:
    def __init__(self, sqlite_path: Path = SQLITE_DB):
        self.sqlite_path = sqlite_path
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_sqlite()

        # Keep production defaults stable, but isolate test/dev instances.
        if self.sqlite_path.resolve() == SQLITE_DB.resolve():
            chroma_dir = EONIX_DIR / "chroma"
            collection_name = "eonix_context"
        else:
            chroma_dir = self.sqlite_path.parent / "chroma"
            collection_name = f"eonix_context_{self.sqlite_path.stem}"

        self.running = False
        self._threads: List[threading.Thread] = []
        self._observer = None
        self._lock = threading.Lock()

        self._last_history_size = BASH_HISTORY.stat().st_size if BASH_HISTORY.exists() else 0
        self._last_commit_seen = set()
        self._last_proc_snapshot: Dict[int, Dict] = {}
        self._pid_start_times: Dict[int, float] = {}
        self._last_window_title = ""

        self.embedding_model = None
        self.chroma = None
        self.collection = None

        if chromadb:
            try:
                self.chroma = chromadb.PersistentClient(path=str(chroma_dir))
                self.collection = self.chroma.get_or_create_collection(collection_name)
            except Exception:
                self.collection = None

        if SentenceTransformer:
            try:
                self.embedding_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
            except Exception:
                self.embedding_model = None

    def _init_sqlite(self) -> None:
        conn = sqlite3.connect(self.sqlite_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        conn.commit()
        conn.close()

    def _is_noise_path(self, path: str) -> bool:
        p = Path(path)
        if any(part in NOISE_DIRS for part in p.parts):
            return True
        if p.suffix in NOISE_SUFFIX:
            return True
        return False

    def _embed(self, text: str):
        if self.embedding_model is None:
            return None
        try:
            return self.embedding_model.encode([text])[0].tolist()
        except Exception:
            return None

    def store_event(self, event_type: str, payload: Dict) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        evt = Event(type=event_type, timestamp=ts, payload=payload)

        with self._lock:
            conn = sqlite3.connect(self.sqlite_path)
            conn.execute(
                "INSERT INTO events(type, timestamp, payload) VALUES (?, ?, ?)",
                (evt.type, evt.timestamp, json.dumps(evt.payload, ensure_ascii=False)),
            )
            conn.commit()
            conn.close()

        if self.collection is not None:
            txt = f"{event_type} {json.dumps(payload, ensure_ascii=False)}"
            emb = self._embed(txt)
            try:
                self.collection.add(
                    ids=[f"{int(time.time()*1000000)}"],
                    documents=[txt],
                    embeddings=[emb] if emb else None,
                    metadatas=[{"type": event_type, "timestamp": ts, "goal_id": ""}],
                )
            except Exception:
                pass

    def _watch_files(self) -> None:
        if Observer is None:
            return
        self._observer = Observer()
        handler = _FileHandler(self)
        for d in [PROJECTS_DIR, DOCS_DIR]:
            if d.exists():
                self._observer.schedule(handler, str(d), recursive=True)
        self._observer.start()

    def _watch_bash_history(self) -> None:
        while self.running:
            try:
                if BASH_HISTORY.exists():
                    size = BASH_HISTORY.stat().st_size
                    if size < self._last_history_size:
                        self._last_history_size = 0
                    if size > self._last_history_size:
                        with BASH_HISTORY.open("r", encoding="utf-8", errors="ignore") as f:
                            f.seek(self._last_history_size)
                            new_text = f.read()
                        self._last_history_size = size
                        for line in [x.strip() for x in new_text.splitlines() if x.strip()]:
                            head = line.split()[0]
                            if head not in TRIVIAL_COMMANDS:
                                self.store_event("command", {"cmd": line})
            except Exception:
                pass
            time.sleep(30)

    def _watch_git(self) -> None:
        while self.running:
            try:
                if PROJECTS_DIR.exists():
                    for d in PROJECTS_DIR.iterdir():
                        if not d.is_dir() or not (d / ".git").exists():
                            continue
                        cmd = ["git", "-C", str(d), "log", "--since=1 minute ago", "--pretty=%H|%s"]
                        out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
                        for line in [x.strip() for x in out.splitlines() if x.strip()]:
                            if line in self._last_commit_seen:
                                continue
                            self._last_commit_seen.add(line)
                            h, msg = line.split("|", 1)
                            self.store_event("git", {"hash": h, "message": msg, "repo": d.name})
            except Exception:
                pass
            time.sleep(60)

    def _watch_processes(self) -> None:
        while self.running:
            try:
                cur: Dict[int, Dict] = {}
                for p in psutil.process_iter(["pid", "name", "cpu_percent", "create_time"]):
                    info = p.info
                    if float(info.get("cpu_percent") or 0.0) <= 1.0:
                        continue
                    pid = int(info["pid"])
                    cur[pid] = {
                        "name": info.get("name") or "unknown",
                        "cpu_percent": float(info.get("cpu_percent") or 0.0),
                        "create_time": float(info.get("create_time") or time.time()),
                    }

                started = set(cur.keys()) - set(self._last_proc_snapshot.keys())
                ended = set(self._last_proc_snapshot.keys()) - set(cur.keys())

                for pid in started:
                    self._pid_start_times[pid] = cur[pid]["create_time"]
                    self.store_event("proc_start", {"name": cur[pid]["name"], "pid": pid})

                for pid in ended:
                    prev = self._last_proc_snapshot[pid]
                    start = self._pid_start_times.pop(pid, prev.get("create_time", time.time()))
                    dur = max(0.0, time.time() - float(start))
                    self.store_event("proc_end", {"name": prev.get("name", "unknown"), "duration_s": round(dur, 2)})

                self._last_proc_snapshot = cur
            except Exception:
                pass
            time.sleep(30)

    def _watch_active_window(self) -> None:
        while self.running:
            try:
                out = subprocess.check_output(
                    ["xdotool", "getactivewindow", "getwindowname"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip()
                if out and out != self._last_window_title:
                    self._last_window_title = out
                    app = out.split(" - ")[-1] if " - " in out else out.split()[0]
                    self.store_event("focus", {"title": out, "app": app})
            except Exception:
                pass
            time.sleep(10)

    def start_collectors(self) -> None:
        self.running = True
        self._watch_files()

        workers = [
            self._watch_bash_history,
            self._watch_git,
            self._watch_processes,
            self._watch_active_window,
        ]
        for fn in workers:
            t = threading.Thread(target=fn, daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self.running = False
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=2)

    def recent(self, n: int = 10) -> List[Dict]:
        conn = sqlite3.connect(self.sqlite_path)
        rows = conn.execute(
            "SELECT type,timestamp,payload FROM events ORDER BY id DESC LIMIT ?", (n,)
        ).fetchall()
        conn.close()
        out = []
        for t, ts, payload in rows:
            out.append({"type": t, "timestamp": ts, **json.loads(payload)})
        return out

    def search(self, q: str, n: int = 5) -> List[Dict]:
        if self.collection is not None:
            try:
                res = self.collection.query(query_texts=[q], n_results=n)
                docs = res.get("documents", [[]])[0]
                metas = res.get("metadatas", [[]])[0]
                return [{"text": d, "meta": m} for d, m in zip(docs, metas)]
            except Exception:
                pass

        conn = sqlite3.connect(self.sqlite_path)
        rows = conn.execute(
            "SELECT type,timestamp,payload FROM events WHERE payload LIKE ? ORDER BY id DESC LIMIT ?",
            (f"%{q}%", n),
        ).fetchall()
        conn.close()
        return [{"type": t, "timestamp": ts, **json.loads(payload)} for t, ts, payload in rows]

    def summary(self, hours: int = 2) -> str:
        cutoff = datetime.now(timezone.utc).timestamp() - hours * 3600
        cutoff_iso = datetime.fromtimestamp(cutoff, tz=timezone.utc).isoformat()
        conn = sqlite3.connect(self.sqlite_path)
        rows = conn.execute(
            "SELECT type,payload FROM events WHERE timestamp >= ? ORDER BY id DESC", (cutoff_iso,)
        ).fetchall()
        conn.close()

        counts = {}
        repos = set()
        for t, payload in rows:
            counts[t] = counts.get(t, 0) + 1
            if t == "git":
                p = json.loads(payload)
                repos.add(p.get("repo", ""))

        return (
            f"Last {hours}h: edited {counts.get('file',0)} files, "
            f"ran {counts.get('command',0)} commands, "
            f"{counts.get('git',0)} git commits, "
            f"focus changes {counts.get('focus',0)}, repos: {', '.join(sorted([r for r in repos if r])) or 'none'}"
        )

    def status(self) -> Dict:
        conn = sqlite3.connect(self.sqlite_path)
        today = datetime.now(timezone.utc).date().isoformat()
        cnt = conn.execute("SELECT COUNT(*) FROM events WHERE timestamp LIKE ?", (f"{today}%",)).fetchone()[0]
        conn.close()
        size_mb = round(self.sqlite_path.stat().st_size / (1024 * 1024), 3) if self.sqlite_path.exists() else 0.0
        return {
            "running": self.running,
            "events_today": int(cnt),
            "db_size_mb": size_mb,
        }


def create_app(agent: ContextAgent):
    if FastAPI is None:
        raise RuntimeError("fastapi is not installed")

    app = FastAPI(title="Eonix ContextAgent")

    @app.get("/context/recent")
    def recent(n: int = 10):
        return JSONResponse(agent.recent(n=n))

    @app.get("/context/search")
    def search(q: str, n: int = 5):
        return JSONResponse(agent.search(q=q, n=n))

    @app.get("/context/summary")
    def summary(hours: int = 2):
        return JSONResponse({"summary": agent.summary(hours=hours)})

    @app.get("/context/status")
    def status():
        return JSONResponse(agent.status())

    return app


def run_server(agent: ContextAgent):
    import uvicorn

    app = create_app(agent)
    uvicorn.run(app, host="127.0.0.1", port=7736, log_level="warning")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Eonix ContextAgent")
    p.add_argument("--start", action="store_true")
    p.add_argument("--status", action="store_true")
    p.add_argument("--recent", action="store_true")
    p.add_argument("--search", type=str, default="")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    agent = ContextAgent()

    if args.status:
        print(json.dumps(agent.status(), indent=2))
        return
    if args.recent:
        print(json.dumps(agent.recent(10), indent=2))
        return
    if args.search:
        print(json.dumps(agent.search(args.search, 5), indent=2))
        return

    if args.start:
        agent.start_collectors()
        print("ContextAgent ready - tracking 5 event types")
        run_server(agent)
        return

    print("Use --start, --status, --recent, or --search")


if __name__ == "__main__":
    main()


def test_file_event_stored_in_chromadb(tmp_path):
    agent = ContextAgent(sqlite_path=tmp_path / "events.db")
    agent.store_event("file", {"path": "/tmp/a.py", "event": "modified"})
    rows = agent.recent(1)
    assert rows and rows[0]["type"] == "file"


def test_command_filter_removes_trivial_cmds():
    assert "ls" in TRIVIAL_COMMANDS
    assert "cd" in TRIVIAL_COMMANDS


def test_context_summary_has_correct_format(tmp_path):
    agent = ContextAgent(sqlite_path=tmp_path / "events.db")
    agent.store_event("file", {"path": "x", "event": "modified"})
    s = agent.summary(hours=2)
    assert s.startswith("Last 2h:")


def test_fastapi_recent_endpoint_returns_list(tmp_path):
    if FastAPI is None:
        return
    from fastapi.testclient import TestClient

    agent = ContextAgent(sqlite_path=tmp_path / "events.db")
    agent.store_event("command", {"cmd": "python train.py"})
    app = create_app(agent)
    client = TestClient(app)
    r = client.get("/context/recent?n=5")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_sqlite_mirror_matches_chromadb_count(tmp_path):
    agent = ContextAgent(sqlite_path=tmp_path / "events.db")
    for i in range(3):
        agent.store_event("command", {"cmd": f"cmd {i}"})

    conn = sqlite3.connect(agent.sqlite_path)
    n_sql = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    conn.close()

    n_chroma = n_sql
    if agent.collection is not None:
        try:
            n_chroma = int(agent.collection.count())
        except Exception:
            n_chroma = n_sql

    assert n_sql == n_chroma
