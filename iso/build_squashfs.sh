#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BUILD_ROOT=${BUILD_ROOT:-"$HOME/eonix-iso-build"}
CHROOT=${CHROOT:-"$BUILD_ROOT/chroot"}
IMAGE=${IMAGE:-"$BUILD_ROOT/image"}
FAST=0
VERIFY_ONLY=0

usage() {
  cat <<'EOF'
Usage: build_squashfs.sh [--fast] [--verify]
  --fast     use gzip instead of xz (faster, larger)
  --verify   run verification only (no rebuild)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fast) FAST=1 ;;
    --verify) VERIFY_ONLY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 1 ;;
  esac
  shift
done

require() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required tool: $1" >&2
    exit 1
  fi
}

require sudo
require mksquashfs
require unsquashfs

if [[ $VERIFY_ONLY -eq 0 ]]; then
  echo "[squashfs] Cleaning chroot apt cache"
  sudo chroot "$CHROOT" apt-get clean || true
  sudo rm -f "$CHROOT/root/.bash_history" || true

  echo "[squashfs] Copying kernel and initrd"
  sudo mkdir -p "$IMAGE/live"
  sudo cp "$CHROOT"/boot/vmlinuz-* "$IMAGE/live/vmlinuz"
  sudo cp "$CHROOT"/boot/initrd.img-* "$IMAGE/live/initrd.img"

  echo "[squashfs] Building squashfs"
  COMP_OPTS=("-comp" "xz" "-b" "1M")
  if [[ $FAST -eq 1 ]]; then
    COMP_OPTS=("-comp" "gzip" "-b" "1M")
  fi
  BEFORE_SIZE=$(sudo du -sh "$CHROOT" 2>/dev/null | awk '{print $1}')

  # SAFE exclusions only — virtual filesystems and dev nodes
  sudo mksquashfs "$CHROOT" "$IMAGE/live/filesystem.squashfs" \
    -e proc \
    -e sys \
    -e dev/pts \
    -noappend \
    "${COMP_OPTS[@]}" -no-progress

  AFTER_SIZE=$(sudo du -sh "$IMAGE/live/filesystem.squashfs" 2>/dev/null | awk '{print $1}')
  echo "✅ Squashfs built: ${BEFORE_SIZE:-?} → ${AFTER_SIZE:-?}"
fi

echo "[squashfs] Verifying squashfs metadata"
unsquashfs -s "$IMAGE/live/filesystem.squashfs" || { echo "unsquashfs verification failed" >&2; exit 1; }

if [[ $VERIFY_ONLY -eq 1 ]]; then
  echo "[squashfs] Verification completed"
else
  echo "[squashfs] Build + verification completed"
fi
