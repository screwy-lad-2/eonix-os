#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
CHROOT=${CHROOT:-"$HOME/eonix-iso-build/chroot"}

require() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required tool: $1" >&2
    exit 1
  fi
}

require sudo

if [[ ! -d "$CHROOT" ]]; then
  echo "Chroot directory not found: $CHROOT" >&2
  exit 1
fi

echo "[install] Copying EONIX stack into chroot -> $CHROOT/home/eonix"
sudo mkdir -p "$CHROOT/home/eonix"

copy_items=(
  eonix-core
  eonix-cortex
  eonix-mind
  eonix-desktop
  eonix-shell
  eonix-hub
  tests
  results
  start_eonix.sh
  run_all_tests.py
)

for item in "${copy_items[@]}"; do
  src="$REPO_ROOT/$item"
  dest="$CHROOT/home/eonix/$item"
  if [[ -e "$src" ]]; then
    sudo rm -rf "$dest"
    sudo mkdir -p "$(dirname "$dest")"
    sudo cp -a "$src" "$dest"
  else
    echo "[install] WARNING: missing source $src" >&2
  fi
done

sudo chown -R 1000:1000 "$CHROOT/home/eonix"

echo "[install] Installing Python dependencies inside chroot"
sudo chroot "$CHROOT" /bin/bash -lc "pip3 install --no-cache-dir \
  httpx fastapi uvicorn aiohttp \
  websockets requests psutil \
  numpy scikit-learn lightgbm \
  onnxruntime sentence-transformers \
  chromadb prompt_toolkit \
  pycairo PyGObject python-xlib ewmh"

if [[ ! -f "$CHROOT/home/eonix/eonix-mind/mind_v2.py" ]]; then
  echo "mind_v2.py missing after install" >&2
  exit 1
fi
if [[ ! -f "$CHROOT/home/eonix/start_eonix.sh" ]]; then
  echo "start_eonix.sh missing after install" >&2
  exit 1
fi

echo "✅ EONIX stack installed into chroot"
