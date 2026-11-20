import sqlite3
conn = sqlite3.connect(r"c:\Games\repo-setup\repo-setup\cloud_backend.db")
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table';")
print("Tables:", [r[0] for r in c.fetchall()])
try:
    c.execute("SELECT username, role, password_hash FROM users;")
    print("Users:", c.fetchall())
except Exception as e:
    print("Error querying users:", e)
conn.close()

