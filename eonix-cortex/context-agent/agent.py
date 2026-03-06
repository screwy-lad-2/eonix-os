"""
Eonix OS — ContextAgent
========================
Background agent that monitors file events, terminal commands, and
active window titles; embeds each event into ChromaDB for semantic
context retrieval.

Usage: python3 agent.py
"""

import os
import sys
import time
import json
import hashlib
import signal
from datetime import datetime, timezone

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    print("ERROR: watchdog not installed. Run: pip install watchdog")
    sys.exit(1)

try:
    import chromadb
except ImportError:
    chromadb = None
    print("WARNING: chromadb not installed. Events will be logged to file only.")


# ---- File System Monitor ----

class EonixFileHandler(FileSystemEventHandler):
    """Captures file create/modify/delete events."""

    def __init__(self, agent: "ContextAgent"):
        self.agent = agent

    def on_modified(self, event):
        if not event.is_directory:
            self.agent.log_event("file_modified", event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self.agent.log_event("file_created", event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            self.agent.log_event("file_deleted", event.src_path)


# ---- Context Agent ----

class ContextAgent:
    """Maintains the user's cognitive working context."""

    def __init__(self, watch_dirs: list[str] | None = None):
        self.events: list[dict] = []
        self.running = True
        self.device_id = self._get_device_id()
        self.watch_dirs = watch_dirs or [os.path.expanduser("~")]

        # ChromaDB for vector storage
        self.collection = None
        if chromadb:
            client = chromadb.Client()
            self.collection = client.get_or_create_collection(
                name="eonix_context",
                metadata={"description": "User context events"},
            )

        # Event log file (fallback / backup)
        self.log_dir = os.path.expanduser("~/.eonix")
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file = os.path.join(self.log_dir, "context_events.jsonl")

    def _get_device_id(self) -> str:
        """Generate a stable device identifier."""
        import platform
        raw = f"{platform.node()}-{platform.machine()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:12]

    def log_event(self, event_type: str, detail: str):
        """Record a context event."""
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "detail": detail,
            "device_id": self.device_id,
        }
        self.events.append(event)

        # Write to log file
        with open(self.log_file, "a") as f:
            f.write(json.dumps(event) + "\n")

        # Store in ChromaDB if available
        if self.collection:
            doc_text = f"{event_type}: {detail}"
            doc_id = hashlib.sha256(
                f"{event['timestamp']}-{detail}".encode()
            ).hexdigest()[:16]

            self.collection.add(
                documents=[doc_text],
                ids=[doc_id],
                metadatas=[event],
            )

    def get_recent(self, limit: int = 50) -> list[dict]:
        """Return the most recent context events."""
        return self.events[-limit:]

    def search_context(self, query: str, limit: int = 10) -> list:
        """Semantic search across context events."""
        if not self.collection:
            return []

        results = self.collection.query(
            query_texts=[query],
            n_results=limit,
        )
        return results.get("documents", [[]])[0]

    def run(self):
        """Start the context agent."""
        print(f"[ContextAgent] Device ID: {self.device_id}")
        print(f"[ContextAgent] Watching: {self.watch_dirs}")
        print(f"[ContextAgent] Log: {self.log_file}")
        print("[ContextAgent] Press Ctrl+C to stop\n")

        # File system observer
        observer = Observer()
        handler = EonixFileHandler(self)

        for watch_dir in self.watch_dirs:
            if os.path.isdir(watch_dir):
                observer.schedule(handler, watch_dir, recursive=True)

        observer.start()

        def signal_handler(sig, frame):
            self.running = False

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        try:
            while self.running:
                time.sleep(1)
        finally:
            observer.stop()
            observer.join()

        print(f"\n[ContextAgent] Stopped. Total events: {len(self.events)}")


if __name__ == "__main__":
    # Watch the home directory and project directory
    dirs_to_watch = [
        os.path.expanduser("~/Projects"),
    ]
    agent = ContextAgent(watch_dirs=dirs_to_watch)
    agent.run()
