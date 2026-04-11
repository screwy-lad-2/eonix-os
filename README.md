# ⚡ EONIX OS — AI-Native Operating System

> Your OS knows what you are building.

[![CI](https://github.com/shahnoor-exe/eonix-os/actions/workflows/test.yml/badge.svg)](https://github.com/shahnoor-exe/eonix-os/actions/workflows/test.yml)
[![Tests](https://img.shields.io/badge/tests-162%2B_target-brightgreen)](https://github.com/shahnoor-exe/eonix-os/actions)
[![Version](https://img.shields.io/badge/version-v0.9.0-blue)](https://github.com/shahnoor-exe/eonix-os/tags)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## What Is EONIX OS?

EONIX OS is an AI-first operating layer on Linux that combines a goal-aware shell, autonomous agents, and a self-improving scheduler into one cohesive developer environment. It is designed so the system understands intent, keeps context over time, and helps execute workflows across local and networked nodes.

Today, EONIX ships as a full stack with EonixShell, MIND v2, GoalEngine, ContextAgent, ResourceAgent, SyncDaemon, Android companion app, and the web-based Eonix Hub. The next milestone is a bootable ISO in Month 8.

## Architecture Diagram (ASCII)

```text
┌─────────────────────────────────────────┐
│           EONIX OS v0.9.0               │
├──────────┬──────────┬────────┬──────────┤
│  Shell   │  MIND    │  Hub   │ Android  │
│ (v0.6)   │  v2.0    │ :7750  │   App    │
├──────────┴──────────┴────────┴──────────┤
│  GoalEngine  │  ContextAgent  │  Sync   │
│    :7735     │     :7736      │  :7740  │
├──────────────┼────────────────┼─────────┤
│ ResourceAgent│   Memory(DB)   │StateStore│
│    :7737     │  (ChromaDB)    │  JSON   │
├──────────────┴────────────────┴─────────┤
│         AI Scheduler (LightGBM+ONNX)    │
│    v1.1 | 61.61% Top-3 | Auto-retrains  │
└─────────────────────────────────────────┘
```

## Quick Install (Linux)

```bash
curl -fsSL https://raw.githubusercontent.com/shahnoor-exe/eonix-os/master/install/eonix-install.sh | bash
eonix-shell
```

## Quick Start (Dev)

```bash
git clone https://github.com/shahnoor-exe/eonix-os.git
cd eonix-os
bash install/eonix-install.sh --dev
bash start_eonix.sh
python3 eonix-shell/shell.py
```

## Features Table

| Feature              | Status  | Since   |
|----------------------|---------|---------|
| AI Scheduler         | ✅ Live | Month 1 |
| EONIX MIND v2.0      | ✅ Live | Month 4 |
| GoalEngine           | ✅ Live | Month 4 |
| Persistent Memory    | ✅ Live | Month 4 |
| ContextAgent         | ✅ Live | Month 3 |
| ResourceAgent        | ✅ Live | Month 4 |
| SyncDaemon (LAN)     | ✅ Live | Month 5 |
| Android App          | ✅ Live | Month 5 |
| Eonix Hub            | ✅ Live | Month 5 |
| EonixShell           | ✅ Live | Month 6 |
| NL Interpreter       | ✅ Live | Month 6 |
| Installer            | ✅ Live | Month 6 |
| Desktop GUI          | ✅ Live | Month 7 |
| Bootable ISO         | ✅ Live (GTK4 desktop confirmed) | Month 9 |

## Test Coverage

162+ target tests | 30 CI jobs | 0 failures target

## Week 27 ISO Build (Codespaces)

Week 27 requires Linux tooling for debootstrap/live ISO preparation. Use GitHub Codespaces for the full pipeline:

```bash
bash iso/codespaces_build.sh
RUN_FULL_BUILD=1 bash iso/codespaces_build.sh
```

Detailed instructions are in docs/week27_codespaces.md.

## Boot EONIX OS

You can boot the full ISO on VirtualBox (4GB RAM, 2 CPUs, VMSVGA display) or QEMU:
```bash
qemu-system-x86_64 -cdrom eonix-os-0.9.0.iso -m 4G
```

![GTK4 Desktop Month 9](results/week34_desktop_final.png)

## Roadmap

Month 7 → Eonix Desktop (GTK GUI, shipped v0.7.0)
Month 8 → Bootable ISO
Month 9 → Hardware testing
Month 10 → Public release

## Author

Shahnoor | B.Tech | Presidency University
https://github.com/shahnoor-exe/eonix-os
