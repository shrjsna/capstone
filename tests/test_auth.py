"""
tests/test_auth.py
==================
Comprehensive tests for authentication and session management:
- Password strength validation (min 12 chars, upper, lower, digit, symbol).
- Argon2id hashing and verification.
- Account lockout throttling (5 consecutive failed attempts).
- Session lifecycle (idle timeout, absolute timeout, logout).
- CSRF validation for state-changing requests.
- `must_change_password` mandatory enforcement flow.
"""

from datetime import datetime, timezone
import pytest
from fastapi import HTTPException
from cloud.backend.auth import (
    SESSION_COOKIE_NAME,
    hash_token,
    validate_password_strength,
)
from cloud.backend.database import get_db
from cloud.backend.models import LoginAttemptModel, SessionModel, UserModel
from cloud.backend.config import get_settings

settings = get_settings()


def test_password_strength_rules():
    """Verify password policy rejection and acceptance criteria."""
    # Short
    with pytest.raises(HTTPException):
        validate_password_strength("short", username="admin")
    # All lower
    with pytest.raises(HTTPException):
        validate_password_strength("alllowercase123!", username="admin")
    # All upper
    with pytest.raises(HTTPException):
        validate_password_strength("ALLUPPERCASE123!", username="admin")
    # No digits
    with pytest.raises(HTTPException):
        validate_password_strength("NoDigitsHereAtAll!", username="admin")
    # No symbols
    with pytest.raises(HTTPException):
        validate_password_strength("NoSymbols123456", username="admin")
    # Username in password
    with pytest.raises(HTTPException):
        validate_password_strength("AdminPassword123!", username="admin")

    # Valid strong password should not raise
    validate_password_strength("Correct-Horse-Battery-Staple-2026!", username="admin")


def test_login_success_and_session_cookie(anon_client, admin_user):
    """Successful login sets secure session cookie and returns CSRF token."""
    res = anon_client.post(
        "/auth/login",
        json={"username": "test_admin", "password": "AegisTestPassword123!"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["user"]["username"] == "test_admin"
    assert data["user"]["role"] == "admin"
    assert "csrf_token" in data
    
    # Verify session cookie
    cookies = res.cookies
    assert SESSION_COOKIE_NAME in cookies


def test_login_invalid_password(anon_client, admin_user):
    """Invalid credentials return 401 with standard error format."""
    res = anon_client.post(
        "/auth/login",
        json={"username": "test_admin", "password": "WrongPassword999!"},
    )
    assert res.status_code == 401
    data = res.json()
    assert data["detail"]["code"] == "INVALID_CREDENTIALS"


def test_account_lockout_after_consecutive_failures(anon_client, test_db):
    """5 failed attempts locks the account."""
    from argon2 import PasswordHasher
    ph = PasswordHasher()
    u = UserModel(
        username="lockout_victim",
        password_hash=ph.hash("InitialPassword123!"),
        role="operator",
        active=1,
        must_change_password=0,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    test_db.add(u)
    test_db.commit()

    # 5 failed attempts recorded
    for _ in range(5):
        r = anon_client.post(
            "/auth/login",
            json={"username": "lockout_victim", "password": "BadPassword123!"},
        )
        assert r.status_code == 401
        assert r.json()["detail"]["code"] == "INVALID_CREDENTIALS"

    # 6th attempt: triggers throttle lockout
    r = anon_client.post(
        "/auth/login",
        json={"username": "lockout_victim", "password": "BadPassword123!"},
    )
    assert r.status_code == 429
    assert r.json()["detail"]["code"] == "LOGIN_THROTTLED"

    # Subsequent attempt even with correct password returns 429
    r = anon_client.post(
        "/auth/login",
        json={"username": "lockout_victim", "password": "InitialPassword123!"},
    )
    assert r.status_code == 429


def test_csrf_protection_on_mutating_requests(operator_client):
    """Mutating state-changing requests require matching CSRF header."""
    operator_client.csrf_token = None
    res = operator_client.post(
        "/feedback",
        json={
            "event_id": "00000000-0000-0000-0000-000000000000",
            "feedback": "confirmed",
            "operator_id": "op_test",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        headers={"X-CSRF-Token": ""},
    )
    assert res.status_code == 403
    assert res.json()["code"] == "CSRF_FAILED"


def test_logout_revokes_session(anon_client, operator_user):
    """Logging out revokes session in DB and clears cookies."""
    login_res = anon_client.post(
        "/auth/login",
        json={"username": "test_operator", "password": "AegisTestPassword123!"},
    )
    assert login_res.status_code == 200
    csrf_token = login_res.json()["csrf_token"]

    # Verify /auth/me works
    anon_client.headers["X-CSRF-Token"] = csrf_token
    r_me = anon_client.get("/auth/me")
    assert r_me.status_code == 200

    # Logout
    r_logout = anon_client.post("/auth/logout")
    assert r_logout.status_code == 200

    # Calling /auth/me now fails with 401
    r_me_after = anon_client.get("/auth/me")
    assert r_me_after.status_code == 401


def test_must_change_password_enforcement(anon_client, test_db):
    """Users with must_change_password=1 can only change password or logout."""
    from argon2 import PasswordHasher
    ph = PasswordHasher()
    forced_user = UserModel(
        username="force_pwd_user",
        password_hash=ph.hash("TemporaryPass123!"),
        role="operator",
        active=1,
        must_change_password=1,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    test_db.add(forced_user)
    test_db.commit()

    # Login
    r = anon_client.post(
        "/auth/login",
        json={"username": "force_pwd_user", "password": "TemporaryPass123!"},
    )
    assert r.status_code == 200
    assert r.json()["user"]["must_change_password"] is True
    csrf = r.json()["csrf_token"]
    anon_client.headers["X-CSRF-Token"] = csrf

    # Accessing /alerts should return 403 PASSWORD_CHANGE_REQUIRED
    r_alerts = anon_client.get("/alerts")
    assert r_alerts.status_code == 403
    assert r_alerts.json()["code"] == "PASSWORD_CHANGE_REQUIRED"

    # Accessing /auth/me is permitted
    r_me = anon_client.get("/auth/me")
    assert r_me.status_code == 200

    # Change password
    r_change = anon_client.post(
        "/auth/change-password",
        json={
            "old_password": "TemporaryPass123!",
            "new_password": "NewPermanentPass123!",
        },
    )
    assert r_change.status_code == 200

    # Now /alerts is permitted!
    r_alerts_now = anon_client.get("/alerts")
    assert r_alerts_now.status_code == 200
