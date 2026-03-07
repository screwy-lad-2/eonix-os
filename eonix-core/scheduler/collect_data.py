#!/usr/bin/env python3
"""
Eonix OS — Scheduler Data Collector Daemon
============================================
Background daemon that monitors the process table every 200ms, detects
LAUNCH and EXIT events, and stores them in SQLite for later ML training
of the predictive scheduler.

Usage:
    python collect_data.py --daemon        # Start as background process
    python collect_data.py --foreground    # Run in foreground (dev/debug)
    python collect_data.py --stop          # Stop the running daemon
    python collect_data.py --status        # Check if daemon is running
    python collect_data.py --install       # Auto-start on login (Windows Task Scheduler)
    python collect_data.py --uninstall     # Remove auto-start task

Data is stored at:  ~/.eonix/scheduler_data.db
PID file:           ~/.eonix/collector.pid
Log file:           ~/.eonix/collector.log
"""

import argparse
import atexit
import logging
import os
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta

import psutil

IS_WINDOWS = sys.platform == "win32"
TASK_NAME = "EonixSchedulerCollector"

# ---- Paths ----
EONIX_DIR = os.path.expanduser("~/.eonix")
DB_PATH = os.path.join(EONIX_DIR, "scheduler_data.db")
PID_FILE = os.path.join(EONIX_DIR, "collector.pid")
LOG_FILE = os.path.join(EONIX_DIR, "collector.log")

# ---- Configuration ----
POLL_INTERVAL_SEC = 0.2          # 200ms
LOG_STATS_INTERVAL_SEC = 3600    # 1 hour
DB_ROTATE_WEEKS = 4              # Keep last 4 weeks of data
DB_ROTATE_CHECK_SEC = 86400      # Check rotation once per day


def ensure_dirs():
    """Create ~/.eonix/ directory if it doesn't exist."""
    os.makedirs(EONIX_DIR, exist_ok=True)


# ---- Logging ----

def setup_logging(foreground: bool = False):
    """Configure logging to file (and optionally stdout)."""
    ensure_dirs()
    handlers = [
        logging.FileHandler(LOG_FILE),
    ]
    if foreground:
        handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )


# ---- Database ----

def init_db() -> sqlite3.Connection:
    """Initialize SQLite database with the events schema."""
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL NOT NULL,
            event_type TEXT NOT NULL,
            pid INTEGER NOT NULL,
            name TEXT,
            cpu_percent REAL,
            memory_percent REAL,
            parent_pid INTEGER,
            session_hour INTEGER,
            session_dow INTEGER
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_events_timestamp
        ON events(timestamp)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_events_type
        ON events(event_type)
    """)
    conn.commit()
    return conn


def rotate_db(conn: sqlite3.Connection):
    """Delete events older than DB_ROTATE_WEEKS weeks."""
    cutoff = time.time() - (DB_ROTATE_WEEKS * 7 * 86400)
    cursor = conn.execute(
        "DELETE FROM events WHERE timestamp < ?", (cutoff,)
    )
    deleted = cursor.rowcount
    if deleted > 0:
        conn.execute("PRAGMA optimize")
        conn.commit()
        logging.info("DB rotation: deleted %d events older than %d weeks",
                     deleted, DB_ROTATE_WEEKS)


# ---- PID File Management ----

def write_pid_file():
    """Write the current PID to the PID file."""
    ensure_dirs()
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def read_pid_file() -> int | None:
    """Read the PID from the PID file, return None if not found."""
    if not os.path.exists(PID_FILE):
        return None
    try:
        with open(PID_FILE) as f:
            return int(f.read().strip())
    except (ValueError, OSError):
        return None


def remove_pid_file():
    """Remove the PID file."""
    try:
        os.remove(PID_FILE)
    except OSError:
        pass


def is_daemon_running() -> tuple[bool, int | None]:
    """Check if the daemon is currently running."""
    pid = read_pid_file()
    if pid is None:
        return False, None
    try:
        proc = psutil.Process(pid)
        # Verify it's actually our collector process
        if "collect_data" in " ".join(proc.cmdline()):
            return True, pid
        return False, None
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        remove_pid_file()
        return False, None


# ---- Process Tracking ----

def get_process_snapshot() -> dict[int, dict]:
    """Take a snapshot of all running processes."""
    snapshot = {}
    for proc in psutil.process_iter(
        ["pid", "name", "cpu_percent", "memory_percent", "ppid"]
    ):
        try:
            info = proc.info
            snapshot[info["pid"]] = {
                "pid": info["pid"],
                "name": info["name"],
                "cpu_percent": info["cpu_percent"] or 0.0,
                "memory_percent": info["memory_percent"] or 0.0,
                "parent_pid": info["ppid"],
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return snapshot


def detect_events(
    prev_snapshot: dict[int, dict],
    curr_snapshot: dict[int, dict],
) -> list[tuple]:
    """Compare two snapshots and return LAUNCH/EXIT event rows."""
    now = time.time()
    dt = datetime.now(timezone.utc)
    session_hour = dt.hour
    session_dow = dt.weekday()  # Monday=0, Sunday=6

    events = []

    # LAUNCH: PIDs in current but not in previous
    new_pids = set(curr_snapshot.keys()) - set(prev_snapshot.keys())
    for pid in new_pids:
        p = curr_snapshot[pid]
        events.append((
            now,              # timestamp
            "LAUNCH",         # event_type
            p["pid"],         # pid
            p["name"],        # name
            p["cpu_percent"], # cpu_percent
            p["memory_percent"],  # memory_percent
            p["parent_pid"],  # parent_pid
            session_hour,     # session_hour
            session_dow,      # session_dow
        ))

    # EXIT: PIDs in previous but not in current
    gone_pids = set(prev_snapshot.keys()) - set(curr_snapshot.keys())
    for pid in gone_pids:
        p = prev_snapshot[pid]
        events.append((
            now,
            "EXIT",
            p["pid"],
            p["name"],
            p["cpu_percent"],
            p["memory_percent"],
            p["parent_pid"],
            session_hour,
            session_dow,
        ))

    return events


def store_events(conn: sqlite3.Connection, events: list[tuple]):
    """Insert event rows into the database."""
    if not events:
        return
    conn.executemany("""
        INSERT INTO events
        (timestamp, event_type, pid, name, cpu_percent,
         memory_percent, parent_pid, session_hour, session_dow)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, events)
    conn.commit()


# ---- Main Collection Loop ----

def collection_loop(foreground: bool = False):
    """Main loop: poll processes, detect events, store to DB."""
    setup_logging(foreground=foreground)
    logging.info("Eonix Scheduler Collector starting (PID %d)", os.getpid())
    logging.info("DB: %s | Poll: %dms | Rotate: %d weeks",
                 DB_PATH, int(POLL_INTERVAL_SEC * 1000), DB_ROTATE_WEEKS)

    conn = init_db()
    write_pid_file()
    atexit.register(remove_pid_file)

    # Graceful shutdown
    running = True

    def handle_signal(signum, frame):
        nonlocal running
        logging.info("Received signal %d, shutting down...", signum)
        running = False

    signal.signal(signal.SIGINT, handle_signal)
    if not IS_WINDOWS:
        signal.signal(signal.SIGTERM, handle_signal)
    else:
        signal.signal(signal.SIGBREAK, handle_signal)

    # Counters
    total_launches = 0
    total_exits = 0
    last_log_time = time.time()
    last_rotate_time = time.time()

    # Initial snapshot (don't log the initial population as LAUNCH events)
    psutil.cpu_percent(interval=None)  # prime CPU counter
    prev_snapshot = get_process_snapshot()
    logging.info("Initial snapshot: %d processes", len(prev_snapshot))

    while running:
        try:
            curr_snapshot = get_process_snapshot()
            events = detect_events(prev_snapshot, curr_snapshot)

            if events:
                store_events(conn, events)
                for ev in events:
                    if ev[1] == "LAUNCH":
                        total_launches += 1
                    else:
                        total_exits += 1

            prev_snapshot = curr_snapshot

            # Hourly stats log
            now = time.time()
            if now - last_log_time >= LOG_STATS_INTERVAL_SEC:
                row = conn.execute(
                    "SELECT COUNT(*) FROM events"
                ).fetchone()
                total_rows = row[0] if row else 0
                logging.info(
                    "Stats: launches=%d exits=%d total_db_rows=%d "
                    "tracked_pids=%d",
                    total_launches, total_exits, total_rows,
                    len(curr_snapshot),
                )
                last_log_time = now

            # Daily DB rotation check
            if now - last_rotate_time >= DB_ROTATE_CHECK_SEC:
                rotate_db(conn)
                last_rotate_time = now

            time.sleep(POLL_INTERVAL_SEC)

        except Exception:
            logging.exception("Error in collection loop")
            time.sleep(1)  # Back off on error

    # Graceful shutdown: flush and close
    logging.info(
        "Shutting down. Final stats: launches=%d exits=%d",
        total_launches, total_exits,
    )
    conn.commit()
    conn.close()
    remove_pid_file()
    logging.info("Collector stopped cleanly.")


# ---- Daemon / Background Mode ----

def daemonize_unix():
    """Double-fork to daemonize the process (Unix only)."""
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError as e:
        sys.stderr.write(f"Fork #1 failed: {e}\n")
        sys.exit(1)

    os.setsid()
    os.umask(0o022)

    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError as e:
        sys.stderr.write(f"Fork #2 failed: {e}\n")
        sys.exit(1)

    sys.stdout.flush()
    sys.stderr.flush()
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, sys.stdin.fileno())
    os.dup2(devnull, sys.stdout.fileno())
    os.dup2(devnull, sys.stderr.fileno())
    os.close(devnull)


def spawn_background_windows():
    """Spawn a detached background process on Windows using pythonw."""
    # Find pythonw.exe next to the current python.exe
    python_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(python_dir, "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable  # fallback

    script = os.path.abspath(__file__)
    # Launch with --foreground but via pythonw (no console window)
    # Use CREATE_NO_WINDOW flag for extra safety
    CREATE_NO_WINDOW = 0x08000000
    DETACHED_PROCESS = 0x00000008
    proc = subprocess.Popen(
        [pythonw, script, "--foreground"],
        creationflags=CREATE_NO_WINDOW | DETACHED_PROCESS,
        close_fds=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc.pid


def cmd_start_daemon():
    """Start the collector as a background process."""
    running, pid = is_daemon_running()
    if running:
        print(f"Collector is already running (PID {pid})")
        sys.exit(1)

    print("Starting Eonix Scheduler Collector...")
    print(f"  DB:  {DB_PATH}")
    print(f"  PID: {PID_FILE}")
    print(f"  Log: {LOG_FILE}")

    if IS_WINDOWS:
        child_pid = spawn_background_windows()
        # Give it a moment to write its PID file
        time.sleep(1)
        ok, real_pid = is_daemon_running()
        if ok:
            print(f"Collector started (PID {real_pid})")
        else:
            print(f"Spawned process PID {child_pid} — check {LOG_FILE} for details")
    else:
        daemonize_unix()
        collection_loop(foreground=False)


def cmd_foreground():
    """Run the collector in the foreground."""
    running, pid = is_daemon_running()
    if running:
        print(f"Collector daemon is already running (PID {pid})")
        print("Stop it first with: python3 collect_data.py --stop")
        sys.exit(1)

    print("Running Eonix Scheduler Collector in foreground (Ctrl+C to stop)")
    collection_loop(foreground=True)


def cmd_stop():
    """Stop the running daemon (cross-platform)."""
    running, pid = is_daemon_running()
    if not running:
        print("Collector is not running.")
        remove_pid_file()
        return

    print(f"Stopping collector (PID {pid})...")
    try:
        proc = psutil.Process(pid)
        proc.terminate()  # SIGTERM on Unix, TerminateProcess on Windows
        proc.wait(timeout=5)
        print("Collector stopped.")
    except psutil.NoSuchProcess:
        print("Process already exited.")
    except psutil.TimeoutExpired:
        proc.kill()
        print("Collector force-killed.")
    except Exception as e:
        print(f"Error stopping collector: {e}")
    remove_pid_file()


def cmd_status():
    """Print the daemon status."""
    running, pid = is_daemon_running()
    if running:
        print(f"Eonix Scheduler Collector is RUNNING (PID {pid})")
        # Show DB stats
        if os.path.exists(DB_PATH):
            try:
                conn = sqlite3.connect(DB_PATH)
                row = conn.execute("SELECT COUNT(*) FROM events").fetchone()
                total = row[0] if row else 0
                launches = conn.execute(
                    "SELECT COUNT(*) FROM events WHERE event_type='LAUNCH'"
                ).fetchone()[0]
                exits = conn.execute(
                    "SELECT COUNT(*) FROM events WHERE event_type='EXIT'"
                ).fetchone()[0]
                oldest = conn.execute(
                    "SELECT MIN(timestamp) FROM events"
                ).fetchone()[0]
                conn.close()

                print(f"  Total events: {total}")
                print(f"  Launches: {launches}  Exits: {exits}")
                if oldest:
                    dt = datetime.fromtimestamp(oldest, tz=timezone.utc)
                    print(f"  Oldest event: {dt.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                db_size_mb = os.path.getsize(DB_PATH) / 1048576
                print(f"  DB size: {db_size_mb:.2f} MB")
            except Exception:
                pass
    else:
        print("Eonix Scheduler Collector is NOT running.")


# ---- Windows Task Scheduler (auto-start on login) ----

def _get_python_exe() -> str:
    """Return path to pythonw.exe (Windows) or python3 (Unix)."""
    if IS_WINDOWS:
        python_dir = os.path.dirname(sys.executable)
        pythonw = os.path.join(python_dir, "pythonw.exe")
        if os.path.exists(pythonw):
            return pythonw
    return sys.executable


def _get_startup_folder() -> str:
    """Return the user's Windows Startup folder path."""
    import winreg
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
        )
        path, _ = winreg.QueryValueEx(key, "Startup")
        winreg.CloseKey(key)
        return path
    except Exception:
        return os.path.join(
            os.environ.get("APPDATA", ""),
            r"Microsoft\Windows\Start Menu\Programs\Startup",
        )


def _startup_vbs_path() -> str:
    """Path to the VBS launcher in the Startup folder."""
    if IS_WINDOWS:
        return os.path.join(_get_startup_folder(), "eonix-collector.vbs")
    return ""


def cmd_install():
    """Place a hidden-launch script in the Windows Startup folder."""
    if not IS_WINDOWS:
        print("Use the systemd service file for Linux:")
        print("  sudo cp eonix-collector.service /etc/systemd/system/")
        print("  sudo systemctl enable --now eonix-collector")
        return

    exe = _get_python_exe()
    script = os.path.abspath(__file__)
    vbs_path = _startup_vbs_path()

    # VBScript runs pythonw silently — no console flash at login
    vbs_content = (
        f'Set WshShell = CreateObject("WScript.Shell")\n'
        f'WshShell.Run """{exe}"" ""{script}"" --foreground", 0, False\n'
    )
    with open(vbs_path, "w") as f:
        f.write(vbs_content)

    print("Eonix Scheduler Collector registered for auto-start at login.")
    print(f"  Startup script: {vbs_path}")
    print(f"  Executable:     {exe}")
    print(f"  Collector:      {script}")
    print("\nIt will start silently every time you log into Windows.")
    print("To start it right now:  python collect_data.py --daemon")


def cmd_uninstall():
    """Remove the auto-start script from the Startup folder."""
    if not IS_WINDOWS:
        print("Use systemd to disable:")
        print("  sudo systemctl disable --now eonix-collector")
        return

    vbs_path = _startup_vbs_path()
    if os.path.exists(vbs_path):
        os.remove(vbs_path)
        print(f"Removed: {vbs_path}")
        print("Collector will no longer auto-start at login.")
    else:
        print("Auto-start script not found (already removed or never installed).")


# ---- Entry Point ----

def main():
    parser = argparse.ArgumentParser(
        description="Eonix OS Scheduler Data Collector Daemon",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python collect_data.py --daemon       Start as background process
  python collect_data.py --foreground   Run in foreground (dev mode)
  python collect_data.py --stop         Stop the running collector
  python collect_data.py --status       Check status & DB stats
  python collect_data.py --install      Auto-start on every login
  python collect_data.py --uninstall    Remove auto-start
        """,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--daemon", action="store_true",
                       help="Start as a background process")
    group.add_argument("--foreground", action="store_true",
                       help="Run in foreground (for development)")
    group.add_argument("--stop", action="store_true",
                       help="Stop the running collector")
    group.add_argument("--status", action="store_true",
                       help="Show status and DB statistics")
    group.add_argument("--install", action="store_true",
                       help="Register auto-start at login (Task Scheduler)")
    group.add_argument("--uninstall", action="store_true",
                       help="Remove auto-start task")

    args = parser.parse_args()

    if args.daemon:
        cmd_start_daemon()
    elif args.foreground:
        cmd_foreground()
    elif args.stop:
        cmd_stop()
    elif args.status:
        cmd_status()
    elif args.install:
        cmd_install()
    elif args.uninstall:
        cmd_uninstall()


if __name__ == "__main__":
    main()
