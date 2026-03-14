## v0.4.0 - Month 4: EONIX MIND v2.0 Full Integration
Released: March 2026

### Executive Summary
v0.4.0 completes the Month 4 integration milestone for EONIX MIND v2.0, unifying goal-driven orchestration, persistent memory, proactive intelligence, and resource-aware runtime controls.

### Platform Highlights

#### EONIX MIND v2.0
- JARVIS-style startup banner with live system snapshot.
- 600-token context pipeline across SystemReader, Memory, ContextAgent, and GoalEngine.
- ProactiveMonitor with 7 autonomous rules that can surface alerts without prompting.

#### GoalEngine (Port 7735)
- Voice-driven goal lifecycle: create, activate, complete, and track.
- Automatic progress estimation from commit activity and focus-time signals.
- Semantic goal retrieval via ChromaDB.
- SQLite persistence across reboot cycles.

#### Persistent Memory
- EonixMemory APIs for remember, recall, and forget powered by ChromaDB.
- Reboot-persistent memory state for long-horizon personalization.
- Auto-capture triggers including: remember that, my deadline is, I prefer, note that.
- Deadline reminder policy that triggers 7 days before due date.

#### ResourceAgent (Port 7737)
- Process relevance scoring against the active goal.
- Tiered CPU and RAM allocation policy by relevance class.
- Graceful fallback behavior when cgroup writes are unavailable.
- Dry-run mode for safe validation.

### Repository Hygiene
- Removed accidentally tracked Gradle/Kotlin DSL artifacts (commit 395228b).
- Hardened ignore rules for .gradle, build, and .kotlin cache artifacts.

### Test Coverage
| Suite | Tests |
|---|---:|
| Scheduler + retrain | 13 |
| ContextAgent | 5 |
| system_reader | 5 |
| mind_v1 | 3 |
| GoalEngine | 6 |
| memory | 5 |
| ProactiveMonitor | 4 |
| MIND v2.0 | 3 |
| TOTAL | 44 |

### CI and Validation
- 17/17 CI jobs green on master.
- Cumulative runner available via run_all_tests.py.

### Auto-Retrain Watch
- v1.1 active at 61.61% Top-3 with approximately 33,431 rows.
- v1.2 automatic trigger at 120,000 rows (estimated around April 1).

---
Next target: v0.5.0 - Month 5: Cross-Device Continuity
