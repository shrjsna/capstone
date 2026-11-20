"""
cloud/backend/users_admin.py
============================
User and Edge-Key Administration Endpoints for the AEGIS Industrial Safety System.
Enforces atomic last-admin protection, secure password initialization, and edge credential management.
"""

import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from argon2 import PasswordHasher
from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from cloud.backend.audit import record_audit
from cloud.backend.auth import (
    AuthenticatedIdentity,
    get_client_ip,
    get_current_identity,
    hash_token,
    validate_password_strength,
)
from cloud.backend.database import get_db
from cloud.backend.models import EdgeKeyModel, SessionModel, UserModel

logger = logging.getLogger("aegis.users_admin")
ph = PasswordHasher()

admin_users_router = APIRouter(prefix="/admin", tags=["User Administration"])


# ---------------------------------------------------------------------------
# Request & Response Schemas
# ---------------------------------------------------------------------------

class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)
    role: str = Field(..., pattern="^(admin|operator)$")
    temp_password: str = Field(..., min_length=12, max_length=128)


class UpdateUserRequest(BaseModel):
    role: Optional[str] = Field(None, pattern="^(admin|operator)$")
    active: Optional[bool] = None


class ResetPasswordRequest(BaseModel):
    temp_password: str = Field(..., min_length=12, max_length=128)


class CreateEdgeKeyRequest(BaseModel):
    label: str = Field(..., min_length=1, max_length=64)


# ---------------------------------------------------------------------------
# User Administration Endpoints
# ---------------------------------------------------------------------------

@admin_users_router.get("/users")
def list_users(
    db: Session = Depends(get_db),
):
    """
    GET /admin/users — List registered user accounts (never returns password hashes).
    Admin-only.
    """
    users = db.query(UserModel).order_by(UserModel.id).all()
    return [
        {
            "id": u.id,
            "username": u.username,
            "role": u.role,
            "active": bool(u.active),
            "must_change_password": bool(u.must_change_password),
            "created_at": u.created_at,
            "created_by": u.created_by,
            "last_login_at": u.last_login_at,
        }
        for u in users
    ]


@admin_users_router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(
    req: CreateUserRequest,
    request: Request,
    db: Session = Depends(get_db),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
):
    """
    POST /admin/users — Create a new user account. Forces must_change_password=1.
    Admin-only.
    """
    username = req.username.strip()
    validate_password_strength(req.temp_password, username)

    # Check for existing user (case-insensitive)
    existing = db.query(UserModel).filter(func.lower(UserModel.username) == username.lower()).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{username}' is already in use.",
        )

    actor = identity.actor if identity else "admin"
    now = datetime.now(timezone.utc).isoformat()
    new_user = UserModel(
        username=username,
        password_hash=ph.hash(req.temp_password),
        role=req.role,
        active=1,
        must_change_password=1,
        created_at=now,
        created_by=actor,
        last_login_at=None,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    record_audit(
        db=db,
        action="user.create",
        outcome="success",
        actor=actor,
        role=identity.role if identity else "admin",
        target=f"user:{new_user.id}:{new_user.username}",
        client_addr=get_client_ip(request),
        detail=f"Created user '{username}' with role '{req.role}'.",
    )

    return {
        "status": "ok",
        "id": new_user.id,
        "username": new_user.username,
        "role": new_user.role,
        "active": bool(new_user.active),
        "must_change_password": bool(new_user.must_change_password),
    }


@admin_users_router.patch("/users/{id}")
def update_user(
    id: int,
    req: UpdateUserRequest,
    request: Request,
    db: Session = Depends(get_db),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
):
    """
    PATCH /admin/users/{id} — Update user role or active status.
    Enforces atomic last-admin protection.
    Admin-only.
    """
    user = db.query(UserModel).filter(UserModel.id == id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {user_id} not found.",
        )

    actor = identity.actor if identity else "admin"

    # LAST ADMIN PROTECTION:
    # If the user is currently an active admin, and the change demotes or disables them:
    demoting = req.role is not None and req.role != "admin" and user.role == "admin"
    disabling = req.active is False and bool(user.active) and user.role == "admin"

    if demoting or disabling:
        # Count remaining active admins within the same transaction
        active_admins_count = (
            db.query(UserModel)
            .filter(UserModel.role == "admin", UserModel.active == 1)
            .count()
        )
        if active_admins_count <= 1:
            record_audit(
                db=db,
                action="user.disable" if disabling else "user.role_change",
                outcome="denied",
                actor=actor,
                role=identity.role if identity else "admin",
                target=f"user:{user.id}:{user.username}",
                client_addr=get_client_ip(request),
                detail="Denied: cannot demote or disable the last active administrator.",
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot demote or disable the last active administrator.",
            )

    action_name = "user.role_change"
    if req.role is not None:
        user.role = req.role

    if req.active is not None:
        user.active = 1 if req.active else 0
        action_name = "user.enable" if req.active else "user.disable"
        # If disabled, revoke all active sessions immediately
        if not req.active:
            db.query(SessionModel).filter(SessionModel.user_id == user.id).update({"revoked": 1})

    db.commit()

    record_audit(
        db=db,
        action=action_name,
        outcome="success",
        actor=actor,
        role=identity.role if identity else "admin",
        target=f"user:{user.id}:{user.username}",
        client_addr=get_client_ip(request),
        detail=f"Updated user ID {user.id}: role={user.role}, active={bool(user.active)}.",
    )

    return {
        "status": "ok",
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "active": bool(user.active),
    }


@admin_users_router.post("/users/{id}/reset-password")
def reset_password(
    id: int,
    req: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
):
    """
    POST /admin/users/{id}/reset-password — Reset password, require change on next login,
    and revoke all open sessions for this user.
    Admin-only.
    """
    user = db.query(UserModel).filter(UserModel.id == id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with ID {id} not found.",
        )

    validate_password_strength(req.temp_password, user.username)

    user.password_hash = ph.hash(req.temp_password)
    user.must_change_password = 1

    # Revoke all current sessions for this user
    db.query(SessionModel).filter(SessionModel.user_id == user.id).update({"revoked": 1})
    db.commit()

    actor = identity.actor if identity else "admin"
    record_audit(
        db=db,
        action="user.password_reset",
        outcome="success",
        actor=actor,
        role=identity.role if identity else "admin",
        target=f"user:{user.id}:{user.username}",
        client_addr=get_client_ip(request),
        detail=f"Reset password for user '{user.username}'. Sessions revoked.",
    )

    return {"status": "ok", "message": f"Password reset successfully for user '{user.username}'."}


# ---------------------------------------------------------------------------
# Edge Key Management Endpoints
# ---------------------------------------------------------------------------

@admin_users_router.get("/edge-keys")
def list_edge_keys(
    db: Session = Depends(get_db),
):
    """
    GET /admin/edge-keys — List edge credentials (prefix and label only; secrets are never stored).
    Admin-only.
    """
    keys = db.query(EdgeKeyModel).order_by(EdgeKeyModel.id).all()
    return [
        {
            "id": k.id,
            "key_prefix": k.key_prefix,
            "label": k.label,
            "created_at": k.created_at,
            "created_by": k.created_by,
            "active": bool(k.active),
            "revoked_at": k.revoked_at,
            "last_used_at": k.last_used_at,
        }
        for k in keys
    ]


@admin_users_router.post("/edge-keys", status_code=status.HTTP_201_CREATED)
def create_edge_key(
    req: CreateEdgeKeyRequest,
    request: Request,
    db: Session = Depends(get_db),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
):
    """
    POST /admin/edge-keys — Issue a new edge API key.
    The full key is returned ONCE in the response; only the prefix and cryptographic hash are stored.
    Admin-only.
    """
    prefix = secrets.token_hex(4)
    secret = secrets.token_urlsafe(32)
    full_key = f"aegis_edge_{prefix}_{secret}"
    key_h = hash_token(full_key)

    actor = identity.actor if identity else "admin"
    now = datetime.now(timezone.utc).isoformat()

    entry = EdgeKeyModel(
        key_prefix=prefix,
        key_hash=key_h,
        label=req.label.strip(),
        created_at=now,
        created_by=actor,
        active=1,
        revoked_at=None,
        last_used_at=None,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    record_audit(
        db=db,
        action="edge_key.create",
        outcome="success",
        actor=actor,
        role=identity.role if identity else "admin",
        target=f"edge_key:{entry.key_prefix}:{entry.label}",
        client_addr=get_client_ip(request),
        detail=f"Issued edge key '{entry.label}' with prefix '{entry.key_prefix}'.",
    )

    return {
        "status": "ok",
        "key_prefix": entry.key_prefix,
        "label": entry.label,
        "api_key": full_key,  # Shown ONCE upon creation
        "warning": "Store this key safely; it cannot be retrieved again."
    }


@admin_users_router.post("/edge-keys/{prefix}/revoke")
def revoke_edge_key(
    prefix: str,
    request: Request,
    db: Session = Depends(get_db),
    identity: AuthenticatedIdentity = Depends(get_current_identity),
):
    """
    POST /admin/edge-keys/{prefix}/revoke — Revoke an edge API key immediately.
    Admin-only.
    """
    key_entry = db.query(EdgeKeyModel).filter(EdgeKeyModel.key_prefix == prefix).first()
    if not key_entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Edge key with prefix '{prefix}' not found.",
        )

    key_entry.active = 0
    key_entry.revoked_at = datetime.now(timezone.utc).isoformat()
    db.commit()

    actor = identity.actor if identity else "admin"
    record_audit(
        db=db,
        action="edge_key.revoke",
        outcome="success",
        actor=actor,
        role=identity.role if identity else "admin",
        target=f"edge_key:{key_entry.key_prefix}:{key_entry.label}",
        client_addr=get_client_ip(request),
        detail=f"Revoked edge key prefix '{prefix}'.",
    )

    return {"status": "ok", "message": f"Edge key prefix '{prefix}' revoked immediately."}
