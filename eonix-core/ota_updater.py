"""Eonix OTA Updater — check for updates, backup, apply.

Checks GitHub releases API for new versions.
Backs up config before updates. Applies minor
updates via git pull.
"""
import os
import shutil
import datetime


class EonixOTA:
    CURRENT_VERSION = "1.5.0"
    RELEASES_URL = (
        "https://api.github.com/repos/"
        "screwy-lad-2/eonix-os/releases/latest")
    BACKUP_DIR = os.path.expanduser("~/.eonix_backup")
    CONFIG_DIR = os.path.expanduser("~/.config/eonix")

    def check_for_updates(self):
        import urllib.request
        import json
        try:
            req = urllib.request.Request(
                self.RELEASES_URL,
                headers={"User-Agent": "EonixOS/1.5"})
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read().decode())
            latest = data.get("tag_name", "v1.5.0").lstrip("v")
            notes = data.get("body", "")
            assets = data.get("assets", [])
            size_mb = sum(a.get("size", 0) for a in assets) / (1024 * 1024)
            available = latest != self.CURRENT_VERSION
            level = self._level(self.CURRENT_VERSION, latest)
            return {
                "available": available,
                "latest": latest,
                "current": self.CURRENT_VERSION,
                "notes": notes,
                "size_mb": round(size_mb, 1),
                "level": level,
            }
        except Exception as e:
            return {"available": False, "error": str(e)}

    def _level(self, cur, new):
        try:
            c = [int(x) for x in cur.split(".")]
            n = [int(x) for x in new.split(".")]
            if n[0] > c[0]:
                return "critical"
            if n[1] > c[1]:
                return "major"
            return "minor"
        except Exception:
            return "major"

    def backup_config(self):
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = os.path.join(self.BACKUP_DIR, ts)
        os.makedirs(dest, exist_ok=True)
        if os.path.exists(self.CONFIG_DIR):
            shutil.copytree(
                self.CONFIG_DIR,
                os.path.join(dest, "eonix_config"),
                dirs_exist_ok=True)
        return dest

    def apply_minor_update(self):
        import subprocess
        r = subprocess.run(
            ["git", "-C", "/opt/eonix", "pull", "origin", "master"],
            capture_output=True, text=True, timeout=60)
        return r.stdout.strip()
