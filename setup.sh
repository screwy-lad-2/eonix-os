#!/usr/bin/env bash
# =============================================================================
# Eonix OS — One-Shot Development Environment Setup
# =============================================================================
# Run on Ubuntu 24.04 LTS (dual boot alongside Windows recommended)
# Usage: chmod +x setup.sh && ./setup.sh
# =============================================================================

set -euo pipefail

echo "============================================="
echo "  Eonix OS — Development Environment Setup"
echo "============================================="
echo ""

# ---- System packages ----
echo "[1/5] Installing system packages..."
sudo apt update && sudo apt install -y \
  build-essential git curl wget \
  qemu-system-x86_64 libvirt-daemon-system \
  linux-headers-$(uname -r) \
  bpfcc-tools libbpf-dev clang llvm \
  python3 python3-pip python3-venv \
  gdb valgrind strace

# ---- Rust toolchain ----
echo ""
echo "[2/5] Installing Rust (nightly)..."
if ! command -v rustup &> /dev/null; then
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
    source "$HOME/.cargo/env"
fi
rustup install nightly
rustup default nightly
rustup component add rust-src

# ---- Python virtual environment ----
echo ""
echo "[3/5] Setting up Python virtual environment..."
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install \
  psutil \
  scikit-learn \
  lightgbm \
  onnxruntime \
  chromadb \
  sentence-transformers \
  llama-cpp-python \
  faster-whisper \
  openwakeword \
  watchdog \
  fastapi \
  uvicorn \
  websockets

# ---- Verify installations ----
echo ""
echo "[4/5] Verifying installations..."
echo "  GCC:    $(gcc --version | head -1)"
echo "  Rust:   $(rustc --version)"
echo "  Python: $(python3 --version)"
echo "  QEMU:   $(qemu-system-x86_64 --version | head -1)"
echo "  Clang:  $(clang --version | head -1)"

# ---- Directory structure verification ----
echo ""
echo "[5/5] Verifying project structure..."
DIRS=(
  "eonix-silicon"
  "eonix-core/deadlock" "eonix-core/scheduler" "eonix-core/security"
  "eonix-core/memory" "eonix-core/ipc"
  "eonix-cortex/context-agent" "eonix-cortex/goal-engine"
  "eonix-cortex/cross-device" "eonix-cortex/resource-agent"
  "eonix-mind/stt" "eonix-mind/llm" "eonix-mind/tts"
  "eonix-mind/vision" "eonix-mind/proactive"
  "eonix-shell/compositor" "eonix-shell/ui"
  "legacy-bridge"
  "datasets/scheduler" "datasets/security"
  "models/onnx" "models/gguf" "models/whisper"
  "tests" "docs" ".github/workflows"
)

ALL_OK=true
for d in "${DIRS[@]}"; do
  if [ ! -d "$d" ]; then
    echo "  MISSING: $d"
    mkdir -p "$d"
    ALL_OK=false
  fi
done

if $ALL_OK; then
  echo "  All directories present ✓"
fi

echo ""
echo "============================================="
echo "  Setup complete! You're ready to build."
echo "============================================="
echo ""
echo "Next steps:"
echo "  1. Activate the Python venv:  source .venv/bin/activate"
echo "  2. Start with the deadlock module:  cd eonix-core/deadlock"
echo "  3. Build & test in QEMU:  make && make test QEMU=1"
echo ""
