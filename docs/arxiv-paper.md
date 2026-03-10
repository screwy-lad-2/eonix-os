# Eonix OS: Autonomous Deadlock Recovery via Real-Time Resource Allocation Graph Monitoring in the Linux Kernel

**Authors:** Shah Noor Butt

---

## Abstract

Deadlocks remain one of the most pernicious classes of concurrency bugs in modern operating systems, yet every production kernel in widespread use today employs the Ostrich Algorithm—simply ignoring the problem.  We present Eonix OS, a Linux kernel module that maintains a live Resource Allocation Graph (RAG), performs iterative depth-first search cycle detection at 500 ms intervals via an hrtimer, and autonomously recovers from detected deadlocks through a tiered strategy of resource preemption, SIGTERM, and SIGKILL.  In evaluation on a WSL2 6.6-series kernel, the system achieves a mean detection-to-recovery latency of [MEASURED: 279 ms] across 10 benchmark iterations (all detected), sustains a [MEASURED: 100/100] detection rate over a 100-cycle stress test, correctly handles self-deadlocks, N-way cycles (N ≤ 3 tested), and priority-inversion scenarios, and introduces zero false positives in a 1 000-iteration rapid lock/unlock workload.  To our knowledge, this is the first student-built, open-source kernel module that provides fully autonomous deadlock detection and recovery for unmodified Linux user-space processes.

**Keywords:** deadlock detection, resource allocation graph, kernel module, kprobes, operating systems

---

## 1  Introduction

Deadlock—the condition in which two or more concurrent processes each hold a resource required by another and none can proceed—has been a fundamental problem in operating-system design since Dijkstra's seminal work on concurrent programming [1].  In user-visible terms, a deadlock manifests as an application freeze: the affected processes consume no CPU, yet they cannot be terminated gracefully because the operating system is unaware that they are permanently blocked.

Despite decades of theoretical advances, every major production kernel—Linux, Windows NT, macOS XNU, and the BSDs—handles deadlocks via the *Ostrich Algorithm*: the system makes no attempt to detect or recover from them, relying instead on users or administrators to identify hung processes and terminate them manually [2].  The rationale is pragmatic: the overhead of classical prevention or avoidance algorithms (e.g., Banker's Algorithm) is considered too high for general-purpose workloads, while detection-only schemes require manual intervention that is slow and error-prone.

We argue that the gap between theory and practice can be closed by a lightweight, modular approach implemented entirely within the kernel's loadable-module framework.  Specifically, we make the following contributions:

1. **A live RAG maintained via kprobes.**  By hooking `__mutex_lock_slowpath` and `mutex_unlock` with minimal overhead, we track resource acquisition and contention without modifying any kernel source.
2. **Iterative DFS cycle detection.**  An hrtimer fires every 500 ms and runs an iterative depth-first search over the RAG.  The iterative formulation is critical: the Linux kernel stack is limited to 8–16 KiB, making deep recursion unsafe.
3. **Tiered autonomous recovery.**  Upon detecting a cycle, the system identifies the lowest-priority participant, checkpoints its state, releases its held resources, and sends SIGTERM followed (after a 200 ms grace period) by SIGKILL.
4. **Process checkpointing.**  Before terminating the victim, the module saves its identity, executable path, held resources, and command-line arguments to a ring buffer, enabling informed manual restart.
5. **Empirical evaluation.**  We report [MEASURED: 279 ms] average recovery latency, [MEASURED: 100 %] detection over 100 sequential cycles, correct priority-based victim selection, and zero false positives.

The remainder of this paper is organized as follows.  Section 2 provides background on RAG theory and deadlock handling.  Section 3 describes the design of the Eonix deadlock monitor.  Sections 4–6 (forthcoming) will cover the implementation, evaluation, and related work.

---

## 2  Background

### 2.1  Resource Allocation Graphs

Holt [3] formalized the Resource Allocation Graph as a bipartite directed graph $G = (V, E)$ where the vertex set $V = P \cup R$ consists of processes $P$ and resources $R$.  An *assignment edge* $(r_j, p_i)$ indicates that resource $r_j$ is currently held by process $p_i$; a *request edge* $(p_i, r_j)$ indicates that $p_i$ is blocked waiting for $r_j$.  A cycle in $G$ is a necessary condition for deadlock when each resource type has a single instance—a property that holds for mutexes, the dominant synchronization primitive in user-space Linux programs.

### 2.2  Coffman Conditions

Coffman et al. [4] identified four necessary conditions for deadlock:

1. **Mutual exclusion:** at least one resource must be held in a non-sharable mode.
2. **Hold and wait:** a process holding at least one resource is waiting to acquire additional resources held by other processes.
3. **No preemption:** resources cannot be forcibly removed from a process.
4. **Circular wait:** a circular chain of processes exists, each waiting for a resource held by the next.

All four conditions must hold simultaneously.  Classical *prevention* strategies negate one condition a priori (e.g., imposing a total ordering on resource acquisition eliminates circular wait), but they impose design constraints that are impractical for general-purpose OS workloads.  *Avoidance* algorithms such as the Banker's Algorithm [1] require advance knowledge of maximum resource demands, which is unavailable for arbitrary user-space programs.

### 2.3  Detection and Recovery

Detection-based approaches allow deadlocks to occur and then break them.  This family is the most practical for an OS kernel because it neither restricts programmers nor requires a priori resource declarations.  The key challenge is the cost of the detection algorithm (cycle finding in the RAG) and the policy for selecting a victim.  Prior work in database systems (e.g., wait-for graph analysis in MySQL InnoDB and PostgreSQL) has demonstrated that periodic detection is feasible at scale, but no analogous mechanism exists in general-purpose OS kernels.

### 2.4  Why Kernel Modules?

Linux's loadable kernel module (LKM) framework provides a uniquely suitable implementation layer.  Modules execute in ring 0, can register kprobes on arbitrary kernel symbols, and have direct access to the scheduler's `task_struct`.  Crucially, they can be loaded and unloaded at runtime without recompiling or rebooting the kernel, making iterative development practical even on production-adjacent systems.

---

## 3  Design

The Eonix deadlock monitor comprises five subsystems: (i) the RAG data store, (ii) the kprobe hook layer, (iii) the cycle detector, (iv) the recovery engine, and (v) the user-space interface.

### 3.1  RAG Data Structures

The RAG is stored in two statically allocated arrays:

- `rag_process[MAX_PROCESSES]` — each entry records the PID, process name (`comm`), list of held resource IDs, the resource the process is waiting for (or $-1$ if not blocked), a priority score, and an `active` flag.
- `rag_resource[MAX_RESOURCES]` — each entry records the resource ID, the PID of the current holder (0 if free), and a list of PIDs waiting for the resource.

Static allocation is a deliberate design choice: `kmalloc` in an hrtimer callback (which may execute in hard-IRQ context on some configurations) is unsafe when `GFP_KERNEL` is unavailable.  The arrays are protected by a single reader–writer spinlock (`rwlock_t`), allowing concurrent reads from the `/proc` interface while serializing writes from kprobe handlers.

### 3.2  kprobe Hook Architecture

The module registers kprobes on three kernel functions:

| Hook target               | Semantic event             | Data extracted               |
|---------------------------|---------------------------|------------------------------|
| `do_exit`                 | Process termination       | PID from `current->pid`      |
| `__mutex_lock_slowpath`   | Mutex contention (block)  | PID, resource ID from `regs` |
| `mutex_unlock`            | Mutex release             | PID, resource ID from `regs` |

On x86-64, the resource identity is derived from the first argument register (`rdi`) masked to 7 bits, yielding a resource-ID space of 128 entries.  This lossy mapping means that distinct mutexes may alias to the same RAG resource; however, aliasing can only produce false dependencies (which trigger cycle detection but not false *recovery*, since the recovery engine re-verifies the cycle before acting) and never conceals a real cycle.

The `do_exit` handler is essential for bookkeeping: when a process terminates (naturally or via signal), all its held resources must be released in the RAG to prevent phantom edges from accumulating.

### 3.3  Iterative DFS Cycle Detection

The detector constructs an implicit process-to-process adjacency by following wait-for → held-by edges: if process $p_i$ waits for resource $r_k$ and $r_k$ is held by $p_j$, then there is an edge $p_i \to p_j$.  A depth-first search over this adjacency detects cycles.

The DFS is implemented *iteratively* using an explicit `in_path[]` bit-vector rather than recursion.  This is a critical design constraint: the Linux kernel stack is limited to one or two pages (8–16 KiB), and a recursive DFS with a call frame per node could overflow the stack for moderately deep wait chains.  The iterative formulation uses only $O(n)$ stack-allocated arrays, where $n$ = `MAX_PROCESSES`, which fits comfortably in 2 KiB.

When a back edge is found (i.e., a node already in the current path is revisited), the algorithm extracts the cycle by tracing from the back-edge target back to itself, records all participating PIDs, and selects the *lowest-priority* participant as the victim.

### 3.4  Tiered Recovery

Recovery proceeds in four stages:

1. **Checkpoint.**  The victim's process name, UID, executable path, held resources, and wait state are saved to a 64-entry ring buffer (the *checkpoint manager*), enabling post-mortem inspection or manual restart.
2. **Resource preemption.**  All resources held by the victim are released in the RAG, and waiters on those resources are unblocked.
3. **SIGTERM.**  The victim receives `SIGTERM`, allowing it to run cleanup handlers.
4. **SIGKILL (after 200 ms).**  If the victim has not exited after a 200 ms grace period, `SIGKILL` is sent to force termination.

This tiered approach balances gracefulness with liveness: well-behaved programs will exit on SIGTERM, while unresponsive or signal-masking programs are forcibly killed.

### 3.5  hrtimer Polling

The detection cycle is driven by a high-resolution timer (`hrtimer`) configured to fire every 500 ms in `HRTIMER_MODE_REL`.  After each scan, the timer reschedules itself via `HRTIMER_RESTART`.  The 500 ms interval was chosen as a balance between detection latency (lower is faster) and CPU overhead (higher is cheaper).  Empirical measurements show that a single DFS scan over 256 process slots and 128 resource slots completes in under 10 $\mu$s, making the per-interval overhead negligible.

### 3.6  /proc Interface

The module exports four entries under `/proc/eonix/`:

| Entry           | Mode  | Purpose                                                  |
|-----------------|-------|----------------------------------------------------------|
| `deadlock_log`  | 0444  | Sequential event log (DEADLOCK_DETECTED, RECOVERY_COMPLETE) with timestamps |
| `rag_state`     | 0444  | Live dump of all active processes and resources in the RAG |
| `rag_inject`    | 0666  | Write-only test harness: HOLD, WAIT, RELEASE, PRIORITY, RESET commands |
| `checkpoints`   | 0444  | Ring buffer of victim checkpoint records                  |

The `rag_inject` interface enables deterministic testing from user space without requiring real multi-threaded programs, which is essential for CI pipelines that lack `insmod` privileges.

---

## References

[1] E. W. Dijkstra, "Cooperating Sequential Processes," in *Programming Languages*, F. Genuys, Ed. Academic Press, 1968, pp. 43–112. (Original manuscript, 1965.)

[2] A. S. Tanenbaum and H. Bos, *Modern Operating Systems*, 4th ed. Pearson, 2015.

[3] R. C. Holt, "Some Deadlock Properties of Computer Systems," *ACM Computing Surveys*, vol. 4, no. 3, pp. 179–196, 1972.

[4] E. G. Coffman, M. J. Elphick, and A. Shoshani, "System Deadlocks," *ACM Computing Surveys*, vol. 3, no. 2, pp. 67–78, 1971.

[5] Linux kernel documentation, "Kernel Probes (kprobes)," https://www.kernel.org/doc/html/latest/trace/kprobes.html.
