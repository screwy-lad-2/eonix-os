# EONIX OS — CLAUDE OPUS AGENT BRAIN
# File: eonix_project_brain_prompt.md
# Use this EVERY TIME you start a Claude Opus session on this project.
# Do NOT read individual source files first — read the DB first.

---

## STARTUP INSTRUCTION FOR CLAUDE OPUS AGENT

You are the Eonix OS project agent. Before doing ANYTHING else, run this script:

```python
import sqlite3, json

DB = "eonix_project_brain.db"  # located at repo root
conn = sqlite3.connect(DB)
c = conn.cursor()

# Load full project context
meta    = dict(c.execute("SELECT key, value FROM project_meta").fetchall())
modules = c.execute("SELECT name, status, risks, notes FROM modules ORDER BY layer").fetchall()
files   = c.execute("SELECT filepath, status, change_summary, known_issues FROM files").fetchall()
issues  = c.execute("SELECT priority, title, description, status FROM open_issues WHERE status='OPEN' ORDER BY priority").fetchall()
pending = c.execute("SELECT week, title, description, blockers FROM tasks WHERE status IN ('PENDING','NOT_STARTED') ORDER BY week").fetchall()
latest  = c.execute("SELECT session_id, summary, next_steps FROM session_context ORDER BY id DESC LIMIT 1").fetchone()
model   = c.execute("SELECT version, active, training_rows, notes FROM model_versions").fetchall()

print("=== EONIX OS PROJECT BRAIN LOADED ===")
print(f"Version: {meta['version_current']} | Month: {meta['month_current']} | Week: {meta['week_current']}")
print(f"Tests: {meta['cumulative_tests_passing']} passing | AI Model: {meta['ai_model_active']}")
print(f"Retrain: {meta['training_rows_current']}/{meta['training_rows_target']} rows | ETA: {meta['retrain_eta']}")
print(f"Health: {meta['project_health_score']} | CI: {meta['ci_mode']}")
print()
print("OPEN ISSUES:")
for p, t, d, s in issues:
    print(f"  [{p}] {t}")
print()
print("PENDING TASKS:")
for w, t, d, b in pending:
    print(f"  Week {w}: {t} — blockers: {b}")
print()
print("LAST SESSION:")
if latest: print(f"  {latest[0]}: {latest[1]}")
print()
print("NEXT STEPS:")
if latest:
    steps = json.loads(latest[2])
    for s in steps: print(f"  → {s}")

conn.close()
```

After running this, you have full project context. 
You now know EXACTLY where the project is without reading any source files.

---

## HOW TO LOG EVERY CHANGE YOU MAKE

After EVERY file change, run this:

```python
import sqlite3, json
from datetime import datetime

conn = sqlite3.connect("eonix_project_brain.db")
c = conn.cursor()

# 1. Log the change
c.execute("""INSERT INTO change_log
  (timestamp, session, file_changed, change_type, description, commit_hash, author)
  VALUES(?,?,?,?,?,?,?)""", (
    datetime.now().isoformat(),
    "SESSION-ID-HERE",        # replace with current session id
    "path/to/changed/file",   # full relative path
    "FIX|FEATURE|REFACTOR|TEST|CONFIG",
    "Describe exactly what changed and why",
    "commit_hash_if_known",
    "Claude Opus 4.5 Agent"
))

# 2. Update the file record
c.execute("""UPDATE files SET
  status=?, last_changed=?, change_summary=?, known_issues=?
  WHERE filepath=?""", (
    "COMPLETE|FIXED|PARTIAL",
    datetime.now().isoformat(),
    "What was changed",
    "Any remaining issues",
    "path/to/changed/file"
))

# 3. Update task if completing one
c.execute("""UPDATE tasks SET
  status='DONE', result=?, completed_at=?
  WHERE title=?""", (
    "What was achieved",
    datetime.now().isoformat(),
    "Task title here"
))

conn.commit()
conn.close()
print("✅ Brain updated")
```

---

## HOW TO START EACH SESSION

```python
import sqlite3, json
from datetime import datetime

conn = sqlite3.connect("eonix_project_brain.db")
c = conn.cursor()
SESSION_ID = f"SESSION-{datetime.now().strftime('%Y%m%d-%H%M')}"

c.execute("""INSERT INTO session_context
  (session_id, started_at, summary, files_touched, tasks_completed, next_steps)
  VALUES(?,?,?,?,?,?)""", (
    SESSION_ID,
    datetime.now().isoformat(),
    "Session started",
    json.dumps([]),
    json.dumps([]),
    json.dumps([])
))
conn.commit()
conn.close()
```

## HOW TO END EACH SESSION

```python
import sqlite3, json
from datetime import datetime

conn = sqlite3.connect("eonix_project_brain.db")
c = conn.cursor()

c.execute("""UPDATE session_context SET
  ended_at=?, summary=?, files_touched=?, tasks_completed=?, next_steps=?
  WHERE session_id=?""", (
    datetime.now().isoformat(),
    "One sentence summary of what was done this session",
    json.dumps(["list", "of", "files", "touched"]),
    json.dumps(["list", "of", "tasks", "completed"]),
    json.dumps(["next", "priority", "items"]),
    "SESSION-ID-HERE"
))
conn.commit()
conn.close()
print("✅ Session closed and logged")
```

---

## KEY RULES FOR CLAUDE OPUS AGENT

1. ALWAYS load the DB first — never start from scratch
2. ALWAYS log every file change to change_log table  
3. ALWAYS update the files table after editing a file
4. ALWAYS update tasks table when completing a task
5. NEVER ignore open_issues — check them before each task
6. ALWAYS open a session at start and close at end
7. If rows >= 120,000 → immediately run retrain, update model_versions
8. Rollback threshold is 2% — log rollback decision in change_log
9. Before any ISO work → check if CI is manual-only in project_meta
10. test target = 162+ Windows | 182+ Linux — never break this

---

## DATABASE TABLES REFERENCE

| Table            | Purpose                              |
|------------------|--------------------------------------|
| project_meta     | Global project state (KV store)      |
| modules          | Layer-by-layer module status         |
| files            | Per-file status + logic + issues     |
| tasks            | All tasks (done/pending/not started) |
| test_suites      | Test counts per month                |
| ci_runs          | CI run history + fixes               |
| change_log       | Every change ever made               |
| open_issues      | Active blockers + resolutions        |
| agent_ports      | Port map for all 5 agents            |
| model_versions   | v1.1 live, v1.2 pending              |
| release_history  | All releases with ISO/boot status    |
| session_context  | Session-by-session log               |
