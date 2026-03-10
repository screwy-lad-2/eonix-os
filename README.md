# ⚡ Eonix OS

[![Build](https://github.com/shahnoor-exe/eonix-os/actions/workflows/test.yml/badge.svg)](https://github.com/shahnoor-exe/eonix-os/actions)
[![Tests](https://img.shields.io/badge/tests-136_passing-brightgreen)](https://github.com/shahnoor-exe/eonix-os/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![arXiv](https://img.shields.io/badge/arXiv-2603.XXXXX-b31b1b.svg)](docs/arxiv-paper.pdf)

> **An intent-driven, self-healing, AI-native operating system — built by a 2nd year B.Tech student.**

---

## Key Results

| Metric | Value |
|--------|-------|
| 🔄 **Autonomous deadlock recovery** | **279 ms** average (234 ms min) |
| ✅ **Detection rate** | **100 %** across 130 deadlock scenarios |
| 🛡️ **False positives** | **0** across 1,000 benign lock/unlock cycles |
| ⚡ **CPU overhead** | **0.0125 %** for continuous kernel monitoring |
| 📊 **Tests passing** | **136** across C, Rust, Python, and eBPF |
| 📝 **Kernel module** | **770+ lines** of production kernel C |

---

## Demo

<!-- Replace with your demo GIF or YouTube thumbnail -->
> **[🎬 Watch the demo on YouTube](https://youtube.com/PLACEHOLDER)** — 4-minute live demonstration of autonomous deadlock recovery in a real Linux kernel.

```
$ sudo insmod eonix_deadlock.ko
$ sudo ./trigger_deadlock          # 2-way circular wait
[EONIX] DEADLOCK_DETECTED: cycle [PID 1001 → PID 1002 → PID 1001]
[EONIX] RECOVERY_COMPLETE: victim=PID 1002, duration=279ms
```

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
║           │  ├─ deadlock/  RAG Monitor (kprobes + DFS)  ✅   ║
║           │  ├─ scheduler/ ML-Predictive Scheduler      ✅   ║
║           │  ├─ security/  eBPF Syscall Monitor         ✅   ║
║           │  ├─ memory/    Adaptive Memory Manager      ✅   ║
║           │  └─ ipc/       Capability IPC Broker        ✅   ║
╠══════════════════════════════════════════════════════════════╣
║  LAYER 1 │ EONIX SILICON  — Hardware Abstraction Layer      ║
╚══════════════════════════════════════════════════════════════╝
              ↕  Legacy Bridge: POSIX │ Win32 │ Android
```

---

## How It Works

The **Self-Healing Deadlock Engine** (the core Month 2 deliverable) runs entirely inside the Linux kernel:

1. **kprobe hooks** intercept `__mutex_lock_slowpath` and `mutex_unlock` — building a live Resource Allocation Graph (RAG) with zero application changes.
2. **An hrtimer** fires every 500 ms and runs an **iterative DFS** over the RAG to detect cycles (iterative, not recursive — safe for the kernel's 8–16 KiB stack).
3. Upon detecting a cycle, the **tiered recovery engine**:
   - Checkpoints the victim process state (PID, comm, resources)
   - Preempts the victim's held resources
   - Sends SIGTERM → waits 200 ms → SIGKILL if still alive
4. Full event log available at `/proc/eonix/deadlock_log`, live RAG at `/proc/eonix/rag_state`.

---

## Quick Start

```bash
# Clone
git clone https://github.com/shahnoor-exe/eonix-os.git
cd eonix-os

# Build the deadlock module (requires WSL2 or native Linux)
cd eonix-core/deadlock
make

# Load the module
sudo insmod eonix_deadlock.ko

# Trigger a test deadlock
cd tests
gcc -O2 -Wall -pthread -o trigger_deadlock trigger_deadlock.c
sudo ./trigger_deadlock

# Watch it self-heal
sudo dmesg | grep EONIX
cat /proc/eonix/deadlock_log
```

---

## Research Paper

The full arXiv paper is included in this repository:

📄 **[Eonix OS: Autonomous Deadlock Recovery via Real-Time Resource Allocation Graph Monitoring in the Linux Kernel](docs/arxiv-paper.pdf)** (10 pages)

**arXiv submission:** `arXiv:2603.XXXXX` *(link will be updated upon acceptance)*

---

## Project Structure

```
eonix-os/
├── eonix-silicon/          # Layer 1: Hardware Abstraction Layer (Rust)
├── eonix-core/             # Layer 2: Smart Microkernel
│   ├── deadlock/           #   Self-healing deadlock manager (C kernel module)
│   │   ├── rag_monitor.c   #     770+ lines — RAG + DFS + recovery engine
│   │   ├── checkpoint.c    #     Process state checkpoint manager
│   │   ├── tests/          #     Stress tests, edge cases, triggers
│   │   └── results/        #     Benchmark data, overhead measurements
│   ├── scheduler/          #   ML-predictive scheduler (C + Python)
│   ├── security/           #   eBPF syscall monitor (7 tracepoints)
│   ├── memory/             #   Adaptive memory manager (C)
│   └── ipc/                #   Capability-based IPC broker (Rust)
├── eonix-cortex/           # Layer 3: Agent Kernel
├── eonix-mind/             # Layer 4: JARVIS Cognitive Assistant
├── eonix-shell/            # Layer 5: Spatial Adaptive UI
├── docs/                   # arXiv paper (MD + LaTeX + PDF)
└── .github/workflows/      # CI: 10 jobs, all passing
```

---

## 7-Month Roadmap

| Month | Focus | Status |
|-------|-------|--------|
| **1** | Environment + HAL + scheduler + memory + IPC | ✅ Complete |
| **2** | Self-healing deadlock engine + arXiv paper | ✅ **Complete** |
| **3** | eBPF security fabric + anomaly detection | 🔨 In progress |
| **4** | EONIX MIND — voice assistant (STT/LLM/TTS) | 📋 Planned |
| **5** | Agent Kernel + cross-device sync | 📋 Planned |
| **6** | Spatial shell + compositor | 📋 Planned |
| **7** | Integration, custom distro, public launch | 📋 Planned |

---

## Built With

![C](https://img.shields.io/badge/C-00599C?style=flat&logo=c&logoColor=white)
![Rust](https://img.shields.io/badge/Rust-000000?style=flat&logo=rust&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white)
![eBPF](https://img.shields.io/badge/eBPF-FF6600?style=flat&logoColor=white)
![Linux](https://img.shields.io/badge/Linux_Kernel-FCC624?style=flat&logo=linux&logoColor=black)
![GitHub Actions](https://img.shields.io/badge/CI-GitHub_Actions-2088FF?style=flat&logo=github-actions&logoColor=white)

---

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.

---

## Author

Built by **[@shahnoor-exe](https://github.com/shahnoor-exe)** — 2nd Year B.Tech CSE, Presidency University, Bengaluru

> *"From zero to a living, thinking operating system."*
