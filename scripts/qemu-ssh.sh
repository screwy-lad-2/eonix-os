#!/bin/bash
# =============================================================
# Eonix OS — QEMU SSH Helper
# =============================================================
# Quick SSH into the running QEMU test VM.
# Usage:
#   ./scripts/qemu-ssh.sh                  # Interactive shell
#   ./scripts/qemu-ssh.sh "dmesg | tail"   # Run a command
# =============================================================

set -euo pipefail

SSH_PORT=2222
SSH_USER="eonix"
SSH_HOST="localhost"

ssh -p "$SSH_PORT" \
    -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null \
    -o LogLevel=ERROR \
    "${SSH_USER}@${SSH_HOST}" "$@"
