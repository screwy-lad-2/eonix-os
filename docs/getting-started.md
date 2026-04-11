# Getting Started with Eonix OS

## Requirements
- VirtualBox 7.0+
- 4GB RAM, 20GB disk free
- Windows, Mac, or Linux host

## Boot in VirtualBox
1. Download eonix-os-0.9.0.iso from GitHub Releases
2. VirtualBox -- New VM:
   - Name: Eonix OS | Type: Linux | Version: Debian 64
   - RAM: 4096 MB | CPUs: 2
   - Display: VMSVGA | VRAM: 128MB | 3D: OFF
3. Settings -- Storage -- attach ISO
4. Start VM -- select "Boot EONIX OS" in GRUB
5. Wait ~30s -- GTK4 desktop appears

## What You'll See
- GRUB menu -- "Starting EONIX OS..."
- 5 agents start (ports 7735-7750)
- Splash screen -- GTK4 desktop
- GoalPanel on left | TopBar with clock at top
- Hub status: http://localhost:7750/hub/status

## QEMU (Linux)
  qemu-system-x86_64 -cdrom eonix-os-0.9.0.iso -m 4G -smp 2
