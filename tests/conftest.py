"""
tests/conftest.py
=================
Shared pytest fixtures and test harness for the AEGIS Industrial Safety System.
Provides isolated, realistic authenticated clients (admin, operator, edge, anon)
backed by a clean temporary SQLite database.
"""

import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Add repo root to sys.path for test discovery
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cloud.backend.auth import hash_token, ph
from cloud.backend.database import get_db
from cloud.backend.main import app
from cloud.backend.models import (
    AuditLogModel,
    Base,
    EdgeKeyModel,
    EventModel,
    FeedbackModel,
    PolicyVersionModel,
    SessionModel,
    UserModel,
)

# Shared in-memory test database using StaticPool
TEST_DB_URL = "sqlite://"
test_engine = create_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


class AuthenticatedTestClient(TestClient):
    """
    Subclassed TestClient that automatically attaches session cookies,
    CSRF headers, or edge API keys to simulate authenticated roles.
    """

    def __init__(self, app, cookie_token=None, csrf_token=None, api_key=None, **kwargs):
        super().__init__(app, **kwargs)
        self.cookie_token = cookie_token
        self.csrf_token = csrf_token
        self.api_key = api_key
        if cookie_token:
            self.cookies.set("aegis_session", cookie_token)

    def request(self, method, url, **kwargs):
        headers = dict(kwargs.get("headers") or {})
        # Attach CSRF token on state-changing requests if not explicitly overridden
        if self.csrf_token and method.upper() in ("POST", "PUT", "PATCH", "DELETE"):
            if "X-CSRF-Token" not in headers:
                headers["X-CSRF-Token"] = self.csrf_token
        # Attach Edge API key if not explicitly overridden
        if self.api_key and "X-API-Key" not in headers:
            headers["X-API-Key"] = self.api_key
        kwargs["headers"] = headers
        return super().request(method, url, **kwargs)


@pytest.fixture(autouse=True)
def setup_test_db():
    """Build complete database schema on test_engine before every test."""
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_get_db

    # Create audit_log append-only triggers on test engine
    with test_engine.begin() as conn:
        from sqlalchemy import text
        conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS audit_log_no_update
            BEFORE UPDATE ON audit_log
            BEGIN
                SELECT RAISE(ABORT, 'audit_log is append-only: UPDATE rejected');
            END;
        """))
        conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS audit_log_no_delete
            BEFORE DELETE ON audit_log
            BEGIN
                SELECT RAISE(ABORT, 'audit_log is append-only: DELETE rejected');
            END;
        """))

    # Seed initial policy record
    db = TestingSessionLocal()
    if not db.query(PolicyVersionModel).first():
        seed_policy = PolicyVersionModel(
            policy_version="v1.0.0-mock",
            trained_at="2026-09-20T10:00:00Z",
            validation_score=0.915,
            previous_version="v0.9.0",
            deployed=True,
        )
        db.add(seed_policy)
        db.commit()
    db.close()

    yield

    Base.metadata.drop_all(bind=test_engine)


def _create_user_and_session(username: str, role: str) -> tuple[UserModel, str, str]:
    from cloud.backend.permissions import get_session_for_request
    db = get_session_for_request(app)
    try:
        user = db.query(UserModel).filter(UserModel.username == username).first()
        if not user:
            user = UserModel(
                username=username,
                password_hash=ph.hash("AegisTestPassword123!"),
                role=role,
                active=1,
                must_change_password=0,
                created_at=datetime.now(timezone.utc).isoformat(),
                created_by="test_setup",
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        raw_token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        session = SessionModel(
            token_hash=hash_token(raw_token),
            user_id=user.id,
            csrf_token=csrf_token,
            created_at=now.isoformat(),
            last_seen_at=now.isoformat(),
            expires_at=(now + timedelta(hours=12)).isoformat(),
            revoked=0,
            client_addr="testclient",
        )
        db.add(session)
        db.commit()
        return user, raw_token, csrf_token
    finally:
        db.close()


@pytest.fixture
def test_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def admin_user():
    user, _, _ = _create_user_and_session("test_admin", "admin")
    return user


@pytest.fixture
def operator_user():
    user, _, _ = _create_user_and_session("test_operator", "operator")
    return user


@pytest.fixture
def admin_client():
    _, token, csrf = _create_user_and_session("test_admin", "admin")
    return AuthenticatedTestClient(app, cookie_token=token, csrf_token=csrf)


@pytest.fixture
def operator_client():
    _, token, csrf = _create_user_and_session("test_operator", "operator")
    return AuthenticatedTestClient(app, cookie_token=token, csrf_token=csrf)


@pytest.fixture
def test_edge_key():
    from cloud.backend.permissions import get_session_for_request
    db = get_session_for_request(app)
    try:
        prefix = "tst1"
        secret = secrets.token_urlsafe(32)
        full_key = f"aegis_edge_{prefix}_{secret}"
        entry = EdgeKeyModel(
            key_prefix=prefix,
            key_hash=hash_token(full_key),
            label="test_camera_edge",
            created_at=datetime.now(timezone.utc).isoformat(),
            created_by="test_setup",
            active=1,
        )
        db.add(entry)
        db.commit()
        return full_key
    finally:
        db.close()


@pytest.fixture
def edge_client(test_edge_key):
    return AuthenticatedTestClient(app, api_key=test_edge_key)


@pytest.fixture
def anon_client():
    return AuthenticatedTestClient(app)


@pytest.fixture
def client(admin_client):
    """Default client fixture providing admin access for backwards-compatible test suites."""
    return admin_client
