# -*- coding: utf-8 -*-
"""Eonix Sync Server — push/pull/status + notification relay."""
import sqlite3
import time
import os
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import threading

DB = os.path.expanduser("~/.config/eonix/sync.db")
TABLES = ["notes", "goals", "settings", "notifications", "file_index"]

_notifs = []


def get_db():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    # Ensure tables exist
    for t in TABLES:
        conn.execute(f"""CREATE TABLE IF NOT EXISTS '{t}' (
            id TEXT PRIMARY KEY,
            data TEXT,
            updated_at REAL DEFAULT 0
        )""")
    conn.commit()
    return conn


class SyncHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Suppress default logs

    def _send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        if path == "/sync/status":
            self._send_json({
                "version": "1.5.0",
                "tables": TABLES,
                "time": time.time(),
                "device": "eonix-pc"
            })
        elif path == "/sync/pull":
            table = params.get("table", [None])[0]
            since = float(params.get("since", [0])[0])
            if table not in TABLES:
                self._send_json({"error": "table not allowed"}, 400)
                return
            db = get_db()
            try:
                rows = db.execute(
                    f"SELECT * FROM '{table}' WHERE updated_at > ?", (since,)).fetchall()
                self._send_json({
                    "rows": [dict(r) for r in rows],
                    "table": table,
                    "timestamp": time.time()
                })
            except sqlite3.OperationalError:
                self._send_json({"rows": [], "table": table, "timestamp": time.time()})
            finally:
                db.close()
        elif path == "/notify/poll":
            since = float(params.get("since", [0])[0])
            self._send_json({"items": [n for n in _notifs if n["time"] > since]})
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/sync/push":
            data = self._read_body()
            table = data.get("table")
            rows = data.get("rows", [])
            dev_id = data.get("device_id", "unknown")
            if table not in TABLES:
                self._send_json({"error": "table not allowed"}, 400)
                return
            db = get_db()
            merged = 0
            for row in rows:
                rid = row.get("id")
                ts = float(row.get("updated_at", time.time()))
                cur = db.execute(
                    f"SELECT updated_at FROM '{table}' WHERE id=?", (rid,)).fetchone()
                if cur is None or float(cur["updated_at"]) < ts:
                    db.execute(
                        f"INSERT OR REPLACE INTO '{table}' (id, data, updated_at) VALUES (?, ?, ?)",
                        (rid, json.dumps(row), ts))
                    merged += 1
            db.commit()
            db.close()
            self._send_json({"merged": merged, "device": dev_id})
        elif path == "/notify/send":
            data = self._read_body()
            msg = data.get("message", "")
            _notifs.append({"msg": msg, "time": time.time()})
            self._send_json({"ok": True})
        else:
            self._send_json({"error": "not found"}, 404)


def start_server(port=7740):
    server = HTTPServer(("0.0.0.0", port), SyncHandler)
    print(f"[Sync] Server running on :{port}")
    server.serve_forever()


if __name__ == "__main__":
    start_server()
