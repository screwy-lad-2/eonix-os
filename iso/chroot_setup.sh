#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y --no-install-recommends \
  linux-image-amd64 live-boot systemd systemd-sysv sudo curl wget git \
  python3 python3-pip python3-venv python3-gi python3-gi-cairo \
  gir1.2-gtk-4.0 libgtk-4-dev \
  portaudio19-dev ffmpeg espeak-ng \
  xorg xinit openbox xterm \
  fonts-noto-color-emoji \
  network-manager xvfb dbus-x11

# VirtualBox guest packages are in contrib/non-free on some Debian mirrors.
# Install only those currently resolvable to keep CI builds reproducible.
vbox_guest_packages=(
  virtualbox-guest-x11
  virtualbox-guest-utils
  virtualbox-guest-dkms
)
available_vbox_guest_packages=()
for pkg in "${vbox_guest_packages[@]}"; do
  if apt-cache show "$pkg" >/dev/null 2>&1; then
    available_vbox_guest_packages+=("$pkg")
  else
    echo "[chroot_setup] INFO: Optional package '$pkg' not available; skipping"
  fi
done
if [[ ${#available_vbox_guest_packages[@]} -gt 0 ]]; then
  apt-get install -y --no-install-recommends "${available_vbox_guest_packages[@]}"
else
  echo "[chroot_setup] INFO: No VirtualBox guest packages available in apt sources"
fi

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

# Auto-start X on tty1 login
cat >> /home/eonix/.bashrc <<'BASHEOF'

# --- Eonix OS: Auto-start graphical desktop on tty1 ---
if [[ -z "$DISPLAY" ]] && [[ "$(tty)" == "/dev/tty1" ]]; then
  exec startx -- -nolisten tcp vt1 2>/home/eonix/.xsession-errors
fi
BASHEOF

# X session startup: window manager + agents + desktop
cat > /home/eonix/.xinitrc <<'XINITEOF'
#!/bin/bash

# Set DISPLAY explicitly
export DISPLAY=:0

# Start D-Bus session bus (needed by GTK4)
if command -v dbus-launch >/dev/null 2>&1; then
  eval $(dbus-launch --sh-syntax)
fi

# Set keyboard repeat rate
xset r rate 250 30 2>/dev/null || true

# Start the window manager (openbox) in the background
openbox &
sleep 1

# Start EONIX background agents (non-fatal if they fail)
cd /home/eonix
bash /home/eonix/start_eonix.sh >/home/eonix/results/boot_agents.log 2>&1 &
AGENT_PID=$!

# Give agents time to initialize
sleep 4

# Launch the GTK4 Desktop (this is the main foreground process)
exec python3 /home/eonix/eonix-desktop/desktop.py
XINITEOF

chown eonix:eonix /home/eonix/.bashrc /home/eonix/.xinitrc
chmod +x /home/eonix/.xinitrc

# Runtime Python dependencies baked into the ISO
python3 -m pip install --break-system-packages --no-cache-dir --upgrade pip
python3 -m pip install --no-cache-dir \
  --break-system-packages \
  numpy scikit-learn lightgbm onnxruntime \
  psutil prompt_toolkit pytest-asyncio pyarrow \
  pycairo PyGObject python-xlib ewmh \
  httpx fastapi uvicorn aiohttp websockets zeroconf requests

# Avoid hard CI failures from very large optional AI wheels (torch/CUDA stack).
optional_python_packages=(
  sentence-transformers
  chromadb
)
for pkg in "${optional_python_packages[@]}"; do
  if ! python3 -m pip install --no-cache-dir --break-system-packages "$pkg"; then
    echo "[chroot_setup] WARNING: Optional Python package '$pkg' failed to install; continuing"
  fi
done

# Ensure MIND code exists inside the live filesystem
if [[ -d /home/eonix/eonix-os/eonix-mind ]]; then
  cp -a /home/eonix/eonix-os/eonix-mind /home/eonix/eonix-mind
  chown -R eonix:eonix /home/eonix/eonix-mind
else
  echo "[chroot_setup] WARNING: /home/eonix/eonix-os/eonix-mind missing; skipping copy" >&2
fi

# Pre-create the results directory so agent logs have somewhere to go
mkdir -p /home/eonix/results
chown eonix:eonix /home/eonix/results

apt-get clean
