#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y --no-install-recommends \
  linux-image-amd64 live-boot live-boot-initramfs-tools \
  live-config live-config-systemd \
  systemd systemd-sysv sudo curl wget git \
  python3 python3-pip python3-venv python3-gi python3-gi-cairo \
  gir1.2-gtk-4.0 libgtk-4-dev \
  portaudio19-dev ffmpeg espeak-ng \
  xorg xinit openbox xterm \
  network-manager xvfb dbus-x11

# Optional font and VTE packages — must not break the build
apt-get install -y --no-install-recommends fonts-noto-color-emoji || true
apt-get install -y --no-install-recommends fonts-noto || true
apt-get install -y --no-install-recommends gir1.2-vte-2.91 libvte-2.91-0 || true

# Nautilus file manager + GVFS backends for full file support
apt-get install -y --no-install-recommends \
  nautilus gvfs gvfs-backends libglib2.0-bin || true

# VirtualBox guest packages (optional, may not be in apt sources)
for pkg in virtualbox-guest-x11 virtualbox-guest-utils virtualbox-guest-dkms; do
  if apt-cache show "$pkg" >/dev/null 2>&1; then
    apt-get install -y --no-install-recommends "$pkg" || true
  else
    echo "[chroot_setup] INFO: Optional package '$pkg' not available; skipping"
  fi
done

# Verify init/systemd exists after install
if [ ! -f /sbin/init ] && [ ! -f /usr/sbin/init ] && \
   [ ! -L /sbin/init ]; then
    echo "ERROR: /sbin/init not found after setup!"
    ls -la /sbin/init /usr/sbin/init 2>/dev/null || true
    exit 1
fi
echo "VERIFY: init found at $(readlink -f /sbin/init)"

# Verify python3 works
python3 --version || { echo "ERROR: python3 missing"; exit 1; }

# Verify GTK4 is installed
python3 -c "import gi; gi.require_version('Gtk','4.0'); \
  from gi.repository import Gtk; print('GTK4 OK')" || \
  echo "WARN: GTK4 not available"

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

export DISPLAY=:0

# Start D-Bus session bus (needed by GTK4)
if command -v dbus-launch >/dev/null 2>&1; then
  eval $(dbus-launch --sh-syntax)
fi

xset r rate 250 30 2>/dev/null || true

# Start openbox window manager
openbox &
sleep 1

# Start EONIX agents (non-fatal)
cd /home/eonix
if [[ -f /home/eonix/eonix-os/start_eonix.sh ]]; then
  bash /home/eonix/eonix-os/start_eonix.sh >/home/eonix/results/boot_agents.log 2>&1 &
elif [[ -f /home/eonix/start_eonix.sh ]]; then
  bash /home/eonix/start_eonix.sh >/home/eonix/results/boot_agents.log 2>&1 &
fi

sleep 4

# Launch the GTK4 Desktop
if [[ -f /home/eonix/eonix-os/eonix-desktop/desktop.py ]]; then
  exec python3 /home/eonix/eonix-os/eonix-desktop/desktop.py
elif [[ -f /home/eonix/eonix-desktop/desktop.py ]]; then
  exec python3 /home/eonix/eonix-desktop/desktop.py
else
  echo "ERROR: desktop.py not found" >/home/eonix/results/desktop_error.log
  exec xterm
fi
XINITEOF

chown eonix:eonix /home/eonix/.bashrc /home/eonix/.xinitrc
chmod +x /home/eonix/.xinitrc

# Apply Eonix dark theme to Nautilus/GTK4 apps
mkdir -p /home/eonix/.config/gtk-4.0
if [[ -f /home/eonix/eonix-os/eonix-desktop/assets/gtk4-override.css ]]; then
  cp /home/eonix/eonix-os/eonix-desktop/assets/gtk4-override.css \
     /home/eonix/.config/gtk-4.0/gtk.css
fi
chown -R eonix:eonix /home/eonix/.config

# Runtime Python dependencies
python3 -m pip install --break-system-packages --no-cache-dir --upgrade pip
python3 -m pip install --no-cache-dir \
  --break-system-packages \
  numpy scikit-learn lightgbm onnxruntime \
  psutil prompt_toolkit pytest-asyncio pyarrow \
  pycairo PyGObject python-xlib ewmh \
  httpx fastapi uvicorn aiohttp websockets zeroconf requests

# Optional heavy AI packages
for pkg in sentence-transformers chromadb; do
  if ! python3 -m pip install --no-cache-dir --break-system-packages "$pkg"; then
    echo "[chroot_setup] WARNING: Optional '$pkg' failed; continuing"
  fi
done

# Ensure MIND code exists
if [[ -d /home/eonix/eonix-os/eonix-mind ]]; then
  cp -a /home/eonix/eonix-os/eonix-mind /home/eonix/eonix-mind
  chown -R eonix:eonix /home/eonix/eonix-mind
fi

mkdir -p /home/eonix/results
chown eonix:eonix /home/eonix/results

# Regenerate initramfs with all live-boot hooks
echo "[chroot_setup] Regenerating initramfs"
update-initramfs -u -k all 2>&1 || echo "[chroot_setup] WARNING: update-initramfs non-zero"

# Safe cleanup — do NOT remove system files
apt-get clean
apt-get autoremove -y
rm -rf /var/cache/apt/archives/*.deb
rm -f /tmp/*.tmp
