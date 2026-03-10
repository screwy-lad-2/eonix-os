#!/usr/bin/env bash
# =================================================================
# Eonix OS — Full Security Pipeline Integration Test
# =================================================================
# Requires: Linux (WSL2 or bare metal), root for eBPF
# Run: sudo bash eonix-core/security/test_security_integration.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

PYTHON=${PYTHON:-python3}
PIPELINE="eonix-core/security/security_pipeline.py"
MONITOR="eonix-core/security/syscall_monitor"

echo "========================================"
echo " Eonix Security Pipeline — Integration "
echo "========================================"

# ------ Step 0: Pre-flight checks ------
echo "[0] Pre-flight checks..."
$PYTHON -c "import sklearn, pandas, numpy, joblib; print('Dependencies OK')"

# Train model if not already trained
if [ ! -f models/security/isolation_forest.pkl ]; then
    echo "[0] Training anomaly detection model..."
    cd eonix-core/security
    $PYTHON anomaly_detector.py --train
    cd "$PROJECT_ROOT"
fi

# ------ Step 1: Start pipeline ------
echo ""
echo "[1] Starting security pipeline..."

if [ -x "$MONITOR" ]; then
    echo "    eBPF monitor available — full pipeline mode"
    sudo "$MONITOR" --monitor > /tmp/bpf_events.txt 2>&1 &
    BPF_PID=$!
else
    echo "    eBPF monitor not built — using log-tail mode"
    BPF_PID=""
fi

$PYTHON "$PIPELINE" --start &
PIPELINE_PID=$!
sleep 3

# ------ Step 2: Benign commands ------
echo ""
echo "[2] Running benign commands..."
ls /tmp > /dev/null 2>&1 || true
cat /etc/hostname 2>/dev/null || true
echo "benign test" > /dev/null

sleep 2
echo "=== Benign commands — threats check ==="
$PYTHON "$PIPELINE" --threats

# ------ Step 3: Simulated attack ------
echo ""
echo "[3] Running simulated attack..."

# Create a fake malware script
cat > /tmp/fake_malware.sh << 'MALWARE'
#!/bin/bash
# Simulated malicious behavior (harmless)
for i in $(seq 1 50); do
    ls /etc/shadow 2>/dev/null || true
done
# Rapid connect attempts (curl to localhost, harmless)
for i in $(seq 1 10); do
    timeout 1 bash -c "echo >/dev/tcp/127.0.0.1/1 2>/dev/null" || true
done
echo "[fake_malware] done"
MALWARE
chmod +x /tmp/fake_malware.sh
bash /tmp/fake_malware.sh || true
sleep 3

echo "=== After attack — threats check ==="
$PYTHON "$PIPELINE" --threats

# ------ Step 4: Status ------
echo ""
echo "[4] Security status:"
$PYTHON "$PIPELINE" --status

# ------ Step 5: Recent events ------
echo ""
echo "[5] Recent events:"
$PYTHON "$PIPELINE" --events

# ------ Step 6: Save proof ------
echo ""
echo "[6] Saving integration proof..."
RESULTS_DIR="$PROJECT_ROOT/results"
mkdir -p "$RESULTS_DIR"
{
    echo "=== Eonix Security Pipeline Integration Proof ==="
    echo "Date: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    echo "Kernel: $(uname -r)"
    echo "Host: $(hostname)"
    echo ""
    echo "--- Status ---"
    $PYTHON "$PIPELINE" --status 2>&1 || true
    echo ""
    echo "--- Events ---"
    $PYTHON "$PIPELINE" --events 2>&1 || true
    echo ""
    echo "--- Threats ---"
    $PYTHON "$PIPELINE" --threats 2>&1 || true
    echo ""
    echo "=== END ==="
} > "$RESULTS_DIR/security_integration_proof.txt"
echo "Proof saved to results/security_integration_proof.txt"

# ------ Step 7: Cleanup ------
echo ""
echo "[7] Stopping pipeline..."
if [ -n "${BPF_PID:-}" ]; then
    kill "$BPF_PID" 2>/dev/null || true
fi
kill "$PIPELINE_PID" 2>/dev/null || true
$PYTHON "$PIPELINE" --stop 2>/dev/null || true

echo ""
echo "============================================"
echo " Full security pipeline integration test   "
echo "              COMPLETE                      "
echo "============================================"
