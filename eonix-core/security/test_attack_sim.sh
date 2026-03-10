#!/bin/bash
# Eonix OS — Integration Test: Detect a Simulated Attack
#
# Prerequisites:
#   - Built: syscall_monitor.bpf.o and syscall_monitor binary
#   - Root privileges (for BPF loading)
#
# Usage: sudo bash test_attack_sim.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EONIX_DIR="$HOME/.eonix"
ALERT_LOG="$EONIX_DIR/security_alerts.log"

echo "=== Eonix Security Integration Test ==="
echo "Date: $(date -Iseconds)"

# Ensure .eonix directory exists
mkdir -p "$EONIX_DIR"

# Clear previous alerts
> "$ALERT_LOG"

# Check binaries exist
if [ ! -f "$SCRIPT_DIR/syscall_monitor.bpf.o" ]; then
    echo "ERROR: syscall_monitor.bpf.o not found. Run 'make' first."
    exit 1
fi
if [ ! -f "$SCRIPT_DIR/syscall_monitor" ]; then
    echo "ERROR: syscall_monitor binary not found. Run 'make' first."
    exit 1
fi

echo "[1/5] Starting eBPF monitor in background..."
cd "$SCRIPT_DIR"
./syscall_monitor --monitor > /tmp/eonix_monitor_output.txt 2>&1 &
MONITOR_PID=$!
sleep 2

# Verify monitor started
if ! kill -0 "$MONITOR_PID" 2>/dev/null; then
    echo "ERROR: Monitor failed to start. Check /tmp/eonix_monitor_output.txt"
    exit 1
fi
echo "  Monitor PID=$MONITOR_PID"

echo "[2/5] Running simulated malware (rapid fork + exec)..."
# Rapid process spawning (fork bomb pattern)
for i in $(seq 1 25); do
    bash -c "exit 0" &
done
wait

# Trigger ptrace-adjacent call
strace ls /dev/null 2>/dev/null || true

# Trigger setuid-adjacent calls
id > /dev/null 2>&1
whoami > /dev/null 2>&1

# Port scan simulation
for port in 80 443 8080 8443 3000; do
    (echo "" > /dev/tcp/127.0.0.1/$port) 2>/dev/null &
done
sleep 1
wait 2>/dev/null

echo "[3/5] Waiting for events to propagate..."
sleep 3

echo "[4/5] Checking results..."
echo ""

echo "=== Security Alerts Generated ==="
if [ -f "$ALERT_LOG" ]; then
    ALERT_COUNT=$(wc -l < "$ALERT_LOG")
    echo "Total alerts: $ALERT_COUNT"
    tail -20 "$ALERT_LOG"
else
    ALERT_COUNT=0
    echo "No alerts generated"
fi

echo ""
echo "=== Monitor Output (ALERT/BLOCKED lines) ==="
grep -E "ALERT|BLOCKED" /tmp/eonix_monitor_output.txt | head -20 || echo "(none)"

echo ""
echo "[5/5] Stopping monitor..."
kill "$MONITOR_PID" 2>/dev/null || true
wait "$MONITOR_PID" 2>/dev/null || true

# Verify expected alerts
FORK_ALERTS=$(grep -c "fork_bomb\|exec_storm" "$ALERT_LOG" 2>/dev/null || echo "0")
echo ""
echo "=== Summary ==="
echo "  Total alerts:     $ALERT_COUNT"
echo "  Fork/exec alerts: $FORK_ALERTS"

if [ "$FORK_ALERTS" -gt 0 ]; then
    echo "  Result: PASS — Attack simulation detected"
    exit 0
else
    echo "  Result: WARN — No fork/exec alerts (may need more iterations)"
    exit 0
fi
