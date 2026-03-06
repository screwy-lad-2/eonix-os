"""
Eonix OS — eBPF Syscall Security Monitor
==========================================
Attaches kprobes to critical syscalls, builds per-process behavioral
fingerprints, and uses an Isolation Forest model for anomaly detection.

Requires: root privileges, bcc tools installed
Usage: sudo python3 syscall_monitor.py
"""

import os
import sys
import time
import json
import signal
import collections
from datetime import datetime, timezone

# BCC import (requires bpfcc-tools and libbpf-dev)
try:
    from bcc import BPF
except ImportError:
    print("ERROR: bcc not installed. Run: sudo apt install bpfcc-tools python3-bpfcc")
    sys.exit(1)

# Anomaly detection
try:
    from sklearn.ensemble import IsolationForest
    import numpy as np
except ImportError:
    print("WARNING: scikit-learn not installed. Anomaly detection disabled.")
    IsolationForest = None

# ---- eBPF Program (C code loaded into kernel) ----

BPF_PROGRAM = r"""
#include <uapi/linux/ptrace.h>
#include <linux/sched.h>

struct syscall_event {
    u32 pid;
    u32 tgid;
    u32 syscall_id;
    u64 timestamp_ns;
    char comm[TASK_COMM_LEN];
};

BPF_PERF_OUTPUT(events);

TRACEPOINT_PROBE(raw_syscalls, sys_enter) {
    struct syscall_event evt = {};

    evt.pid = bpf_get_current_pid_tgid() >> 32;
    evt.tgid = bpf_get_current_pid_tgid() & 0xFFFFFFFF;
    evt.syscall_id = args->id;
    evt.timestamp_ns = bpf_ktime_get_ns();
    bpf_get_current_comm(&evt.comm, sizeof(evt.comm));

    events.perf_submit(args, &evt, sizeof(evt));
    return 0;
}
"""

# ---- Behavioral Fingerprint ----

WINDOW_SIZE = 1000  # Rolling window of syscalls per process
ANOMALY_THRESHOLD = 0.7

# Syscalls we track for the fingerprint histogram (Linux x86_64)
TRACKED_SYSCALLS = {
    0: "read", 1: "write", 2: "open", 3: "close",
    9: "mmap", 11: "munmap", 41: "socket", 42: "connect",
    56: "clone", 57: "fork", 59: "execve", 62: "kill",
    101: "ptrace", 257: "openat",
}

class ProcessFingerprint:
    """Rolling syscall histogram for a single process."""

    def __init__(self, pid: int, comm: str):
        self.pid = pid
        self.comm = comm
        self.syscalls = collections.deque(maxlen=WINDOW_SIZE)
        self.histogram = collections.Counter()

    def add_syscall(self, syscall_id: int):
        if len(self.syscalls) == WINDOW_SIZE:
            old = self.syscalls[0]
            self.histogram[old] -= 1
        self.syscalls.append(syscall_id)
        self.histogram[syscall_id] += 1

    def feature_vector(self) -> list:
        """Return normalized histogram as feature vector."""
        total = len(self.syscalls) or 1
        return [self.histogram.get(sid, 0) / total
                for sid in sorted(TRACKED_SYSCALLS.keys())]


class SecurityMonitor:
    """Main security monitor with anomaly detection."""

    def __init__(self):
        self.fingerprints: dict[int, ProcessFingerprint] = {}
        self.model = None
        self.training_data: list[list[float]] = []
        self.alert_log: list[dict] = []
        self.running = True

        if IsolationForest:
            self.model = IsolationForest(
                n_estimators=100,
                contamination=0.05,
                random_state=42,
            )

    def process_event(self, pid: int, syscall_id: int, comm: str):
        if pid not in self.fingerprints:
            self.fingerprints[pid] = ProcessFingerprint(pid, comm)
        self.fingerprints[pid].add_syscall(syscall_id)

    def train_baseline(self, min_samples: int = 500):
        """Train anomaly model on collected normal behavior."""
        if not self.model:
            return

        vectors = []
        for fp in self.fingerprints.values():
            if len(fp.syscalls) >= 100:
                vectors.append(fp.feature_vector())

        if len(vectors) >= min_samples:
            self.model.fit(vectors)
            print(f"[EONIX Security] Model trained on {len(vectors)} process fingerprints")

    def check_anomaly(self, pid: int) -> float:
        """Return anomaly score (0=normal, 1=anomalous) for a process."""
        if not self.model or pid not in self.fingerprints:
            return 0.0

        fp = self.fingerprints[pid]
        if len(fp.syscalls) < 50:
            return 0.0

        try:
            vec = np.array([fp.feature_vector()])
            # decision_function returns negative for anomalies
            score = -self.model.decision_function(vec)[0]
            # Normalize to 0-1 range (approximate)
            return max(0.0, min(1.0, (score + 0.5)))
        except Exception:
            return 0.0

    def handle_anomaly(self, pid: int, score: float, comm: str):
        """Take action based on anomaly score."""
        alert = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "pid": pid,
            "process": comm,
            "score": round(score, 3),
            "action": "none",
        }

        if score < 0.3:
            return  # Normal
        elif score < 0.6:
            alert["action"] = "alert"
            print(f"[EONIX Security] SUSPICIOUS: PID {pid} ({comm}) score={score:.3f}")
        elif score < 0.8:
            alert["action"] = "restrict_network"
            print(f"[EONIX Security] RESTRICTING: PID {pid} ({comm}) score={score:.3f}")
            # In production: os.system(f"iptables -A OUTPUT -m owner --uid-owner ...")
        else:
            alert["action"] = "sandbox"
            print(f"[EONIX Security] SANDBOXING: PID {pid} ({comm}) score={score:.3f}")
            # In production: launch in gVisor container

        self.alert_log.append(alert)


def main():
    monitor = SecurityMonitor()

    def signal_handler(sig, frame):
        monitor.running = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print("[EONIX Security] Loading eBPF program...")
    b = BPF(text=BPF_PROGRAM)

    event_count = 0
    TRAIN_INTERVAL = 10000  # Train model every N events

    def handle_event(cpu, data, size):
        nonlocal event_count
        event = b["events"].event(data)
        monitor.process_event(event.pid, event.syscall_id,
                              event.comm.decode("utf-8", errors="replace"))
        event_count += 1

        # Periodic model training
        if event_count % TRAIN_INTERVAL == 0:
            monitor.train_baseline()

        # Periodic anomaly check
        if event_count % 1000 == 0:
            score = monitor.check_anomaly(event.pid)
            if score > 0.3:
                monitor.handle_anomaly(
                    event.pid, score,
                    event.comm.decode("utf-8", errors="replace"))

    b["events"].open_perf_buffer(handle_event)

    print("[EONIX Security] Monitoring syscalls... (Ctrl+C to stop)")

    while monitor.running:
        try:
            b.perf_buffer_poll(timeout=100)
        except KeyboardInterrupt:
            break

    print(f"\n[EONIX Security] Stopped. Events processed: {event_count}")
    print(f"[EONIX Security] Alerts generated: {len(monitor.alert_log)}")

    # Save alerts
    if monitor.alert_log:
        alert_file = "/tmp/eonix_security_alerts.json"
        with open(alert_file, "w") as f:
            json.dump(monitor.alert_log, f, indent=2)
        print(f"[EONIX Security] Alerts saved to {alert_file}")


if __name__ == "__main__":
    if os.geteuid() != 0:
        print("ERROR: This script requires root privileges.")
        print("Usage: sudo python3 syscall_monitor.py")
        sys.exit(1)
    main()
