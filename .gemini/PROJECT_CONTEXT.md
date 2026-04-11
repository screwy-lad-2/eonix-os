# EONIX OS — AGENT CONTEXT
# Antigravity reads this automatically every session.

## CRITICAL: READ THIS BEFORE TOUCHING ANY FILE

This project has a SQLite brain at repo root:
  eonix_project_brain.db

BEFORE doing any task, run this in terminal:
  python3 -c "
import sqlite3, json
conn = sqlite3.connect('eonix_project_brain.db')
c = conn.cursor()
meta = dict(c.execute('SELECT key,value FROM project_meta').fetchall())
issues = c.execute(\"SELECT priority,title FROM open_issues WHERE status='OPEN'\").fetchall()
pending = c.execute(\"SELECT week,title,blockers FROM tasks WHERE status='PENDING'\").fetchall()
last = c.execute('SELECT summary,next_steps FROM session_context ORDER BY id DESC LIMIT 1').fetchone()
print('VERSION:', meta['version_current'], '| MONTH:', meta['month_current'])
print('TESTS:', meta['cumulative_tests_passing'], 'passing | MODEL:', meta['ai_model_active'])
print('RETRAIN:', meta['training_rows_current'],'/',meta['training_rows_target'],'rows')
print('CI MODE:', meta['ci_mode'])
print('OPEN ISSUES:')
[print(f'  [{p}] {t}') for p,t in issues]
print('PENDING:')
[print(f'  Week {w}: {t} | blockers: {b}') for w,t,b in pending]
print('LAST SESSION:', last[0] if last else 'None')
conn.close()
"

## PROJECT STATE (as of April 7 2026)
- Version: v0.9.0-rc | Month 9 Week 34
- 162 tests passing | 0 failing
- AI Model: LightGBM v1.1 active | v1.2 fires at 120,000 rows (73,499 now)
- CI: manual trigger only (workflow_dispatch)
- Repo: github.com/shahnoor-exe/eonix-os

## BLOCKERS (do not ignore)
1. [CRITICAL] v1.2 retrain not fired — ETA ~June 14
2. [CRITICAL] v0.9.0 ISO not rebuilt since chroot fixes
3. [HIGH] GTK4 desktop boot unconfirmed
4. [HIGH] Repo must be made private (4x CI quota)

## LOG EVERY CHANGE
After every file edit, run:
  python3 -c "
import sqlite3
from datetime import datetime
conn = sqlite3.connect('eonix_project_brain.db')
conn.execute('''INSERT INTO change_log
  (timestamp,session,file_changed,change_type,description,author)
  VALUES(?,?,?,?,?,?)''',
  (datetime.now().isoformat(),'ANTIGRAVITY-SESSION',
   'FILE_PATH','FIX','WHAT_CHANGED','Antigravity Agent'))
conn.commit(); conn.close()
print('Brain updated.')
"