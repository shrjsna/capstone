import sqlite3
conn = sqlite3.connect(r"c:\Games\repo-setup\repo-setup\cloud_backend.db")
c = conn.cursor()
c.execute("SELECT * FROM sessions;")
print("Sessions:", c.fetchall())
c.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 10;")
print("Audit log:", c.fetchall())
conn.close()

