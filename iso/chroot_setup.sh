#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y --no-install-recommends \
  linux-image-amd64 live-boot systemd systemd-sysv sudo curl wget git \
  python3 python3-pip python3-venv python3-gi python3-gi-cairo \
  gir1.2-gtk-4.0 libgtk-4-dev \
  portaudio19-dev ffmpeg espeak-ng \
  xorg xinit openbox \
  fonts-noto-color-emoji \
  network-manager xvfb \
  virtualbox-guest-x11 virtualbox-guest-utils virtualbox-guest-dkms

# Hostname
if [[ ! -f /etc/hostname ]] || ! grep -q '^eonix-os$' /etc/hostname; then
  echo 'eonix-os' > /etc/hostname
fi
if ! grep -q '127.0.1.1 eonix-os' /etc/hosts 2>/dev/null; then
  echo '127.0.1.1 eonix-os' >> /etc/hosts
fi

# User setup
if ! id -u eonix >/dev/null 2>&1; then
  useradd -m -s /bin/bash eonix
fi
echo 'eonix:eonix' | chpasswd
usermod -aG sudo eonix
if ! grep -q '%sudo ALL=(ALL) NOPASSWD:ALL' /etc/sudoers; then
  echo '%sudo ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers
fi

# Auto-login on TTY1
mkdir -p /etc/systemd/system/getty@tty1.service.d/
cat > /etc/systemd/system/getty@tty1.service.d/override.conf <<'EOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin eonix --noclear %I linux
EOF

# Runtime Python dependencies baked into the ISO
python3 -m pip install --no-cache-dir --upgrade pip
python3 -m pip install --no-cache-dir \
  numpy scikit-learn lightgbm onnxruntime \
  sentence-transformers chromadb psutil prompt_toolkit pytest-asyncio pyarrow \
  pycairo PyGObject python-xlib ewmh \
  httpx fastapi uvicorn aiohttp websockets zeroconf requests

# Ensure MIND code exists inside the live filesystem
if [[ -d /home/eonix/eonix-os/eonix-mind ]]; then
  cp -a /home/eonix/eonix-os/eonix-mind /home/eonix/eonix-mind
  chown -R eonix:eonix /home/eonix/eonix-mind
else
  echo "[chroot_setup] WARNING: /home/eonix/eonix-os/eonix-mind missing; skipping copy" >&2
fi

apt-get clean
