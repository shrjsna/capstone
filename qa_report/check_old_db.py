import sqlite3
conn = sqlite3.connect(r"c:\Games\repo-setup\repo-setup\cloud_backend.db")
c = conn.cursor()
c.execute("SELECT id, ts, actor, action, target, outcome, detail FROM audit_log WHERE action LIKE '%user%' OR action LIKE '%auth%' ORDER BY id DESC LIMIT 40;")
for r in c.fetchall():
    print(r)
conn.close()
