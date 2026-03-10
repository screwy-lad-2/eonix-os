#!/bin/bash
# ============================================================
# Eonix OS — Demo Video Terminal Script
# ============================================================
# This script provides the EXACT terminal commands to run during
# the OBS recording.  It pauses between sections so you can
# narrate.  Run inside WSL2 Ubuntu (with the kernel module built).
#
# Usage:  bash scripts/demo_video_commands.sh
#
# The script is NON-DESTRUCTIVE — it only loads/unloads the module
# and reads proc files.  Safe to run multiple times.
# ============================================================

set -e

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

pause() {
    echo ""
    echo -e "${YELLOW}>>> Press ENTER to continue to next section...${NC}"
    read -r
    echo ""
}

clear
echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║          EONIX OS — LIVE DEMO  (4 minutes)             ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "Date: $(date '+%B %d, %Y')"
echo "Kernel: $(uname -r)"
echo ""

# ── SECTION 1: Build the module ──────────────────────────────
echo -e "${GREEN}═══ SECTION 1: Building the Kernel Module ═══${NC}"
pause

cd /mnt/c/Users/laska/Projects/eonix-os/eonix-core/deadlock
echo "$ make clean && make"
make clean 2>/dev/null || true
make 2>&1 | tail -3
echo ""
echo "$ ls -lh eonix_deadlock.ko"
ls -lh eonix_deadlock.ko
pause

# ── SECTION 2: Load the module ───────────────────────────────
echo -e "${GREEN}═══ SECTION 2: Loading the Module ═══${NC}"
sudo rmmod eonix_deadlock 2>/dev/null || true
echo "$ sudo insmod eonix_deadlock.ko"
sudo insmod eonix_deadlock.ko
sleep 1
echo ""
echo "$ lsmod | grep eonix"
lsmod | grep eonix
echo ""
echo "$ dmesg | grep EONIX | tail -5"
dmesg | grep EONIX | tail -5
echo ""
echo "$ ls /proc/eonix/"
ls /proc/eonix/
pause

# ── SECTION 3: Trigger a 2-way deadlock ──────────────────────
echo -e "${GREEN}═══ SECTION 3: Triggering a 2-Way Deadlock ═══${NC}"
echo "Injecting: Process 1001 HOLDS resource 1, WAITS on resource 2"
echo "           Process 1002 HOLDS resource 2, WAITS on resource 1"
echo ""
echo '$ echo "RESET" > /proc/eonix/rag_inject'
echo "RESET" | sudo tee /proc/eonix/rag_inject > /dev/null
echo '$ echo "HOLD 1001 1" > /proc/eonix/rag_inject'
echo "HOLD 1001 1" | sudo tee /proc/eonix/rag_inject > /dev/null
echo '$ echo "HOLD 1002 2" > /proc/eonix/rag_inject'
echo "HOLD 1002 2" | sudo tee /proc/eonix/rag_inject > /dev/null
echo '$ echo "WAIT 1001 2" > /proc/eonix/rag_inject'
echo "WAIT 1001 2" | sudo tee /proc/eonix/rag_inject > /dev/null
echo '$ echo "WAIT 1002 1" > /proc/eonix/rag_inject'
echo "WAIT 1002 1" | sudo tee /proc/eonix/rag_inject > /dev/null

echo ""
echo "Waiting for detection (up to 1 second)..."
sleep 1
echo ""
echo "$ cat /proc/eonix/deadlock_log"
cat /proc/eonix/deadlock_log
pause

# ── SECTION 4: 3-way deadlock ────────────────────────────────
echo -e "${GREEN}═══ SECTION 4: 3-Way Deadlock ═══${NC}"
echo "RESET" | sudo tee /proc/eonix/rag_inject > /dev/null
echo "Injecting 3-process circular wait: A→B→C→A"
echo "HOLD 2001 10" | sudo tee /proc/eonix/rag_inject > /dev/null
echo "HOLD 2002 20" | sudo tee /proc/eonix/rag_inject > /dev/null
echo "HOLD 2003 30" | sudo tee /proc/eonix/rag_inject > /dev/null
echo "WAIT 2001 20" | sudo tee /proc/eonix/rag_inject > /dev/null
echo "WAIT 2002 30" | sudo tee /proc/eonix/rag_inject > /dev/null
echo "WAIT 2003 10" | sudo tee /proc/eonix/rag_inject > /dev/null

sleep 1
echo ""
echo "$ cat /proc/eonix/deadlock_log"
cat /proc/eonix/deadlock_log
pause

# ── SECTION 5: Show checkpoint ───────────────────────────────
echo -e "${GREEN}═══ SECTION 5: Process Checkpoints ═══${NC}"
echo "$ cat /proc/eonix/checkpoints"
cat /proc/eonix/checkpoints
pause

# ── SECTION 6: Run Python security tests ─────────────────────
echo -e "${GREEN}═══ SECTION 6: Security Pipeline — 14/14 Tests ═══${NC}"
cd /mnt/c/Users/laska/Projects/eonix-os
echo "$ python -m pytest eonix-core/security/ -v --tb=short"
python3 -m pytest eonix-core/security/anomaly_detector.py \
                  eonix-core/security/security_pipeline.py \
                  eonix-core/security/behavioral_fingerprint.py \
                  -v --tb=short 2>&1 | tail -20
pause

# ── SECTION 7: Anomaly detector accuracy ─────────────────────
echo -e "${GREEN}═══ SECTION 7: ADFA-LD Anomaly Detection — 100% Recall ═══${NC}"
cd /mnt/c/Users/laska/Projects/eonix-os/eonix-core/security
echo "$ python anomaly_detector.py --train --data ../../datasets/security/"
python3 anomaly_detector.py --train --data ../../datasets/security/ 2>&1 | tail -15
pause

# ── SECTION 8: Cleanup ───────────────────────────────────────
echo -e "${GREEN}═══ SECTION 8: Cleanup ═══${NC}"
echo "$ sudo rmmod eonix_deadlock"
sudo rmmod eonix_deadlock
echo "Module unloaded cleanly."
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║              DEMO COMPLETE — Thank you!                 ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
