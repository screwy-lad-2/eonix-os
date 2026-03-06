# Eonix OS — Architecture Overview

## 5-Layer Stack

### Layer 1: EONIX SILICON (Hardware Abstraction)
- Rust-based HAL for CPU, GPU, NPU, sensors
- Unified device mesh for cross-device hardware sharing
- Driver model: async Rust with DMA-safe memory management

### Layer 2: EONIX CORE (Smart Microkernel)
- **Deadlock Manager**: Real-time RAG (Resource Allocation Graph) with DFS cycle detection, automatic process checkpointing and recovery
- **Predictive Scheduler**: LightGBM model trained on personal usage data, predicts next process launch and pre-warms resources
- **Security Fabric**: eBPF-based syscall monitoring, Isolation Forest anomaly detection, automatic sandboxing via seccomp/gVisor
- **Memory Manager**: LRU-K + ML hybrid page replacement, NUMA-aware huge page management for ML model weights
- **IPC Broker**: Cap'n Proto zero-copy serialization with capability-based security tokens (seL4-inspired)

### Layer 3: EONIX CORTEX (Agent Kernel)
All agents follow the ReAct (Reason + Act) loop:
- **ContextAgent**: Tracks files, commands, apps, browser, git activity → embeds into ChromaDB → reconstructs session context on device switch
- **GoalEngine**: First-class Goal objects as OS primitives, tracks progress via git velocity + file edits + time spent
- **ResourceAgent**: Priority-weighted resource auctioning based on active goal relevance
- **Cross-Device Sync**: CRDT (automerge) state sync over WebSockets + mDNS discovery

### Layer 4: EONIX MIND (JARVIS Engine)
- Wake word detection → Whisper STT → context assembly → LLaMA 3.2 3B inference → action routing → Kokoro TTS response
- Personality: "Eon" — calm, efficient, proactive (JARVIS-inspired)
- Action tags: [OPEN_FILE], [KILL_PROCESS], [RUN_COMMAND], [ALERT], [SPEAK_ONLY]

### Layer 5: EONIX SHELL (Spatial Adaptive UI)
- Wayland compositor via Smithay (Rust)
- Context-aware layout modes: Coding, Reading, Meeting, Idle
- Goal progress bar in status bar, security alerts as toast notifications

## Key Algorithms
| Algorithm | Module | Purpose |
|-----------|--------|---------|
| DFS Cycle Detection | Deadlock Manager | Detect cycles in RAG |
| Banker's Algorithm | Deadlock Manager | Safe-state verification |
| LightGBM (GBDT) | Scheduler | Process launch prediction |
| Isolation Forest | Security Fabric | Syscall anomaly detection |
| LRU-K + ML | Memory Manager | Page replacement |
| CRDT (Automerge) | Cross-Device | Conflict-free state sync |
| ReAct Loop | All Agents | Reason-act-observe pattern |
| Cosine Similarity | ContextAgent | Semantic context retrieval |
