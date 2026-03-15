#!/usr/bin/env bash
set -euo pipefail

BUILD_ROOT=${BUILD_ROOT:-"$HOME/eonix-iso-build"}
IMAGE="$BUILD_ROOT/image"
GRUB_DIR="$IMAGE/boot/grub"
THEME_DIR="$GRUB_DIR/themes/eonix"
EFI_DIR="$IMAGE/EFI/BOOT"

mkdir -p "$GRUB_DIR" "$THEME_DIR" "$EFI_DIR"

cat > "$GRUB_DIR/grub.cfg" <<'EOF'
set default=0
set timeout=5
set gfxmode=auto
set gfxpayload=keep

if loadfont /boot/grub/fonts/unicode.pf2; then
  set gfxmode=auto
  set gfxpayload=keep
fi

set color_normal=green/black
set color_highlight=black/green
terminal_output gfxterm
set theme=($root)/boot/grub/themes/eonix/theme.txt

menuentry '⚡ Boot EONIX OS' {
  linux /live/vmlinuz boot=live quiet splash
  initrd /live/initrd.img
}

menuentry 'Boot EONIX OS (Safe Mode)' {
  linux /live/vmlinuz boot=live nomodeset xforcevesa
  initrd /live/initrd.img
}

menuentry 'Boot from Hard Drive' {
  set root=(hd0)
  chainloader +1
}

menuentry 'Memory Test' {
  linux /live/memtest
}
EOF

cat > "$THEME_DIR/theme.txt" <<'EOF'
# EONIX OS GRUB Theme
# Dark base with neon green accents

+ boot_menu {
    title-color: "#00FF88";
    selected_item_color: "#0A0A0F";
    selected_item_bg_color: "#00FF88";
    item_color: "#E0E0E0";
    item_bg_color: "#0A0A0F";
}

desktop-color: "#0A0A0F";
terminal-color: "#00FF88";
title-text: "⚡ EONIX OS — Boot Menu";
EOF

touch "$THEME_DIR/background.png"
touch "$EFI_DIR/.keep"

if command -v grub-mkimage >/dev/null 2>&1; then
  grub-mkimage -o "$EFI_DIR/bootx64.efi" -O x86_64-efi -p /boot/grub fat iso9660 part_msdos part_gpt linux || true
else
  echo "grub-mkimage not found; skipping EFI image creation" >&2
fi

echo "GRUB configuration staged at $GRUB_DIR"
