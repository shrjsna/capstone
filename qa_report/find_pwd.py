import sys
sys.path.insert(0, r"c:\Games\repo-setup\repo-setup")
from argon2 import PasswordHasher
from cloud.backend.database import SessionLocal
from cloud.backend.models import UserModel

ph = PasswordHasher()
db = SessionLocal()

candidates = [
    "admin", "admin123", "Admin123!", "AdminPassword123!", "AegisTestPassword123!",
    "Password123!", "OperatorPassword123!", "Operator123!", "OperatorPass123!",
    "Aegis2026!", "AegisSafety123!", "AegisAdmin123!", "InitialPassword123!",
    "TemporaryPass123!", "NewPermanentPass123!", "admin_password", "admin_secret",
    "Correct-Horse-Battery-Staple-2026!", "TestPassword123!"
]

for u in db.query(UserModel).all():
    found = False
    for c in candidates:
        try:
            ph.verify(u.password_hash, c)
            print(f"MATCH: {u.username} -> {c}")
            found = True
            break
        except Exception:
            pass
    if not found:
        print(f"No candidate match for {u.username}")

db.close()

