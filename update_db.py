import sqlite3, os
DB = os.path.join("C:\\Users\\laska\\.gemini\\antigravity\\brain\\26c00955-554c-4fec-8c29-af755b84cdc8", "eonix_project_brain.db")
conn = sqlite3.connect(DB)
c = conn.cursor()
c.execute("UPDATE project_meta SET value='203', updated_at=date('now') WHERE key='cumulative_tests_passing'")
c.execute("UPDATE project_meta SET value='v1.5.0-dev', updated_at=date('now') WHERE key='version_current'")
c.execute("UPDATE project_meta SET value='43', updated_at=date('now') WHERE key='week_current'")
conn.commit()
for row in c.execute("SELECT key, value FROM project_meta"):
    print(f"{row[0]}: {row[1]}")
conn.close()
