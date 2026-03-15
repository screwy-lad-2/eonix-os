# ⚡ EONIX OS — AI-Native Operating System

> Your OS knows what you are building.

[![CI](https://github.com/shahnoor-exe/eonix-os/actions/workflows/test.yml/badge.svg)](https://github.com/shahnoor-exe/eonix-os/actions/workflows/test.yml)
[![Tests](https://img.shields.io/badge/tests-108%2B_passing-brightgreen)](https://github.com/shahnoor-exe/eonix-os/actions)
[![Version](https://img.shields.io/badge/version-v0.6.0-blue)](https://github.com/shahnoor-exe/eonix-os/tags)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## What Is EONIX OS?

EONIX OS is an AI-first operating layer on Linux that combines a goal-aware shell, autonomous agents, and a self-improving scheduler into one cohesive developer environment. It is designed so the system understands intent, keeps context over time, and helps execute workflows across local and networked nodes.

Today, EONIX ships as a full stack with EonixShell, MIND v2, GoalEngine, ContextAgent, ResourceAgent, SyncDaemon, Android companion app, and the web-based Eonix Hub. The next milestones are Eonix Desktop GUI in Month 7 and a bootable ISO in Month 8.

## Architecture Diagram (ASCII)

```text
┌─────────────────────────────────────────┐
│           EONIX OS v0.6.0               │
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
| Desktop GUI          | 🔨 Month 7 | Planned |
| Bootable ISO         | 📅 Month 8 | Planned |

## Test Coverage

108+ tests | 24 CI jobs | 0 failures

## Roadmap

Month 7 → Eonix Desktop (GTK GUI)
Month 8 → Bootable ISO
Month 9 → Hardware testing
Month 10 → Public release

## Author

Shahnoor | B.Tech | Presidency University
https://github.com/shahnoor-exe/eonix-os
