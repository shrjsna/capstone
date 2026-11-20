"""
cloud/backend/auth.py
=====================
Authentication engine for the AEGIS Industrial Safety System:
- Argon2id password hashing and constant-time verification.
- Session cookie management with idle and absolute expiration.
- Anti-CSRF protection via double-submit token verification.
- Brute-force login throttling with per-IP and per-user lockouts.
- Immediate permission synchronization on user row modifications.
- Edge key verification and in-memory internal stream worker credential.
"""

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from cloud.backend.audit import record_audit
from cloud.backend.config import get_settings
from cloud.backend.database import get_db
from cloud.backend.models import AuditLogModel, EdgeKeyModel, LoginAttemptModel, SessionModel, UserModel

logger = logging.getLogger("aegis.auth")

ph = PasswordHasher()
# Pre-computed dummy hash for timing-attack mitigation on non-existent usernames
DUMMY_HASH = ph.hash("AegisDummyPassword123!")

# Internal stream worker credential generated once in-memory per process lifecycle
INTERNAL_STREAM_KEY = f"aegis_edge_internal_{secrets.token_urlsafe(32)}"

SESSION_COOKIE_NAME = "aegis_session"

auth_router = APIRouter(prefix="/auth", tags=["Authentication"])


# ---------------------------------------------------------------------------
# Models & Request Schemas
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=1, max_length=128)


# ---------------------------------------------------------------------------
# Client Address & Timing Helpers
# ---------------------------------------------------------------------------

def get_client_ip(request: Request) -> str:
    """Extract client IP, honoring X-Forwarded-For only for trusted proxies."""
    settings = get_settings()
    direct_ip = request.client.host if request.client else "127.0.0.1"

    if direct_ip in settings.TRUSTED_PROXIES:
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            return xff.split(",")[0].strip()

    return direct_ip


def validate_password_strength(password: str, username: str) -> None:
    """Validate password against complexity and length rules."""
    settings = get_settings()
    if len(password) < settings.MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password must be at least {settings.MIN_PASSWORD_LENGTH} characters in length.",
        )
    if len(password) > 128:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must not exceed 128 characters.",
        )
    if not password.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password cannot consist solely of whitespace.",
        )
    if not any(c.isupper() for c in password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one uppercase letter.",
        )
    if not any(c.islower() for c in password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one lowercase letter.",
        )
    if not any(c.isdigit() for c in password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one digit.",
        )
    if not any(not c.isalnum() for c in password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one symbol.",
        )
    if username and username.strip().lower() in password.strip().lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password cannot contain the username.",
        )


# ---------------------------------------------------------------------------
# Throttling
# ---------------------------------------------------------------------------

def check_login_throttling(db: Session, username: str, client_ip: str) -> None:
    """
    Count recent failures for (username, client_ip) and client_ip.
    Raises HTTP 429 if threshold exceeded.
    """
    settings = get_settings()
    window_start = (datetime.now(timezone.utc) - timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)).isoformat()

    # Failures by username or by IP within window
    failures_count = (
        db.query(LoginAttemptModel)
        .filter(
            LoginAttemptModel.attempted_at >= window_start,
            LoginAttemptModel.success == 0,
            (LoginAttemptModel.username == username.lower()) | (LoginAttemptModel.client_addr == client_ip),
        )
        .count()
    )

    if failures_count >= settings.LOGIN_MAX_FAILURES:
        retry_after = settings.LOGIN_LOCKOUT_MINUTES * 60
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "LOGIN_THROTTLED",
                "message": f"Too many failed login attempts. Please wait {settings.LOGIN_LOCKOUT_MINUTES} minutes before retrying."
            },
            headers={"Retry-After": str(retry_after)},
        )


def record_login_attempt(db: Session, username: str, client_ip: str, success: bool) -> None:
    """Log an authentication attempt for rate limiting."""
    attempt = LoginAttemptModel(
        username=username.lower() if username else None,
        client_addr=client_ip,
        attempted_at=datetime.now(timezone.utc).isoformat(),
        success=1 if success else 0,
    )
    db.add(attempt)
    db.commit()


# ---------------------------------------------------------------------------
# Credential Resolution & Session Management
# ---------------------------------------------------------------------------

class AuthenticatedIdentity:
    """Represents the verified caller identity for the current request."""

    def __init__(
        self,
        actor: str,
        role: str,
        auth_type: str,  # "session" | "edge"
        user: Optional[UserModel] = None,
        session: Optional[SessionModel] = None,
        edge_key: Optional[EdgeKeyModel] = None,
    ):
        self.actor = actor
        self.role = role
        self.auth_type = auth_type
        self.user = user
        self.session = session
        self.edge_key = edge_key

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_operator(self) -> bool:
        return self.role == "operator"

    @property
    def is_edge(self) -> bool:
        return self.role == "edge"

    @property
    def must_change_password(self) -> bool:
        return bool(self.user and self.user.must_change_password)


def hash_token(token: str) -> str:
    """Secure SHA-256 hash for lookup of session and API tokens."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def resolve_edge_key(db: Session, key_str: str) -> Optional[AuthenticatedIdentity]:
    """Verify external or internal in-memory edge key."""
    # 1. In-memory internal stream credential
    if hmac.compare_digest(key_str, INTERNAL_STREAM_KEY):
        return AuthenticatedIdentity(
            actor="internal-stream",
            role="edge",
            auth_type="edge",
        )

    # 2. Database-backed edge keys
    if not key_str.startswith("aegis_edge_"):
        return None

    parts = key_str.split("_")
    if len(parts) < 4:
        return None

    prefix = parts[2]
    expected_hash = hash_token(key_str)

    edge_row = db.query(EdgeKeyModel).filter(
        EdgeKeyModel.key_prefix == prefix,
        EdgeKeyModel.active == 1,
        EdgeKeyModel.revoked_at.is_(None),
    ).first()

    if not edge_row:
        return None

    if hmac.compare_digest(edge_row.key_hash, expected_hash):
        edge_row.last_used_at = datetime.now(timezone.utc).isoformat()
        db.commit()
        return AuthenticatedIdentity(
            actor=f"edge:{edge_row.label}",
            role="edge",
            auth_type="edge",
            edge_key=edge_row,
        )

    return None


def resolve_session_cookie(
    db: Session,
    cookie_token: str,
    client_ip: str,
    user_agent: Optional[str] = None,
) -> Optional[AuthenticatedIdentity]:
    """Verify session cookie, check idle and absolute timeouts, re-read user state."""
    settings = get_settings()
    t_hash = hash_token(cookie_token)

    session_row = db.query(SessionModel).filter(
        SessionModel.token_hash == t_hash,
        SessionModel.revoked == 0,
    ).first()

    if not session_row:
        return None

    now = datetime.now(timezone.utc)

    # 1. Check absolute expiration
    try:
        expires_at = datetime.fromisoformat(session_row.expires_at)
        if now > expires_at:
            session_row.revoked = 1
            db.commit()
            return None
    except Exception:
        return None

    # 2. Check idle timeout
    try:
        last_seen = datetime.fromisoformat(session_row.last_seen_at)
        if now - last_seen > timedelta(minutes=settings.SESSION_IDLE_MIN):
            session_row.revoked = 1
            db.commit()
            return None
    except Exception:
        return None

    # 3. Re-read user row dynamically (immediate synchronization)
    user_row = db.query(UserModel).filter(UserModel.id == session_row.user_id).first()
    if not user_row or not user_row.active:
        return None

    # 4. Throttle updating last_seen_at (at most once every 60 seconds)
    if (now - last_seen).total_seconds() > 60:
        session_row.last_seen_at = now.isoformat()
        session_row.client_addr = client_ip
        if user_agent:
            session_row.user_agent = user_agent[:256]
        db.commit()

    return AuthenticatedIdentity(
        actor=user_row.username,
        role=user_row.role,
        auth_type="session",
        user=user_row,
        session=session_row,
    )


def get_current_identity(
    request: Request,
    db: Session = Depends(get_db),
    aegis_session: Optional[str] = Cookie(None, alias=SESSION_COOKIE_NAME),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> Optional[AuthenticatedIdentity]:
    """
    Central dependency resolving the caller credential.
    Strictly forbids presenting both a session cookie and an edge key simultaneously.
    """
    client_ip = get_client_ip(request)

    # Reject ambiguous requests presenting both cookie and API key
    if aegis_session and x_api_key:
        record_audit(
            db=db,
            action="access.denied.403",
            outcome="denied",
            actor="unknown",
            client_addr=client_ip,
            detail="Ambiguous request presenting both session cookie and X-API-Key.",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "AMBIGUOUS_CREDENTIALS", "message": "Cannot present both session cookie and API key."},
        )

    # Edge Key authentication
    if x_api_key:
        identity = resolve_edge_key(db, x_api_key.strip())
        if not identity:
            record_audit(
                db=db,
                action="access.denied.401",
                outcome="denied",
                actor="unknown_edge",
                client_addr=client_ip,
                detail="Invalid or revoked edge key.",
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "AUTH_REQUIRED", "message": "Invalid or revoked edge key."},
            )
        return identity

    # Session cookie authentication
    if aegis_session:
        user_agent = request.headers.get("User-Agent")
        identity = resolve_session_cookie(db, aegis_session, client_ip, user_agent)
        if not identity:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"code": "SESSION_EXPIRED", "message": "Session expired or invalid. Please sign in again."},
            )

        # Anti-CSRF verification for state-changing HTTP methods
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            csrf_header = request.headers.get("X-CSRF-Token")
            if not csrf_header or not hmac.compare_digest(csrf_header, identity.session.csrf_token):
                record_audit(
                    db=db,
                    action="access.denied.403",
                    outcome="denied",
                    actor=identity.actor,
                    role=identity.role,
                    client_addr=client_ip,
                    detail=f"CSRF token validation failed on {request.method} {request.url.path}.",
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"code": "CSRF_FAILED", "message": "Invalid or missing CSRF token."},
                )

        return identity

    return None


# ---------------------------------------------------------------------------
# Auth Endpoints
# ---------------------------------------------------------------------------

@auth_router.post("/login", status_code=status.HTTP_200_OK)
def login(
    req: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    POST /auth/login — Authenticate user, throttle attempts, issue session cookie and CSRF token.
    """
    client_ip = get_client_ip(request)
    username = req.username.strip()

    # 1. Throttling check
    check_login_throttling(db, username, client_ip)

    user = db.query(UserModel).filter(func.lower(UserModel.username) == username.lower()).first()

    # 2. Timing-safe verification
    authenticated = False
    if user and user.active:
        try:
            authenticated = ph.verify(user.password_hash, req.password)
        except VerifyMismatchError:
            authenticated = False
    else:
        # Perform dummy verify to equalize response timing
        try:
            ph.verify(DUMMY_HASH, req.password)
        except VerifyMismatchError:
            pass
        authenticated = False

    if not authenticated:
        record_login_attempt(db, username, client_ip, success=False)
        record_audit(
            db=db,
            action="auth.login.failure",
            outcome="denied",
            actor=username,
            client_addr=client_ip,
            detail="Failed login credentials provided.",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_CREDENTIALS", "message": "Invalid username or password."},
        )

    # 3. Record successful attempt & update user last_login
    record_login_attempt(db, username, client_ip, success=True)
    user.last_login_at = datetime.now(timezone.utc).isoformat()

    # 4. Create new random session token & CSRF token
    settings = get_settings()
    raw_token = secrets.token_urlsafe(32)
    token_h = hash_token(raw_token)
    csrf_token = secrets.token_urlsafe(32)

    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(hours=settings.SESSION_ABSOLUTE_HOURS)).isoformat()

    user_agent = request.headers.get("User-Agent")
    new_session = SessionModel(
        token_hash=token_h,
        user_id=user.id,
        csrf_token=csrf_token,
        created_at=now.isoformat(),
        last_seen_at=now.isoformat(),
        expires_at=expires_at,
        revoked=0,
        client_addr=client_ip,
        user_agent=user_agent[:256] if user_agent else None,
    )
    db.add(new_session)
    db.commit()

    # 5. Set HttpOnly session cookie
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_token,
        httponly=True,
        samesite="strict",
        path="/",
        secure=settings.COOKIE_SECURE,
        max_age=settings.SESSION_ABSOLUTE_HOURS * 3600,
    )

    record_audit(
        db=db,
        action="auth.login.success",
        outcome="success",
        actor=user.username,
        role=user.role,
        client_addr=client_ip,
        detail=f"User signed in successfully (role: {user.role}).",
    )

    return {
        "status": "ok",
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "must_change_password": bool(user.must_change_password),
        },
        "csrf_token": csrf_token,
    }


@auth_router.post("/logout", status_code=status.HTTP_200_OK)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
):
    """
    POST /auth/logout — Invalidate current session on server-side and clear client cookie.
    """
    if not identity or identity.auth_type != "session":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_REQUIRED", "message": "Active session required to log out."},
        )

    if identity.session:
        identity.session.revoked = 1
        db.commit()

    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="strict",
    )

    record_audit(
        db=db,
        action="auth.logout",
        outcome="success",
        actor=identity.actor,
        role=identity.role,
        client_addr=get_client_ip(request),
        detail="User signed out successfully.",
    )

    return {"status": "ok", "message": "Signed out successfully."}


@auth_router.get("/me", status_code=status.HTTP_200_OK)
def me(
    identity: AuthenticatedIdentity = Depends(get_current_identity),
):
    """
    GET /auth/me — Return current authenticated user identity and active CSRF token.
    """
    if not identity:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_REQUIRED", "message": "Sign-in required."},
        )

    if identity.auth_type == "session" and identity.user:
        u_dict = {
            "id": identity.user.id,
            "username": identity.user.username,
            "role": identity.user.role,
            "must_change_password": bool(identity.user.must_change_password),
        }
        return {
            "authenticated": True,
            "type": "user",
            "user": u_dict,
            "username": identity.user.username,
            "role": identity.user.role,
            "must_change_password": bool(identity.user.must_change_password),
            "csrf_token": identity.session.csrf_token if identity.session else None,
        }
    else:
        return {
            "authenticated": True,
            "type": "edge",
            "actor": identity.actor,
            "role": identity.role,
            "csrf_token": None,
        }


@auth_router.post("/change-password", status_code=status.HTTP_200_OK)
def change_password(
    req: ChangePasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
):
    """
    POST /auth/change-password — Update password for the currently signed-in user.
    Clears must_change_password flag upon successful update.
    """
    if not identity or identity.auth_type != "session" or not identity.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "AUTH_REQUIRED", "message": "Signed-in user session required."},
        )

    user = identity.user

    # Verify old password
    try:
        ph.verify(user.password_hash, req.old_password)
    except VerifyMismatchError:
        record_audit(
            db=db,
            action="auth.password.change",
            outcome="denied",
            actor=user.username,
            role=user.role,
            client_addr=get_client_ip(request),
            detail="Password change denied: old password incorrect.",
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )

    # Validate new password strength
    validate_password_strength(req.new_password, user.username)

    # Update password and clear must_change_password
    user.password_hash = ph.hash(req.new_password)
    user.must_change_password = 0
    db.commit()

    record_audit(
        db=db,
        action="auth.password.change",
        outcome="success",
        actor=user.username,
        role=user.role,
        client_addr=get_client_ip(request),
        detail="Password changed successfully.",
    )

    return {"status": "ok", "message": "Password changed successfully."}
