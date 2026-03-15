#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
BUILD_ROOT=${BUILD_ROOT:-"$HOME/eonix-iso-build"}
IMAGE=${IMAGE:-"$BUILD_ROOT/image"}
ISO_PATH=${ISO_PATH:-"$HOME/eonix-os-0.8.0.iso"}
VOLUME_ID=${VOLUME_ID:-"EONIX_OS_0_8_0"}
TEST_MODE=0
SIGN_MODE=0

usage() {
  cat <<'EOF'
Usage: build_iso.sh [--test] [--sign]
  --test   build without EFI stage (faster for test)
  --sign   generate detached GPG signature (requires gpg)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --test) TEST_MODE=1 ;;
    --sign) SIGN_MODE=1 ;;
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
require xorriso

# Ensure grub artifacts are staged
bash "$SCRIPT_DIR/grub_config.sh"

# Preconditions
for f in "$IMAGE/live/vmlinuz" "$IMAGE/live/initrd.img" "$IMAGE/live/filesystem.squashfs" "$IMAGE/boot/grub/grub.cfg"; do
  if [[ ! -f "$f" ]]; then
    echo "Missing required artifact: $f" >&2
    exit 1
  fi
done

OUTPUT_DIR=$(dirname "$ISO_PATH")
mkdir -p "$OUTPUT_DIR"

XORRISO_CMD=(sudo xorriso -as mkisofs \
  -iso-level 3 \
  -full-iso9660-filenames \
  -volid "$VOLUME_ID" \
  -eltorito-boot boot/grub/bios.img \
  -no-emul-boot \
  -boot-load-size 4 \
  -boot-info-table \
  --eltorito-catalog boot/grub/boot.cat \
  --grub2-boot-info \
  --grub2-mbr /usr/lib/grub/i386-pc/boot_hybrid.img)

if [[ $TEST_MODE -eq 0 ]]; then
  XORRISO_CMD+=( -eltorito-alt-boot -e EFI/efiboot.img -no-emul-boot -append_partition 2 0xef EFI/efiboot.img )
fi

XORRISO_CMD+=( -output "$ISO_PATH" "$IMAGE" )

echo "[iso] Building ISO -> $ISO_PATH"
"${XORRISO_CMD[@]}"

echo "[iso] Verifying ISO"
ls -lh "$ISO_PATH"
file "$ISO_PATH"
sha256sum "$ISO_PATH" > "$ISO_PATH.sha256"
cat "$ISO_PATH.sha256"
echo "✅ ISO ready: $ISO_PATH"

if [[ $SIGN_MODE -eq 1 ]]; then
  if command -v gpg >/dev/null 2>&1; then
    gpg --output "$ISO_PATH.sig" --detach-sign "$ISO_PATH"
    echo "GPG signature written to $ISO_PATH.sig"
  else
    echo "gpg not found; skipping signature" >&2
  fi
fi
