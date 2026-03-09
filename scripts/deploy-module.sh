#!/bin/bash
# =============================================================
# Eonix OS — Kernel Module Deploy Script
# =============================================================
# Copies a kernel module directory to the QEMU VM and builds it.
#
# Usage:
#   ./scripts/deploy-module.sh eonix-core/deadlock
#
# After deploying:
#   ./scripts/qemu-ssh.sh "cd ~/deadlock && sudo insmod rag_monitor.ko"
#   ./scripts/qemu-ssh.sh "dmesg | tail -5"
# =============================================================

set -euo pipefail

SSH_PORT=2222
SSH_USER="eonix"
SSH_HOST="localhost"

if [ $# -lt 1 ]; then
    echo "Usage: $0 <module_dir>"
    echo "Example: $0 eonix-core/deadlock"
    exit 1
fi

MODULE_DIR="$1"
MODULE_NAME=$(basename "$MODULE_DIR")

if [ ! -d "$MODULE_DIR" ]; then
    echo "ERROR: Directory not found: $MODULE_DIR"
    exit 1
fi

echo "Deploying kernel module from $MODULE_DIR to QEMU VM..."
echo "  Target: ${SSH_USER}@${SSH_HOST}:~/${MODULE_NAME}/"

scp -P "$SSH_PORT" \
    -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null \
    -o LogLevel=ERROR \
    -r "$MODULE_DIR" "${SSH_USER}@${SSH_HOST}:/home/${SSH_USER}/"

echo "Building module inside VM..."
ssh -p "$SSH_PORT" \
    -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null \
    -o LogLevel=ERROR \
    "${SSH_USER}@${SSH_HOST}" \
    "cd /home/${SSH_USER}/${MODULE_NAME} && make"

echo ""
echo "Module built. To load:"
echo "  ./scripts/qemu-ssh.sh 'sudo insmod /home/${SSH_USER}/${MODULE_NAME}/*.ko'"
echo "  ./scripts/qemu-ssh.sh 'dmesg | tail -5'"
