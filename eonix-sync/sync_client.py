# -*- coding: utf-8 -*-
"""Eonix Sync Client — push/pull tables from sync server."""
import time
import json
import urllib.request
import urllib.error


class EonixSyncClient:
    SERVER = "http://localhost:7740"

    def push_table(self, table, rows):
        data = json.dumps({
            "table": table,
            "rows": rows,
            "device_id": "eonix-pc",
            "timestamp": time.time()
        }).encode()
        req = urllib.request.Request(
            f"{self.SERVER}/sync/push",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read())

    def pull_table(self, table, since=0):
        url = f"{self.SERVER}/sync/pull?table={table}&since={since}"
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.loads(r.read())

    def full_sync(self):
        results = {}
        for t in ["notes", "goals", "settings"]:
            try:
                pulled = self.pull_table(t)
                results[t] = {"pulled": len(pulled.get("rows", []))}
            except Exception as e:
                results[t] = {"error": str(e)}
        return results

    def status(self):
        url = f"{self.SERVER}/sync/status"
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                return json.loads(r.read())
        except Exception as e:
            return {"error": str(e)}
