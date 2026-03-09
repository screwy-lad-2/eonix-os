#!/bin/bash
# benchmark.sh — Measure deadlock detection latency for Eonix RAG Monitor
#
# Prerequisites: eonix_deadlock.ko loaded, run as root
# Usage: sudo bash benchmark.sh [iterations]
#
# Injects a 2-way deadlock via rag_inject, measures time until
# DEADLOCK_DETECTED appears in deadlock_log.

set -euo pipefail

INJECT="/proc/eonix/rag_inject"
LOG="/proc/eonix/deadlock_log"
ITERATIONS="${1:-10}"

if [ ! -f "$INJECT" ]; then
    echo "ERROR: $INJECT not found. Is eonix_deadlock.ko loaded?"
    exit 1
fi

echo "=== Eonix RAG Detection Latency Benchmark ==="
echo "Iterations: $ITERATIONS"
echo ""

total_ms=0
min_ms=999999
max_ms=0
results=()

for i in $(seq 1 "$ITERATIONS"); do
    # Reset state
    echo "RESET" > "$INJECT"
    sleep 0.2

    # Read current deadlock count from status line
    prev_count=$(grep -oP 'deadlocks=\K[0-9]+' "$LOG" 2>/dev/null | tail -1)
    prev_count=${prev_count:-0}

    # Record start time in milliseconds
    start_ns=$(date +%s%N)

    # Inject deadlock
    echo "HOLD 5001 50" > "$INJECT"
    echo "HOLD 5002 51" > "$INJECT"
    echo "PRIORITY 5001 10" > "$INJECT"
    echo "PRIORITY 5002 90" > "$INJECT"
    echo "WAIT 5001 51" > "$INJECT"
    echo "WAIT 5002 50" > "$INJECT"

    # Poll until deadlock count increases (max 5 seconds)
    detected=0
    for _ in $(seq 1 50); do
        cur_count=$(grep -oP 'deadlocks=\K[0-9]+' "$LOG" 2>/dev/null | tail -1)
        cur_count=${cur_count:-0}
        if [ "$cur_count" -gt "$prev_count" ]; then
            detected=1
            break
        fi
        sleep 0.1
    done

    end_ns=$(date +%s%N)
    elapsed_ms=$(( (end_ns - start_ns) / 1000000 ))

    if [ "$detected" -eq 1 ]; then
        results+=("$elapsed_ms")
        total_ms=$((total_ms + elapsed_ms))
        [ "$elapsed_ms" -lt "$min_ms" ] && min_ms=$elapsed_ms
        [ "$elapsed_ms" -gt "$max_ms" ] && max_ms=$elapsed_ms
        printf "  Run %2d: %4dms  ✓ detected\n" "$i" "$elapsed_ms"
    else
        printf "  Run %2d: TIMEOUT ✗ not detected!\n" "$i"
    fi
done

echo ""
count=${#results[@]}
if [ "$count" -gt 0 ]; then
    avg_ms=$((total_ms / count))
    echo "--- Results ---"
    echo "  Detected: $count / $ITERATIONS"
    echo "  Min:      ${min_ms}ms"
    echo "  Max:      ${max_ms}ms"
    echo "  Average:  ${avg_ms}ms"
    echo "  Target:   < 600ms (500ms interval + overhead)"
    echo ""
    if [ "$avg_ms" -lt 600 ]; then
        echo "BENCHMARK: PASS (avg ${avg_ms}ms < 600ms)"
    else
        echo "BENCHMARK: WARN (avg ${avg_ms}ms >= 600ms)"
    fi
else
    echo "BENCHMARK: FAIL (no deadlocks detected)"
    exit 1
fi

# Final reset
echo "RESET" > "$INJECT"
