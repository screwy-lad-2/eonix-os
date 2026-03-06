# Eonix OS — Setup Guide

## Prerequisites

- **Ubuntu 24.04 LTS** (dual boot alongside Windows recommended)
- **8 GB RAM** minimum (16 GB recommended for ML models)
- **50 GB** free disk space
- GitHub Student Developer Pack (free tools worth $1,500+/year)

## One-Shot Setup

```bash
git clone https://github.com/shahnoor-exe/eonix-os.git
cd eonix-os
chmod +x setup.sh
./setup.sh
```

This installs: GCC, QEMU, Rust nightly, eBPF tools, Python venv with all ML dependencies.

## Free Student Tools to Activate

| Tool | URL | Use in Eonix |
|------|-----|-------------|
| GitHub Pro + Copilot | education.github.com/pack | Code repo, AI coding |
| JetBrains All Products | jetbrains.com/community/education | CLion, RustRover, PyCharm |
| DigitalOcean $200 | Via GitHub Student Pack | Cloud testing |
| Azure $100 GPU | Via GitHub Student Pack | ML model training |
| Oracle Free Tier | cloud.oracle.com/free | Permanent sync server |

## Manual Setup (if not using setup.sh)

### System Packages
```bash
sudo apt update && sudo apt install -y \
  build-essential git curl wget \
  qemu-system-x86_64 libvirt-daemon-system \
  linux-headers-$(uname -r) \
  bpfcc-tools libbpf-dev clang llvm \
  python3 python3-pip python3-venv \
  gdb valgrind strace
```

### Rust
```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
rustup install nightly
rustup default nightly
rustup component add rust-src
```

### Python Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install psutil scikit-learn lightgbm onnxruntime chromadb \
  sentence-transformers llama-cpp-python faster-whisper \
  openwakeword watchdog fastapi uvicorn websockets
```

### EONIX MIND Models (download when ready for Phase 2)
```bash
pip install huggingface-hub
python3 -c "
from huggingface_hub import hf_hub_download
hf_hub_download('lmstudio-community/Llama-3.2-3B-Instruct-GGUF',
                'Llama-3.2-3B-Instruct-Q4_K_M.gguf',
                local_dir='models/gguf/')
"
```

## Testing in QEMU

```bash
# Boot a test Linux kernel in QEMU
qemu-system-x86_64 -kernel bzImage -initrd initramfs.img \
  -append "console=ttyS0" -nographic -m 512M
```

## Development Workflow

1. Write code with GitHub Copilot Agent Mode in VS Code
2. Build and test locally
3. Push to GitHub — CI runs automatically via GitHub Actions
4. Review test results in the Actions tab
