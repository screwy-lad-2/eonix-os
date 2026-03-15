#!/usr/bin/env python3
"""Persistent long-term memory for Eonix MIND."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

try:
    import chromadb
except Exception:
    chromadb = None


class EonixMemory:
    COLLECTION = "eonix_mind_memory"
    DB_PATH = str(Path.home() / ".eonix" / "mind_memory")

    def __init__(self, db_path: Optional[str] = None, collection_name: Optional[str] = None):
        self.db_path = db_path or self.DB_PATH
        self.collection_name = collection_name or self.COLLECTION
        self.sqlite_path = str(Path(self.db_path) / "memory_fallback.db")

        Path(self.db_path).mkdir(parents=True, exist_ok=True)

        self.client = None
        self.collection = None
        self.model = None
        self._embedding_load_attempted = False

        if chromadb is not None:
            try:
                self.client = chromadb.PersistentClient(path=self.db_path)
                self.collection = self.client.get_or_create_collection(self.collection_name)
            except Exception:
                self.collection = None

        self._init_fallback_sqlite()

    def _ensure_embedding_model(self) -> None:
        if self._embedding_load_attempted:
            return
        self._embedding_load_attempted = True
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            self.model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        except Exception:
            self.model = None

    def _init_fallback_sqlite(self) -> None:
        conn = sqlite3.connect(self.sqlite_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                category TEXT NOT NULL,
                importance INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                source TEXT NOT NULL
            )
            """
        )
        conn.commit()
        conn.close()

    def _fallback_remember(self, memory_id: str, text: str, category: str, importance: int, ts: str) -> None:
        conn = sqlite3.connect(self.sqlite_path)
        conn.execute(
            "INSERT INTO memories(id,text,category,importance,timestamp,source) VALUES (?,?,?,?,?,?)",
            (memory_id, text, category, int(importance), ts, "user"),
        )
        conn.commit()
        conn.close()

    def _fallback_score(self, text: str, query: str, importance: int) -> float:
        words = set([w for w in query.lower().split() if w])
        doc = text.lower()
        overlap = sum(1 for w in words if w in doc)
        return float(overlap) + (0.01 * float(importance))

    def _fallback_recall(self, query: str, n: int) -> List[Dict]:
        conn = sqlite3.connect(self.sqlite_path)
        rows = conn.execute(
            "SELECT id,text,category,importance,timestamp FROM memories ORDER BY timestamp DESC"
        ).fetchall()
        conn.close()

        scored = []
        for _, text, category, importance, ts in rows:
            score = self._fallback_score(str(text), query, int(importance))
            scored.append(
                {
                    "text": str(text),
                    "category": str(category),
                    "timestamp": str(ts),
                    "score": round(score, 4),
                }
            )

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:n]

    def _fallback_recall_by_category(self, category: str) -> List[Dict]:
        conn = sqlite3.connect(self.sqlite_path)
        rows = conn.execute(
            "SELECT text,category,timestamp FROM memories WHERE category=? ORDER BY timestamp DESC",
            (category,),
        ).fetchall()
        conn.close()
        return [
            {
                "text": str(text),
                "category": str(cat),
                "timestamp": str(ts),
                "score": 1.0,
            }
            for text, cat, ts in rows
        ]

    def _fallback_forget(self, memory_id: str) -> None:
        conn = sqlite3.connect(self.sqlite_path)
        conn.execute("DELETE FROM memories WHERE id=?", (memory_id,))
        conn.commit()
        conn.close()

    def _fallback_stats(self) -> Dict:
        conn = sqlite3.connect(self.sqlite_path)
        rows = conn.execute("SELECT category,timestamp FROM memories").fetchall()
        conn.close()

        categories: Dict[str, int] = {}
        ts = []
        for cat, stamp in rows:
            c = str(cat)
            categories[c] = categories.get(c, 0) + 1
            ts.append(str(stamp))

        ts.sort()
        return {
            "total_memories": len(rows),
            "categories": categories,
            "oldest_memory": ts[0] if ts else "",
            "newest_memory": ts[-1] if ts else "",
        }

    def _embed(self, text: str) -> List[float]:
        self._ensure_embedding_model()
        if self.model is None:
            return []
        try:
            return self.model.encode([text])[0].tolist()
        except Exception:
            return []

    def _norm_score(self, distance: float) -> float:
        return 1.0 / (1.0 + max(0.0, float(distance)))

    def remember(self, text: str, category: str = "general", importance: int = 1) -> str:
        memory_id = str(uuid.uuid4())
        ts = datetime.now(timezone.utc).isoformat()

        if self.collection is None:
            self._fallback_remember(memory_id, text, category, importance, ts)
            return memory_id

        metadata = {
            "category": category,
            "importance": int(importance),
            "timestamp": ts,
            "source": "user",
        }
        emb = self._embed(text)

        kwargs = {
            "ids": [memory_id],
            "documents": [text],
            "metadatas": [metadata],
        }
        if emb:
            kwargs["embeddings"] = [emb]
        self.collection.add(**kwargs)
        return memory_id

    def recall(self, query: str, n: int = 5) -> List[Dict]:
        if self.collection is None:
            return self._fallback_recall(query, n)

        try:
            q = (query or "").strip()
            emb = self._embed(q) if q else []
            if emb:
                res = self.collection.query(query_embeddings=[emb], n_results=n)
            else:
                res = self.collection.query(query_texts=[q], n_results=n)
        except Exception:
            return []

        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]

        out = []
        for i, doc in enumerate(docs):
            meta = metas[i] if i < len(metas) and isinstance(metas[i], dict) else {}
            dist = dists[i] if i < len(dists) else 1.0
            out.append(
                {
                    "text": doc,
                    "category": str(meta.get("category", "general")),
                    "timestamp": str(meta.get("timestamp", "")),
                    "score": round(self._norm_score(float(dist)), 4),
                }
            )

        out.sort(key=lambda x: x["score"], reverse=True)
        return out

    def recall_by_category(self, category: str) -> List[Dict]:
        if self.collection is None:
            return self._fallback_recall_by_category(category)

        try:
            res = self.collection.get(where={"category": category}, include=["documents", "metadatas"])
        except Exception:
            return []

        docs = res.get("documents", [])
        metas = res.get("metadatas", [])
        out = []
        for i, doc in enumerate(docs):
            meta = metas[i] if i < len(metas) and isinstance(metas[i], dict) else {}
            out.append(
                {
                    "text": doc,
                    "category": str(meta.get("category", "general")),
                    "timestamp": str(meta.get("timestamp", "")),
                    "score": 1.0,
                }
            )
        return out

    def forget(self, memory_id: str) -> None:
        if self.collection is None:
            self._fallback_forget(memory_id)
            return
        try:
            self.collection.delete(ids=[memory_id])
        except Exception:
            pass

    def stats(self) -> Dict:
        if self.collection is None:
            return self._fallback_stats()

        try:
            res = self.collection.get(include=["metadatas"])
        except Exception:
            return {
                "total_memories": 0,
                "categories": {},
                "oldest_memory": "",
                "newest_memory": "",
            }

        metas = [m for m in res.get("metadatas", []) if isinstance(m, dict)]
        total = len(metas)
        categories: Dict[str, int] = {}
        timestamps = []

        for m in metas:
            cat = str(m.get("category", "general"))
            categories[cat] = categories.get(cat, 0) + 1
            ts = str(m.get("timestamp", ""))
            if ts:
                timestamps.append(ts)

        timestamps.sort()
        return {
            "total_memories": total,
            "categories": categories,
            "oldest_memory": timestamps[0] if timestamps else "",
            "newest_memory": timestamps[-1] if timestamps else "",
        }

    def format_relevant(self, query: str) -> str:
        found = self.recall(query, n=3)
        if not found:
            return ""

        parts = []
        for i, item in enumerate(found):
            if i == 0:
                parts.append(f"I remember: {item['text']}.")
            else:
                parts.append(f"Also: {item['text']}.")

        text = " ".join(parts)
        words = text.split()
        if len(words) > 150:
            return " ".join(words[:150])
        return text


def test_remember_stores_and_recall_finds_it(tmp_path):
    m = EonixMemory(db_path=str(tmp_path / "mem"), collection_name="t1")
    mid = m.remember("My B.Tech project deadline is May 2027", category="deadline")
    out = m.recall("deadline", n=5)
    assert mid
    assert any("deadline" in x["text"].lower() for x in out)


def test_recall_returns_semantically_relevant(tmp_path):
    m = EonixMemory(db_path=str(tmp_path / "mem"), collection_name="t2")
    m.remember("My deadline is April 15", category="deadline")
    m.remember("I prefer concise responses", category="preference")
    out = m.recall("when is my deadline", n=3)
    assert out
    assert "deadline" in out[0]["text"].lower()


def test_forget_removes_from_chromadb(tmp_path):
    m = EonixMemory(db_path=str(tmp_path / "mem"), collection_name="t3")
    mid = m.remember("Remember this command", category="command")
    m.forget(mid)
    out = m.recall("remember this command", n=5)
    assert all("remember this command" not in x["text"].lower() for x in out)


def test_stats_returns_correct_counts(tmp_path):
    m = EonixMemory(db_path=str(tmp_path / "mem"), collection_name="t4")
    m.remember("my professor is Dr. Sharma", category="person")
    m.remember("I prefer dark mode", category="preference")
    s = m.stats()
    assert s["total_memories"] == 2
    assert s["categories"].get("person", 0) == 1


def test_format_relevant_under_150_tokens(tmp_path):
    m = EonixMemory(db_path=str(tmp_path / "mem"), collection_name="t5")
    m.remember("I am building an OS for college", category="project")
    m.remember("My deadline is April 15", category="deadline")
    txt = m.format_relevant("project and deadline")
    assert len(txt.split()) <= 150
