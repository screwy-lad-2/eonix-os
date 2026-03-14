#!/usr/bin/env python3
"""Eonix GoalEngine: persistent goal tracking service."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

try:
    import chromadb
except Exception:
    chromadb = None

try:
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
except Exception:
    FastAPI = None  # type: ignore
    JSONResponse = None  # type: ignore
    BaseModel = object  # type: ignore


HOME = Path.home()
EONIX_DIR = HOME / ".eonix"
GOALS_DB = EONIX_DIR / "goals.db"
ACTIVE_GOAL_FILE = EONIX_DIR / "active_goal.txt"
GOAL_CHROMA_DIR = EONIX_DIR / "goals_chroma"
GOAL_COLLECTION = "eonix_goals"
CONTEXT_BASE = "http://127.0.0.1:7736"
REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Goal:
    id: str
    name: str
    description: str
    created_at: str
    status: str
    progress: float
    tags: List[str]
    workspace: Dict
    embedding: List[float]


class GoalEngine:
    def __init__(
        self,
        sqlite_path: Path = GOALS_DB,
        chroma_path: Path = GOAL_CHROMA_DIR,
        active_goal_file: Path = ACTIVE_GOAL_FILE,
        context_base: str = CONTEXT_BASE,
    ):
        self.sqlite_path = sqlite_path
        self.chroma_path = chroma_path
        self.active_goal_file = active_goal_file
        self.context_base = context_base

        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.chroma_path.mkdir(parents=True, exist_ok=True)
        self.active_goal_file.parent.mkdir(parents=True, exist_ok=True)

        self.embedding_model = None
        self._embedding_load_attempted = False
        self.chroma = None
        self.collection = None

        self._init_sqlite()
        self._init_chroma()

    def _init_sqlite(self) -> None:
        conn = sqlite3.connect(self.sqlite_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS goals (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL,
                progress REAL NOT NULL,
                tags TEXT NOT NULL,
                workspace TEXT NOT NULL,
                completed_at TEXT
            )
            """
        )
        conn.commit()
        conn.close()

    def _init_chroma(self) -> None:
        if chromadb is None:
            return
        try:
            self.chroma = chromadb.PersistentClient(path=str(self.chroma_path))
            self.collection = self.chroma.get_or_create_collection(GOAL_COLLECTION)
        except Exception:
            self.collection = None

    def _ensure_embedding_model(self) -> None:
        if self._embedding_load_attempted:
            return
        self._embedding_load_attempted = True
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            self.embedding_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        except Exception:
            self.embedding_model = None

    def _embed(self, text: str) -> List[float]:
        self._ensure_embedding_model()
        if self.embedding_model is None:
            return []
        try:
            return self.embedding_model.encode([text])[0].tolist()
        except Exception:
            return []

    def _row_to_goal(self, row) -> Goal:
        return Goal(
            id=row[0],
            name=row[1],
            description=row[2],
            created_at=row[3],
            status=row[4],
            progress=float(row[5]),
            tags=json.loads(row[6]) if row[6] else [],
            workspace=json.loads(row[7]) if row[7] else {},
            embedding=[],
        )

    def _get_goal(self, goal_id: str) -> Optional[Goal]:
        conn = sqlite3.connect(self.sqlite_path)
        row = conn.execute(
            "SELECT id,name,description,created_at,status,progress,tags,workspace FROM goals WHERE id=?",
            (goal_id,),
        ).fetchone()
        conn.close()
        if row is None:
            return None
        return self._row_to_goal(row)

    def _set_active_goal_name(self, name: str) -> None:
        self.active_goal_file.write_text(name.strip(), encoding="utf-8")

    def _clear_active_goal_name(self) -> None:
        self.active_goal_file.write_text("", encoding="utf-8")

    def create(self, name: str, description: str = "", tags: Optional[List[str]] = None, workspace: Optional[Dict] = None) -> Goal:
        goal = Goal(
            id=str(uuid.uuid4()),
            name=name.strip(),
            description=description.strip(),
            created_at=datetime.now(timezone.utc).isoformat(),
            status="active",
            progress=0.0,
            tags=tags or [],
            workspace=workspace or {},
            embedding=self._embed(f"{name} {description}"),
        )

        conn = sqlite3.connect(self.sqlite_path)
        conn.execute("UPDATE goals SET status='paused' WHERE status='active'")
        conn.execute(
            "INSERT INTO goals(id,name,description,created_at,status,progress,tags,workspace,completed_at) VALUES (?,?,?,?,?,?,?,?,NULL)",
            (
                goal.id,
                goal.name,
                goal.description,
                goal.created_at,
                goal.status,
                goal.progress,
                json.dumps(goal.tags, ensure_ascii=False),
                json.dumps(goal.workspace, ensure_ascii=False),
            ),
        )
        conn.commit()
        conn.close()

        self._set_active_goal_name(goal.name)

        if self.collection is not None:
            try:
                kwargs = {
                    "ids": [goal.id],
                    "documents": [f"{goal.name} {goal.description}".strip()],
                    "metadatas": [
                        {
                            "name": goal.name,
                            "description": goal.description,
                            "created_at": goal.created_at,
                            "status": goal.status,
                        }
                    ],
                }
                if goal.embedding:
                    kwargs["embeddings"] = [goal.embedding]
                self.collection.add(**kwargs)
            except Exception:
                pass

        return goal

    def activate(self, goal_id: str) -> Goal:
        goal = self._get_goal(goal_id)
        if goal is None:
            raise ValueError("goal not found")

        conn = sqlite3.connect(self.sqlite_path)
        conn.execute("UPDATE goals SET status='paused' WHERE id<>? AND status='active'", (goal_id,))
        conn.execute("UPDATE goals SET status='active' WHERE id=?", (goal_id,))
        conn.commit()
        conn.close()

        goal.status = "active"
        self._set_active_goal_name(goal.name)
        self._open_workspace(goal)
        return goal

    def complete(self, goal_id: str) -> None:
        goal = self._get_goal(goal_id)
        if goal is None:
            raise ValueError("goal not found")

        was_active = goal.status == "active"

        conn = sqlite3.connect(self.sqlite_path)
        conn.execute(
            "UPDATE goals SET status='completed', completed_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), goal_id),
        )
        conn.commit()
        conn.close()

        if was_active:
            self._clear_active_goal_name()

        if self.collection is not None:
            try:
                self.collection.update(ids=[goal_id], metadatas=[{"status": "completed"}])
            except Exception:
                pass

    def _http_json(self, path: str):
        url = f"{self.context_base}{path}"
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
            return None

    def _git_commits_since(self, since_iso: str) -> int:
        try:
            out = subprocess.check_output(
                ["git", "-C", str(REPO_ROOT), "log", "--since", since_iso, "--pretty=%H"],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            return len([x for x in out.splitlines() if x.strip()])
        except Exception:
            return 0

    def _context_metrics(self, goal: Goal) -> tuple[int, float]:
        recent = self._http_json("/context/recent?n=500")
        if not isinstance(recent, list):
            return 0, 0.0

        topic_words = [w for w in (goal.name + " " + goal.description).lower().split() if len(w) >= 4]
        files = set()
        focus_count = 0

        for evt in recent:
            et = str(evt.get("type", ""))
            if et == "file":
                path = str(evt.get("path", "")).lower()
                if topic_words and any(w in path for w in topic_words):
                    files.add(path)
            elif et == "focus":
                focus_count += 1

        # Focus collector emits on window changes; use a conservative approximation.
        hours_active = round(focus_count * 0.1, 2)
        return len(files), hours_active

    def estimate_progress(self, goal_id: str) -> float:
        goal = self._get_goal(goal_id)
        if goal is None:
            raise ValueError("goal not found")

        commits = self._git_commits_since(goal.created_at)
        files_edited, hours_active = self._context_metrics(goal)
        manual_override = 0.0
        if isinstance(goal.workspace, dict):
            try:
                manual_override = float(goal.workspace.get("manual_override", 0.0))
            except Exception:
                manual_override = 0.0

        progress = min(
            1.0,
            (commits * 0.15)
            + (files_edited * 0.05)
            + ((hours_active / 8.0) * 0.3)
            + manual_override,
        )

        conn = sqlite3.connect(self.sqlite_path)
        conn.execute("UPDATE goals SET progress=? WHERE id=?", (progress, goal_id))
        conn.commit()
        conn.close()

        return float(progress)

    def list_goals(self) -> List[Goal]:
        conn = sqlite3.connect(self.sqlite_path)
        rows = conn.execute(
            "SELECT id,name,description,created_at,status,progress,tags,workspace FROM goals ORDER BY created_at DESC"
        ).fetchall()
        conn.close()
        return [self._row_to_goal(r) for r in rows]

    def active_goal(self) -> Optional[Goal]:
        conn = sqlite3.connect(self.sqlite_path)
        row = conn.execute(
            "SELECT id,name,description,created_at,status,progress,tags,workspace FROM goals WHERE status='active' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if row is None:
            return None
        return self._row_to_goal(row)

    def search(self, query: str) -> List[Goal]:
        if self.collection is not None:
            try:
                kwargs = {"query_texts": [query], "n_results": 3}
                emb = self._embed(query)
                if emb:
                    kwargs = {"query_embeddings": [emb], "n_results": 3}
                res = self.collection.query(**kwargs)
                ids = res.get("ids", [[]])[0]
                out = []
                for gid in ids:
                    g = self._get_goal(gid)
                    if g is not None:
                        out.append(g)
                if out:
                    return out
            except Exception:
                pass

        conn = sqlite3.connect(self.sqlite_path)
        rows = conn.execute(
            "SELECT id,name,description,created_at,status,progress,tags,workspace FROM goals WHERE name LIKE ? OR description LIKE ? ORDER BY created_at DESC LIMIT 3",
            (f"%{query}%", f"%{query}%"),
        ).fetchall()
        conn.close()
        return [self._row_to_goal(r) for r in rows]

    def _open_workspace(self, goal: Goal) -> None:
        workspace = goal.workspace if isinstance(goal.workspace, dict) else {}
        files = workspace.get("files", []) if isinstance(workspace.get("files", []), list) else []
        urls = workspace.get("urls", []) if isinstance(workspace.get("urls", []), list) else []
        apps = workspace.get("apps", []) if isinstance(workspace.get("apps", []), list) else []

        for f in files:
            try:
                subprocess.Popen(["code", str(f)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

        for u in urls:
            try:
                if sys.platform.startswith("win"):
                    os.startfile(u)  # type: ignore[attr-defined]
                elif sys.platform == "darwin":
                    subprocess.Popen(["open", u], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    subprocess.Popen(["xdg-open", u], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

        for app in apps:
            try:
                if isinstance(app, list):
                    subprocess.Popen(app, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    subprocess.Popen(str(app).split(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

        print(f"Workspace loaded for: {goal.name}")


class GoalCreateBody(BaseModel):
    name: str
    description: str = ""


class GoalActionBody(BaseModel):
    goal_id: str


def create_app(engine: GoalEngine):
    if FastAPI is None:
        raise RuntimeError("fastapi is not installed")

    app = FastAPI(title="Eonix GoalEngine")

    @app.post("/goal/create")
    def goal_create(body: GoalCreateBody):
        goal = engine.create(name=body.name, description=body.description)
        return JSONResponse(asdict(goal))

    @app.post("/goal/activate")
    def goal_activate(body: GoalActionBody):
        try:
            goal = engine.activate(body.goal_id)
            return JSONResponse(asdict(goal))
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=404)

    @app.post("/goal/complete")
    def goal_complete(body: GoalActionBody):
        try:
            engine.complete(body.goal_id)
            return JSONResponse({"ok": True})
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=404)

    @app.get("/goal/active")
    def goal_active():
        g = engine.active_goal()
        return JSONResponse(asdict(g) if g else {})

    @app.get("/goal/list")
    def goal_list():
        return JSONResponse([asdict(g) for g in engine.list_goals()])

    @app.get("/goal/progress/{goal_id}")
    def goal_progress(goal_id: str):
        try:
            progress = engine.estimate_progress(goal_id)
            return JSONResponse({"goal_id": goal_id, "progress": progress})
        except ValueError as e:
            return JSONResponse({"error": str(e)}, status_code=404)

    @app.get("/goal/search")
    def goal_search(q: str):
        return JSONResponse([asdict(g) for g in engine.search(q)])

    @app.get("/goal/status")
    def goal_status():
        return JSONResponse(
            {
                "running": True,
                "chroma_active": engine.collection is not None,
                "embedding_active": engine.embedding_model is not None,
            }
        )

    return app


def run_server(engine: GoalEngine) -> None:
    import uvicorn

    app = create_app(engine)
    uvicorn.run(app, host="127.0.0.1", port=7735, log_level="warning")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Eonix GoalEngine")
    p.add_argument("--start", action="store_true")
    p.add_argument("--status", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    engine = GoalEngine()

    if args.status:
        print(
            json.dumps(
                {
                    "goals": len(engine.list_goals()),
                    "active": asdict(engine.active_goal()) if engine.active_goal() else None,
                    "chroma_active": engine.collection is not None,
                },
                indent=2,
            )
        )
        return

    if args.start:
        print("GoalEngine ready on http://127.0.0.1:7735")
        run_server(engine)
        return

    print("Use --start or --status")


if __name__ == "__main__":
    main()


def test_create_goal_stores_in_sqlite(tmp_path):
    eng = GoalEngine(
        sqlite_path=tmp_path / "goals.db",
        chroma_path=tmp_path / "chroma",
        active_goal_file=tmp_path / "active_goal.txt",
        context_base="http://127.0.0.1:9999",
    )
    g = eng.create("Build EONIX MIND", "Month 4 main task")

    conn = sqlite3.connect(eng.sqlite_path)
    n = conn.execute("SELECT COUNT(*) FROM goals WHERE id=?", (g.id,)).fetchone()[0]
    conn.close()
    assert n == 1


def test_active_goal_file_updated_on_create(tmp_path):
    eng = GoalEngine(
        sqlite_path=tmp_path / "goals.db",
        chroma_path=tmp_path / "chroma",
        active_goal_file=tmp_path / "active_goal.txt",
        context_base="http://127.0.0.1:9999",
    )
    g = eng.create("Build EONIX MIND", "Month 4 main task")
    assert eng.active_goal_file.read_text(encoding="utf-8").strip() == g.name


def test_estimate_progress_returns_0_to_1(tmp_path):
    eng = GoalEngine(
        sqlite_path=tmp_path / "goals.db",
        chroma_path=tmp_path / "chroma",
        active_goal_file=tmp_path / "active_goal.txt",
        context_base="http://127.0.0.1:9999",
    )
    g = eng.create("Build EONIX MIND", "Month 4 main task")
    p = eng.estimate_progress(g.id)
    assert 0.0 <= p <= 1.0


def test_search_returns_semantically_relevant_goal(tmp_path):
    eng = GoalEngine(
        sqlite_path=tmp_path / "goals.db",
        chroma_path=tmp_path / "chroma",
        active_goal_file=tmp_path / "active_goal.txt",
        context_base="http://127.0.0.1:9999",
    )
    eng.create("Build EONIX MIND", "Month 4 main task")
    time.sleep(0.01)
    eng.create("Read operating systems book", "Study")
    res = eng.search("mind")
    assert res and "mind" in (res[0].name + " " + res[0].description).lower()


def test_complete_goal_clears_active_file(tmp_path):
    eng = GoalEngine(
        sqlite_path=tmp_path / "goals.db",
        chroma_path=tmp_path / "chroma",
        active_goal_file=tmp_path / "active_goal.txt",
        context_base="http://127.0.0.1:9999",
    )
    g = eng.create("Build EONIX MIND", "Month 4 main task")
    eng.complete(g.id)
    assert eng.active_goal_file.read_text(encoding="utf-8").strip() == ""


def test_list_goals_sorted_by_created_at(tmp_path):
    eng = GoalEngine(
        sqlite_path=tmp_path / "goals.db",
        chroma_path=tmp_path / "chroma",
        active_goal_file=tmp_path / "active_goal.txt",
        context_base="http://127.0.0.1:9999",
    )
    g1 = eng.create("Goal One", "")
    time.sleep(0.01)
    g2 = eng.create("Goal Two", "")
    goals = eng.list_goals()
    assert goals[0].id == g2.id
    assert goals[1].id == g1.id
