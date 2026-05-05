"""Eonix File Intelligence Engine.

Scans, categorizes, and indexes all files.
Background 60s refresh. Exposes search, stats, organize APIs.
Used by AI Chat, Smart Files UI, and Hub REST API.
"""
import datetime
import json
import os
import shutil
import threading
import time


class EonixFileIntel:
    """AI File Intelligence Engine."""

    INDEX_PATH = os.path.expanduser("~/.config/eonix/file_index.json")

    CATEGORIES = {
        "documents": [
            ".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt",
            ".md", ".csv", ".xlsx", ".xls", ".ppt", ".pptx"],
        "images": [
            ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg",
            ".webp", ".ico", ".tiff"],
        "audio": [
            ".mp3", ".wav", ".flac", ".ogg", ".aac", ".m4a",
            ".opus", ".wma"],
        "video": [
            ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv",
            ".webm", ".m4v"],
        "code": [
            ".py", ".js", ".ts", ".html", ".css", ".json",
            ".sh", ".c", ".cpp", ".h", ".java", ".go",
            ".rs", ".yaml", ".toml"],
        "archives": [
            ".zip", ".tar", ".gz", ".bz2", ".xz", ".rar",
            ".7z", ".deb", ".iso"],
        "data": [
            ".db", ".sqlite", ".sql", ".parquet", ".feather",
            ".pkl", ".npy", ".npz"],
    }

    SKIP_DIRS = {
        ".git", "__pycache__", "node_modules", ".cache",
        "proc", "sys", "dev", "run", "snap"}

    def __init__(self):
        self._index = {}
        self._scan_root = os.path.expanduser("~")
        self._load_index()

    def _load_index(self):
        try:
            with open(self.INDEX_PATH, encoding="utf-8") as f:
                self._index = json.load(f)
        except Exception:
            self._index = {}

    def _save_index(self):
        os.makedirs(os.path.dirname(self.INDEX_PATH), exist_ok=True)
        with open(self.INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(self._index, f, indent=2)

    def scan(self, root=None):
        """Full scan. Builds index dict with files, stats, timestamps."""
        root = root or self._scan_root
        files = []
        stats = {c: 0 for c in self.CATEGORIES}
        stats["other"] = 0
        stats["total_size_bytes"] = 0
        stats["total_count"] = 0
        errors = []

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                d for d in dirnames
                if d not in self.SKIP_DIRS and not d.startswith(".")
            ]
            for fname in filenames:
                try:
                    fpath = os.path.join(dirpath, fname)
                    ext = os.path.splitext(fname)[1].lower()
                    size = os.path.getsize(fpath)
                    mtime = os.path.getmtime(fpath)
                    cat = self._cat(ext)
                    files.append({
                        "name": fname, "path": fpath, "ext": ext,
                        "size": size, "mtime": mtime, "cat": cat,
                    })
                    stats[cat] = stats.get(cat, 0) + 1
                    stats["total_count"] += 1
                    stats["total_size_bytes"] += size
                except Exception as e:
                    errors.append(str(e))

        self._index = {
            "files": files,
            "stats": stats,
            "last_scan": datetime.datetime.now().isoformat(),
            "errors": errors[:10],
        }
        self._save_index()
        return self._index

    def _cat(self, ext):
        for cat, exts in self.CATEGORIES.items():
            if ext in exts:
                return cat
        return "other"

    def search(self, query, category=None, limit=20):
        """Search files by name or extension."""
        q = query.lower()
        results = []
        for f in self._index.get("files", []):
            if category and f["cat"] != category:
                continue
            if q in f["name"].lower() or q in f["ext"]:
                results.append(f)
            if len(results) >= limit:
                break
        results.sort(key=lambda x: x["mtime"], reverse=True)
        return results

    def get_stats(self):
        return self._index.get("stats", {})

    def get_largest(self, n=10):
        files = self._index.get("files", [])
        return sorted(files, key=lambda x: x["size"], reverse=True)[:n]

    def get_recent(self, n=10):
        files = self._index.get("files", [])
        return sorted(files, key=lambda x: x["mtime"], reverse=True)[:n]

    def get_duplicates(self):
        """Find files with same name in different directories."""
        seen = {}
        dupes = []
        for f in self._index.get("files", []):
            name = f["name"].lower()
            if name in seen:
                dupes.append((seen[name], f))
            else:
                seen[name] = f
        return dupes

    def auto_organize(self, dry_run=True):
        """Move files into category folders under ~/organized/."""
        base = os.path.expanduser("~/organized")
        moves = []
        for f in self._index.get("files", []):
            if f["cat"] == "other":
                continue
            src = f["path"]
            dest_dir = os.path.join(base, f["cat"])
            dest = os.path.join(dest_dir, f["name"])
            if src == dest:
                continue
            moves.append({
                "from": src, "to": dest,
                "cat": f["cat"], "name": f["name"],
            })
            if not dry_run:
                try:
                    os.makedirs(dest_dir, exist_ok=True)
                    shutil.move(src, dest)
                except Exception:
                    pass
        return moves

    def start_background_scan(self):
        """Start background thread that rescans every 60 seconds."""
        def _loop():
            while True:
                try:
                    self.scan()
                except Exception:
                    pass
                time.sleep(60)
        t = threading.Thread(target=_loop, daemon=True)
        t.start()
