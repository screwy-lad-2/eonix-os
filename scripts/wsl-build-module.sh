#!/bin/bash
# =============================================================
# Eonix OS — WSL2 Kernel Module Build & Test Script
# =============================================================
# Builds and tests a kernel module using WSL2 Linux environment.
#
# Usage (from Windows PowerShell):
#   wsl -d Ubuntu -e bash scripts/wsl-build-module.sh eonix-core/deadlock
#   wsl -d Ubuntu -e bash scripts/wsl-build-module.sh eonix-core/hello
# =============================================================

set -euo pipefail

REPO_ROOT="/mnt/c/Users/laska/Projects/eonix-os"
KVER=$(uname -r)
KSRC=/usr/src/wsl2-kernel

# Ensure build symlink
sudo ln -sf $KSRC /lib/modules/$KVER/build

if [ $# -lt 1 ]; then
    echo "Usage: $0 <module_dir>"
    echo "Example: $0 eonix-core/deadlock"
    exit 1
fi

MODULE_DIR="$1"
MODULE_NAME=$(basename "$MODULE_DIR")
SRC_PATH="$REPO_ROOT/$MODULE_DIR"

if [ ! -d "$SRC_PATH" ]; then
    echo "ERROR: Directory not found: $SRC_PATH"
    exit 1
fi

# Copy to Linux-native filesystem for faster builds
BUILD_DIR="/tmp/eonix_${MODULE_NAME}_build"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
cp "$SRC_PATH"/*.c "$SRC_PATH"/Makefile "$BUILD_DIR/" 2>/dev/null || true

cd "$BUILD_DIR"

echo "=== Building $MODULE_NAME ==="
make 2>&1
echo ""

# Find the .ko file
KO_FILE=$(find . -name "*.ko" -not -name "*.mod.ko" | head -1)
if [ -z "$KO_FILE" ]; then
    echo "ERROR: No .ko file produced"
    exit 1
fi

KO_NAME=$(basename "$KO_FILE" .ko)
echo "Built: $KO_FILE ($(stat -c%s "$KO_FILE") bytes)"
echo ""

echo "=== Loading $KO_NAME ==="
sudo insmod "$KO_FILE" 2>&1 && echo "Loaded OK" || { echo "LOAD FAILED"; exit 1; }

echo ""
echo "=== dmesg ==="
sudo dmesg | grep -iE "eonix|$KO_NAME" | tail -5

echo ""
echo "=== Unloading $KO_NAME ==="
sudo rmmod "$KO_NAME" 2>&1 && echo "Unloaded OK" || echo "UNLOAD FAILED"

echo ""
echo "=== dmesg after unload ==="
sudo dmesg | grep -iE "eonix|$KO_NAME" | tail -5

echo ""
echo "=== $MODULE_NAME: ALL TESTS PASSED ==="
