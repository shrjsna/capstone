import sqlite3
from argon2 import PasswordHasher

ph = PasswordHasher()
conn = sqlite3.connect(r"c:\Games\repo-setup\repo-setup\cloud_backend.db")
c = conn.cursor()
c.execute("SELECT username, password_hash FROM users;")
users = c.fetchall()
conn.close()

passwords_to_try = [
    "admin", "admin123", "Admin123!", "AdminPassword123!", "AegisTestPassword123!",
    "Password123!", "OperatorPassword123!", "Operator123!", "OperatorPass123!",
    "operator", "operator1", "operator123", "Operator1234!", "Operator12345!",
    "Aegis2026!", "AegisSafety123!", "AegisAdmin123!", "InitialPassword123!",
    "TemporaryPass123!", "NewPermanentPass123!", "InitialTempPassword123!",
    "NewTemporaryPassword123!", "LockoutTest123!", "admin_secret",
    "Correct-Horse-Battery-Staple-2026!", "TestPassword123!", "Admin@123456",
    "Admin123456!", "Admin1234567!", "Admin12345678!", "Operator123456!"
]

for username, p_hash in users:
    matched = None
    for p in passwords_to_try:
        try:
            ph.verify(p_hash, p)
            matched = p
            break
        except Exception:
            pass
    print(f"User: {username} -> Password: {matched}")

