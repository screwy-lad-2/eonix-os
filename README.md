# ⚡ Eonix OS

> **An Intent-Driven, Self-Healing, AI-Native Operating System**

[![Build](https://github.com/shahnoor-exe/eonix-os/actions/workflows/test.yml/badge.svg)](https://github.com/shahnoor-exe/eonix-os/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## Vision

Eonix OS reimagines the operating system as an **intelligent, goal-aware system** that understands user intent, self-heals from failures, proactively manages resources, and provides a unified experience across all devices — powered by embedded AI at every layer.

No existing OS addresses all of these simultaneously: **self-healing deadlocks, predictive scheduling, behavioral security, cross-device continuity, and a JARVIS-like voice assistant** — Eonix OS does.

---

## 5-Layer Architecture

```
╔══════════════════════════════════════════════════════════════╗
║  LAYER 5 │ EONIX SHELL    — Spatial Adaptive UI             ║
╠══════════════════════════════════════════════════════════════╣
║  LAYER 4 │ EONIX MIND     — JARVIS Cognitive Assistant      ║
╠══════════════════════════════════════════════════════════════╣
║  LAYER 3 │ EONIX CORTEX   — Agent Kernel (LLM-Embedded)     ║
╠══════════════════════════════════════════════════════════════╣
║  LAYER 2 │ EONIX CORE     — Smart Microkernel               ║
╠══════════════════════════════════════════════════════════════╣
║  LAYER 1 │ EONIX SILICON  — Hardware Abstraction Layer      ║
╚══════════════════════════════════════════════════════════════╝
              ↕  Legacy Bridge: POSIX │ Win32 │ Android
```

---

## Project Structure

```
eonix-os/
├── eonix-silicon/          # Layer 1: Hardware Abstraction Layer (Rust)
├── eonix-core/             # Layer 2: Smart Microkernel
│   ├── deadlock/           #   Self-healing deadlock manager (C kernel module)
│   ├── scheduler/          #   ML-predictive scheduler (C + ONNX)
│   ├── security/           #   eBPF security fabric (eBPF + Python)
│   ├── memory/             #   Adaptive memory manager (C kernel module)
│   └── ipc/                #   Capability-based IPC broker (Rust + Cap'n Proto)
├── eonix-cortex/           # Layer 3: Agent Kernel
│   ├── context-agent/      #   Cognitive context tracker (Python + ChromaDB)
│   ├── goal-engine/        #   Goal-first OS primitive (Python + JSON)
│   ├── cross-device/       #   CRDT-based device sync (Python + automerge)
│   └── resource-agent/     #   Goal-aware resource allocator (Python)
├── eonix-mind/             # Layer 4: JARVIS Cognitive Assistant
│   ├── stt/                #   Speech-to-text (faster-whisper)
│   ├── llm/                #   Language model (LLaMA 3.2 3B)
│   ├── tts/                #   Text-to-speech (Kokoro TTS)
│   ├── vision/             #   Screen understanding (LLaVA / Moondream2)
│   └── proactive/          #   Background monitoring & proactive alerts
├── eonix-shell/            # Layer 5: Spatial Adaptive UI
│   ├── compositor/         #   Wayland compositor (Rust / Smithay)
│   └── ui/                 #   UI framework (Flutter / Iced)
├── legacy-bridge/          # POSIX / Win32 / Android compatibility
├── datasets/               # Training data (scheduler, security)
├── models/                 # ML model weights (ONNX, GGUF, Whisper)
├── tests/                  # Unit, integration, E2E tests
├── docs/                   # Architecture docs & research paper
└── .github/workflows/      # CI/CD pipelines
```

---

## Core Features

| # | Feature | Module | Status |
|---|---------|--------|--------|
| 1 | **Self-Healing Deadlock Manager** | `eonix-core/deadlock/` | 🔨 Phase 1 |
| 2 | **ML-Predictive Scheduler** | `eonix-core/scheduler/` | 🔨 Phase 1 |
| 3 | **eBPF Behavioral Security** | `eonix-core/security/` | 🔨 Phase 1 |
| 4 | **JARVIS Voice Assistant (Eon)** | `eonix-mind/` | 📋 Phase 2 |
| 5 | **Context-Aware Agent Kernel** | `eonix-cortex/` | 📋 Phase 2 |
| 6 | **Cross-Device Continuity** | `eonix-cortex/cross-device/` | 📋 Phase 2 |
| 7 | **Goal-First OS Primitive** | `eonix-cortex/goal-engine/` | 📋 Phase 2 |
| 8 | **Adaptive Spatial Shell** | `eonix-shell/` | 📋 Phase 3 |
| 9 | **Legacy App Compatibility** | `legacy-bridge/` | 📋 Phase 3 |

---

## Tech Stack

| Category | Technologies |
|----------|-------------|
| **Languages** | Rust, C, Python, Dart, Go |
| **Kernel** | Custom microkernel (Rust) + Linux kernel modules (C) |
| **AI/ML** | LLaMA 3.2 3B, Whisper, Kokoro TTS, LLaVA, LightGBM, Isolation Forest |
| **Runtime** | ONNX Runtime, llama.cpp, faster-whisper |
| **Vector DB** | ChromaDB, LanceDB |
| **Sync** | automerge (CRDT), WebSockets, mDNS |
| **Security** | eBPF, seccomp-bpf, AppArmor, TLS 1.3 |
| **Shell** | Wayland, Smithay (Rust), Flutter |
| **IPC** | Cap'n Proto (zero-copy) |
| **CI/CD** | GitHub Actions |

---

## Quick Start (Development Environment)

### Prerequisites
- Ubuntu 24.04 LTS (dual boot or VM)
- GitHub Student Developer Pack (recommended)

### Setup

```bash
# Clone the repository
git clone https://github.com/shahnoor-exe/eonix-os.git
cd eonix-os

# Run the one-shot environment setup
chmod +x setup.sh
./setup.sh
```

See [docs/setup-guide.md](docs/setup-guide.md) for detailed instructions.

---

## Development Roadmap

| Phase | Timeline | Focus |
|-------|----------|-------|
| **Phase 0** | Weeks 1–8 | Environment setup, prerequisites, data collection |
| **Phase 1** | Weeks 9–28 | Core kernel modules (deadlock, scheduler, security) |
| **Phase 2** | Weeks 29–52 | EONIX MIND + Agent Kernel + Cross-device |
| **Phase 3** | Weeks 53–78 | Full OS integration, custom distro, shell |

---

## The 5-Minute Demo

1. **Boot Eonix OS** — custom dark shell with active goal in status bar
2. **"Hey Eon, what am I working on?"** — context-aware voice response
3. **Trigger a deadlock** — self-heals in <500ms, EONIX MIND announces recovery
4. **Suspicious process** — auto-detected and sandboxed by eBPF security fabric
5. **Pick up phone** — seamless context handoff via CRDT sync
6. **"Hey Eon, shut down gracefully"** — saves all context and powers off

---

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.

---

## Author

Built by [@shahnoor-exe](https://github.com/shahnoor-exe) — 2nd Year B.Tech CSE Student

> *"From zero to a living, thinking operating system."*
