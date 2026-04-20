#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
BUILD_ROOT=${BUILD_ROOT:-"$HOME/eonix-iso-build"}
CHROOT="$BUILD_ROOT/chroot"
IMAGE="$BUILD_ROOT/image"
STAGING="$BUILD_ROOT/staging"

SKIP_BOOTSTRAP=0
SKIP_PACKAGES=0
EONIX_ONLY=0

usage() {
  cat <<'EOF'
Usage: build_base.sh [--skip-bootstrap] [--skip-packages] [--eonix-only]
  --skip-bootstrap   Use existing chroot instead of running debootstrap
  --skip-packages    Skip package install/user setup inside chroot
  --eonix-only       Only install EONIX layer (requires prepared chroot)
EOF
}

log() { echo "[build_base] $*"; }
require() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log "Missing required tool: $1"
    exit 1
  fi
}
sync_tree() {
  local source_dir="$1"
  local dest_dir="$2"
  if command -v rsync >/dev/null 2>&1; then
    sudo rsync -a --delete \
      --exclude '.git/' \
      --exclude '.venv/' \
      --exclude '.venv-iso/' \
      --exclude '__pycache__/' \
      --exclude '.pytest_cache/' \
      "$source_dir/" "$dest_dir/"
  else
    log "rsync not found; using cp -a fallback"
    sudo rm -rf "$dest_dir"
    sudo mkdir -p "$dest_dir"
    sudo cp -a "$source_dir/." "$dest_dir/"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-bootstrap) SKIP_BOOTSTRAP=1 ;;
    --skip-packages) SKIP_PACKAGES=1 ;;
    --eonix-only) EONIX_ONLY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
  esac
  shift
done

if [[ "$(uname -s)" != "Linux" ]]; then
  log "Warning: non-Linux host detected; bootstrap steps require Linux."
fi

mkdir -p "$BUILD_ROOT" "$CHROOT" "$IMAGE/boot" "$IMAGE/EFI" "$IMAGE/live" "$STAGING"

# Step 1: Bootstrap minimal Debian
if [[ $SKIP_BOOTSTRAP -eq 0 && $EONIX_ONLY -eq 0 ]]; then
  log "Bootstrapping Debian base into $CHROOT"
  require sudo
  require debootstrap
  sudo debootstrap --arch=amd64 bookworm "$CHROOT" http://deb.debian.org/debian
else
  log "Skipping bootstrap; using existing chroot at $CHROOT"
fi

# Step 2: Configure chroot packages and system defaults
if [[ $SKIP_PACKAGES -eq 0 && $EONIX_ONLY -eq 0 ]]; then
  log "Running chroot setup script"
  require sudo
  sudo cp "$SCRIPT_DIR/chroot_setup.sh" "$CHROOT/tmp/chroot_setup.sh"
  sudo chroot "$CHROOT" /bin/bash /tmp/chroot_setup.sh
  sudo rm -f "$CHROOT/tmp/chroot_setup.sh"
else
  log "Skipping chroot package installation"
fi

# Step 3: Install EONIX OS layer into chroot
log "Syncing EONIX OS into chroot"
require sudo
sudo mkdir -p "$CHROOT/home/eonix"
sync_tree "$REPO_ROOT" "$CHROOT/home/eonix/eonix-os"
sudo chroot "$CHROOT" chown -R eonix:eonix /home/eonix/eonix-os
log "Invoking installer in dev mode"
sudo chroot "$CHROOT" /bin/bash -lc "su - eonix -c 'bash /home/eonix/eonix-os/install/eonix-install.sh --dev'"

# Step 4: Autostart handled by chroot_setup.sh (.bashrc + .xinitrc)
# Do NOT create a .bash_profile here — it conflicts with the .bashrc autostart
log "Autostart already configured by chroot_setup.sh"

# Step 5: Report status
chroot_size=$(sudo du -sh "$CHROOT" 2>/dev/null | awk '{print $1}')
log "✅ Base system ready"
log "Size: ${chroot_size:-unknown}"
