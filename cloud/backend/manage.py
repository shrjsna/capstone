"""
cloud/backend/manage.py
=======================
Administrative CLI tool for AEGIS Safety System:
- Bootstrap first administrator account (no default credentials).
- Manage user accounts, role assignments, and password resets.
- Issue and revoke non-human edge API keys.
- Emergency recovery interface if all administrators are locked out.
"""

import argparse
import getpass
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from argon2 import PasswordHasher
from sqlalchemy import func

# Ensure repo root is on sys.path
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cloud.backend.auth import hash_token, validate_password_strength
from cloud.backend.config import get_settings
from cloud.backend.database import SessionLocal, init_db
from cloud.backend.models import EdgeKeyModel, SessionModel, UserModel

ph = PasswordHasher()


def cmd_create_admin(args):
    """Interactive command to create an administrator account."""
    init_db()
    db = SessionLocal()
    try:
        print("\n--- AEGIS Administrator Creation ---")
        username = input("Enter admin username: ").strip()
        if not username:
            print("Error: Username cannot be empty.")
            sys.exit(1)

        existing = db.query(UserModel).filter(func.lower(UserModel.username) == username.lower()).first()
        if existing:
            print(f"Error: User '{username}' already exists.")
            sys.exit(1)

        pwd = getpass.getpass("Enter admin password: ")
        confirm_pwd = getpass.getpass("Confirm admin password: ")
        if pwd != confirm_pwd:
            print("Error: Passwords do not match.")
            sys.exit(1)

        try:
            validate_password_strength(pwd, username)
        except Exception as exc:
            print(f"Error: {exc}")
            sys.exit(1)

        now = datetime.now(timezone.utc).isoformat()
        admin = UserModel(
            username=username,
            password_hash=ph.hash(pwd),
            role="admin",
            active=1,
            must_change_password=0,
            created_at=now,
            created_by="CLI:manage",
            last_login_at=None,
        )
        db.add(admin)
        db.commit()
        print(f"\n[+] Administrator '{username}' created successfully!")
    finally:
        db.close()


def cmd_create_user(args):
    """Command to create an operator or admin user."""
    init_db()
    db = SessionLocal()
    try:
        username = args.username.strip()
        role = args.role.strip().lower()
        if role not in ("admin", "operator"):
            print("Error: Role must be either 'admin' or 'operator'.")
            sys.exit(1)

        existing = db.query(UserModel).filter(func.lower(UserModel.username) == username.lower()).first()
        if existing:
            print(f"Error: User '{username}' already exists.")
            sys.exit(1)

        if args.password:
            pwd = args.password
        else:
            pwd = getpass.getpass(f"Enter password for {username}: ")
            confirm = getpass.getpass("Confirm password: ")
            if pwd != confirm:
                print("Error: Passwords do not match.")
                sys.exit(1)

        try:
            validate_password_strength(pwd, username)
        except Exception as exc:
            print(f"Error: {exc}")
            sys.exit(1)

        now = datetime.now(timezone.utc).isoformat()
        user = UserModel(
            username=username,
            password_hash=ph.hash(pwd),
            role=role,
            active=1,
            must_change_password=1 if args.must_change else 0,
            created_at=now,
            created_by="CLI:manage",
        )
        db.add(user)
        db.commit()
        print(f"[+] User '{username}' created with role '{role}' (must_change_password={bool(user.must_change_password)}).")
    finally:
        db.close()


def cmd_list_users(args):
    """List all accounts without revealing passwords."""
    init_db()
    db = SessionLocal()
    try:
        users = db.query(UserModel).order_by(UserModel.id).all()
        print("\n" + "=" * 75)
        print(f"{'ID':<4} {'Username':<18} {'Role':<10} {'Active':<8} {'Must Change':<12} {'Created'}")
        print("-" * 75)
        for u in users:
            print(f"{u.id:<4} {u.username:<18} {u.role:<10} {str(bool(u.active)):<8} {str(bool(u.must_change_password)):<12} {u.created_at[:19]}")
        print("=" * 75 + "\n")
    finally:
        db.close()


def cmd_disable_user(args):
    """Disable a user account with last-admin protection."""
    init_db()
    db = SessionLocal()
    try:
        user = db.query(UserModel).filter(func.lower(UserModel.username) == args.username.strip().lower()).first()
        if not user:
            print(f"Error: User '{args.username}' not found.")
            sys.exit(1)

        if user.role == "admin" and user.active == 1:
            active_admins = db.query(UserModel).filter(UserModel.role == "admin", UserModel.active == 1).count()
            if active_admins <= 1:
                print("Error: Cannot disable the last active administrator.")
                sys.exit(1)

        user.active = 0
        db.query(SessionModel).filter(SessionModel.user_id == user.id).update({"revoked": 1})
        db.commit()
        print(f"[+] User '{user.username}' disabled successfully. All sessions revoked.")
    finally:
        db.close()


def cmd_reset_password(args):
    """Reset password for a user from CLI."""
    init_db()
    db = SessionLocal()
    try:
        user = db.query(UserModel).filter(func.lower(UserModel.username) == args.username.strip().lower()).first()
        if not user:
            print(f"Error: User '{args.username}' not found.")
            sys.exit(1)

        pwd = getpass.getpass(f"Enter new password for {user.username}: ")
        confirm = getpass.getpass("Confirm new password: ")
        if pwd != confirm:
            print("Error: Passwords do not match.")
            sys.exit(1)

        try:
            validate_password_strength(pwd, user.username)
        except Exception as exc:
            print(f"Error: {exc}")
            sys.exit(1)

        user.password_hash = ph.hash(pwd)
        user.must_change_password = 1
        db.query(SessionModel).filter(SessionModel.user_id == user.id).update({"revoked": 1})
        db.commit()
        print(f"[+] Password reset for '{user.username}'. Sessions revoked; must change password on next sign-in.")
    finally:
        db.close()


def cmd_create_edge_key(args):
    """Issue a new edge API key and display once to terminal."""
    init_db()
    db = SessionLocal()
    try:
        label = args.label.strip()
        prefix = secrets.token_hex(4)
        secret = secrets.token_urlsafe(32)
        full_key = f"aegis_edge_{prefix}_{secret}"
        key_h = hash_token(full_key)

        now = datetime.now(timezone.utc).isoformat()
        entry = EdgeKeyModel(
            key_prefix=prefix,
            key_hash=key_h,
            label=label,
            created_at=now,
            created_by="CLI:manage",
            active=1,
        )
        db.add(entry)
        db.commit()

        print("\n" + "=" * 70)
        print("  NEW EDGE API KEY CREATED")
        print("=" * 70)
        print(f"  Label:   {label}")
        print(f"  Prefix:  {prefix}")
        print(f"  API Key: {full_key}")
        print("-" * 70)
        print("  IMPORTANT: Copy this key now. It is shown ONCE and never stored.")
        print("=" * 70 + "\n")
    finally:
        db.close()


def cmd_list_edge_keys(args):
    """List edge keys without exposing secrets."""
    init_db()
    db = SessionLocal()
    try:
        keys = db.query(EdgeKeyModel).order_by(EdgeKeyModel.id).all()
        print("\n" + "=" * 75)
        print(f"{'ID':<4} {'Prefix':<12} {'Label':<20} {'Active':<8} {'Created':<20} {'Last Used'}")
        print("-" * 75)
        for k in keys:
            last = k.last_used_at[:19] if k.last_used_at else "Never"
            print(f"{k.id:<4} {k.key_prefix:<12} {k.label:<20} {str(bool(k.active)):<8} {k.created_at[:19]:<20} {last}")
        print("=" * 75 + "\n")
    finally:
        db.close()


def cmd_revoke_edge_key(args):
    """Revoke an edge key by prefix."""
    init_db()
    db = SessionLocal()
    try:
        prefix = args.prefix.strip()
        key = db.query(EdgeKeyModel).filter(EdgeKeyModel.key_prefix == prefix).first()
        if not key:
            print(f"Error: Edge key with prefix '{prefix}' not found.")
            sys.exit(1)

        key.active = 0
        key.revoked_at = datetime.now(timezone.utc).isoformat()
        db.commit()
        print(f"[+] Edge key '{prefix}' ({key.label}) revoked successfully.")
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="AEGIS System Security & Administration CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create-admin
    subparsers.add_parser("create-admin", help="Create initial system administrator account")

    # create-user
    p_user = subparsers.add_parser("create-user", help="Create a user account")
    p_user.add_argument("username", help="Username")
    p_user.add_argument("--role", default="operator", choices=["admin", "operator"], help="Role (admin/operator)")
    p_user.add_argument("--password", help="Initial password (prompted if omitted)")
    p_user.add_argument("--must-change", action="store_true", help="Force password change on next login")

    # list-users
    subparsers.add_parser("list-users", help="List registered accounts")

    # disable-user
    p_dis = subparsers.add_parser("disable-user", help="Disable a user account")
    p_dis.add_argument("username", help="Username to disable")

    # reset-password
    p_reset = subparsers.add_parser("reset-password", help="Reset password for an existing user")
    p_reset.add_argument("username", help="Username to reset")

    # create-edge-key
    p_key = subparsers.add_parser("create-edge-key", help="Generate a non-human edge producer API key")
    p_key.add_argument("--label", required=True, help="Descriptive label (e.g. cam_line_01)")

    # list-edge-keys
    subparsers.add_parser("list-edge-keys", help="List active edge credentials")

    # revoke-edge-key
    p_rev = subparsers.add_parser("revoke-edge-key", help="Revoke edge credential by prefix")
    p_rev.add_argument("prefix", help="Key prefix to revoke")

    args = parser.parse_args()

    commands = {
        "create-admin": cmd_create_admin,
        "create-user": cmd_create_user,
        "list-users": cmd_list_users,
        "disable-user": cmd_disable_user,
        "reset-password": cmd_reset_password,
        "create-edge-key": cmd_create_edge_key,
        "list-edge-keys": cmd_list_edge_keys,
        "revoke-edge-key": cmd_revoke_edge_key,
    }

    cmd_fn = commands.get(args.command)
    if cmd_fn:
        cmd_fn(args)


if __name__ == "__main__":
    main()

