#!/usr/bin/env bash
set -euo pipefail

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN=python
else
  echo "Python is required but not found (python3/python)." >&2
  exit 1
fi

VENV_PATH="${VENV_PATH:-.venv-iso}"
SKIP_CUMULATIVE_TESTS="${SKIP_CUMULATIVE_TESTS:-0}"

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "This script is intended for Linux/Codespaces." >&2
  exit 1
fi

echo "[Week27] Installing ISO build dependencies"
sudo apt-get update
sudo apt-get install -y \
  debootstrap squashfs-tools \
  xorriso grub-pc-bin grub-efi-amd64-bin \
  mtools dosfstools isolinux live-build rsync

echo "[Week27] Verifying required tools"
which debootstrap xorriso mksquashfs

echo "[Week27] Preparing workspace"
mkdir -p "$HOME/eonix-iso-build/chroot" "$HOME/eonix-iso-build/staging"
mkdir -p "$HOME/eonix-iso-build/image/boot" "$HOME/eonix-iso-build/image/EFI" "$HOME/eonix-iso-build/image/live"

echo "[Week27] Syntax checks"
bash -n iso/build_base.sh
bash -n iso/chroot_setup.sh
bash -n iso/grub_config.sh

echo "[Week27] Installing Python test dependency"
if [[ ! -d "$VENV_PATH" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_PATH"
fi
# shellcheck disable=SC1090
source "$VENV_PATH/bin/activate"
python -m pip install --upgrade pip pytest
python -m pip install numpy scikit-learn lightgbm onnxruntime sentence-transformers chromadb faster-whisper psutil prompt_toolkit pytest-asyncio || true

echo "[Week27] Unit tests"
python -m pytest iso/test_iso_build.py -v

echo "[Week27] Stage GRUB config"
bash iso/grub_config.sh

if [[ "${RUN_FULL_BUILD:-0}" == "1" ]]; then
  echo "[Week27] Running full base build"
  if [[ -x "$HOME/eonix-iso-build/chroot/bin/bash" ]]; then
    sudo bash iso/build_base.sh --skip-bootstrap --skip-packages
  else
    sudo bash iso/build_base.sh
  fi
else
  echo "[Week27] Skipping full bootstrap build. Set RUN_FULL_BUILD=1 to execute." 
fi

if [[ "$SKIP_CUMULATIVE_TESTS" == "1" ]]; then
  echo "[Week27] Skipping cumulative tests (SKIP_CUMULATIVE_TESTS=1)"
else
  echo "[Week27] Running cumulative tests"
  python run_all_tests.py
fi

echo "[Week27] Completed."
