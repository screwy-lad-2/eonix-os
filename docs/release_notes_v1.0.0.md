# Eonix OS v1.0.0 — Public Release (Coming June 2026)

## Overview
Eonix OS is an AI-native, self-healing operating system built from the ground up over 11 months. Version 1.0.0 represents the first stable, production-ready release, featuring a live LightGBM scheduler, ChromaDB-backed persistent memory, and a sophisticated GTK4 desktop environment.

### What's New vs v0.9.0
- **Beta Hardening:** All high and medium severity issues reported during the Week 39/40 beta period have been resolved.
- **Enhanced Testing:** Expanded the regression suite to **180+ verified integration tests**, ensuring absolute stability across the kernel and agent layers.
- **UI Polish:** Finalized the splash screen, TopBar, and workspace theme synchronization.
- **Documentation:** Full system architecture, API reference, and Getting Started guides are now complete and hosted on GitHub Pages.

### Complete Feature Set
- **AI Core:** LightGBM v1.2 engine (63.47% accuracy) trained on 148,812 rows. Features auto-retrain with 2% degradation rollback protection.
- **MIND v2:** Persistent vector memory using ChromaDB. Proactive system monitoring and contextual recall.
- **AI Agents (x5):** GoalEngine, ContextAgent, ResourceAgent, SyncDaemon, and Hub. All running as native background services.
- **GTK4 Desktop:** Premium UI with a 1.5s boot splash, dynamic GoalPanel, and centralized session manager.
- **EonixShell:** Natural language and voice command support with local STT/TTS processing.
- **Cross-Device Sync:** LAN-based peer discovery and state synchronization using zeroconf.
- **Bootable ISO:** Fully bootable Debian-based ISO supporting both BIOS and UEFI. Optimized for VirtualBox (Target: <20s boot).

### Performance Metrics
  Boot time: ~18 seconds (GRUB → desktop)
  RAM at idle: ~1.2 GB
  Model accuracy: 63.47% (v1.2)
  Tests passing: 185+ | Failing: 0

### Install & Getting Started
- **Download:** Available via [GitHub Releases](https://github.com/shahnoor-exe/eonix-os/releases).
- **VM Requirements:** VirtualBox 7.0+, 4GB RAM, 2 CPUs, VMSVGA Graphics (3D Disabled).
- **Official Docs:** [shahnoor-exe.github.io/eonix-os](https://shahnoor-exe.github.io/eonix-os)

### Build Info
- ISO: eonix-os-1.0.0.iso
- Base: Debian 12 (Bookworm)
- Kernel: Linux 6.x
- Desktop: GTK4 (GLib 2.x)
- Python: 3.11+
- AI: LightGBM 4.3+ + ONNX

### Built By
Shahnoor — 11 months solo development
github.com/shahnoor-exe/eonix-os
