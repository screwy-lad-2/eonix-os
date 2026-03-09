#!/bin/bash
# =============================================================
# Eonix OS — QEMU Test Environment Boot Script
# =============================================================
# Boots the QEMU VM used for kernel module testing.
#
# Prerequisites:
#   qemu-img create -f qcow2 ~/eonix-qemu-disk.qcow2 20G
#   Install Ubuntu 24.04 server into the disk image first.
#
# Usage:
#   ./scripts/qemu-boot.sh          # Start VM
#   ./scripts/qemu-ssh.sh           # Connect via SSH
#   kill $(cat /tmp/eonix-qemu.pid) # Stop VM
# =============================================================

set -euo pipefail

DISK="${HOME}/eonix-qemu-disk.qcow2"
SSH_PORT=2222
MEMORY="2G"
CPUS=2

if [ ! -f "$DISK" ]; then
    echo "ERROR: QEMU disk not found at $DISK"
    echo "Create it first:"
    echo "  qemu-img create -f qcow2 $DISK 20G"
    echo "  # Then install Ubuntu 24.04 server into it"
    exit 1
fi

echo "Starting Eonix QEMU test environment..."
echo "  Disk:   $DISK"
echo "  Memory: $MEMORY"
echo "  CPUs:   $CPUS"
echo "  SSH:    localhost:$SSH_PORT"

qemu-system-x86_64 \
    -enable-kvm \
    -m "$MEMORY" \
    -smp "$CPUS" \
    -drive file="$DISK",format=qcow2 \
    -net nic \
    -net user,hostfwd=tcp::${SSH_PORT}-:22 \
    -nographic \
    -serial mon:stdio &

QEMU_PID=$!
echo "$QEMU_PID" > /tmp/eonix-qemu.pid
echo "QEMU PID: $QEMU_PID"

echo "Waiting for VM to boot (30s)..."
sleep 30

echo "VM ready. Connect with:"
echo "  ssh -p ${SSH_PORT} eonix@localhost"
echo "  OR: ./scripts/qemu-ssh.sh"
echo ""
echo "To stop: kill \$(cat /tmp/eonix-qemu.pid)"
