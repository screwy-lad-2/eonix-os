#!/bin/bash
set -e
echo "=== Eonix Emoji Fix ==="

if ! fc-list | grep -q "Noto Color"; then
  sudo apt-get install -y \
    fonts-noto-color-emoji fonts-noto-core \
    fonts-liberation locales
fi

if ! locale -a | grep -q "en_US.utf8"; then
  sudo locale-gen en_US.UTF-8
  sudo update-locale LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8
fi

sudo mkdir -p /etc/fonts/conf.d
sudo tee /etc/fonts/conf.d/99-eonix-emoji.conf > /dev/null << 'FONTEOF'
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <alias>
    <family>sans-serif</family>
    <prefer>
      <family>Noto Sans</family>
      <family>Noto Color Emoji</family>
      <family>DejaVu Sans</family>
    </prefer>
  </alias>
  <alias>
    <family>monospace</family>
    <prefer>
      <family>DejaVu Sans Mono</family>
      <family>Noto Color Emoji</family>
    </prefer>
  </alias>
</fontconfig>
FONTEOF

fc-cache -fv

grep -q "LANG=en_US.UTF-8" /etc/environment || \
  echo 'LANG=en_US.UTF-8
LC_ALL=en_US.UTF-8' | sudo tee -a /etc/environment

echo 'export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export PYTHONIOENCODING=utf-8
export GDK_BACKEND=x11' >> ~/.profile

echo "=== Done. Run: bash ~/start_eonix.sh ==="
