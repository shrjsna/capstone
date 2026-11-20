"""
tests/test_users_admin.py
=========================
Tests for user management, edge key administration, and atomic last-admin protection:
- User CRUD operations and access control.
- Atomic last-admin protection (cannot demote or disable last admin).
- Password reset by admin forcing must_change_password.
- CLI user management operations in cloud/backend/manage.py.
"""

import pytest
from cloud.backend.models import UserModel


def test_list_users_rbac(operator_client, admin_client):
    """Only Admin can list users; Operator is denied with 403."""
    res_op = operator_client.get("/admin/users")
    assert res_op.status_code == 403

    res_admin = admin_client.get("/admin/users")
    assert res_admin.status_code == 200
    users = res_admin.json()
    assert isinstance(users, list)
    usernames = [u["username"] for u in users]
    assert "test_admin" in usernames


def test_create_user(admin_client, operator_client):
    """Admin can create new accounts; Operator cannot."""
    new_user_payload = {
        "username": "new_op_user",
        "role": "operator",
        "temp_password": "InitialTempPassword123!",
    }

    # Operator gets 403
    res_op = operator_client.post("/admin/users", json=new_user_payload)
    assert res_op.status_code == 403

    # Admin succeeds
    res_admin = admin_client.post("/admin/users", json=new_user_payload)
    assert res_admin.status_code in (200, 201)
    data = res_admin.json()
    assert data["username"] == "new_op_user"
    assert data["role"] == "operator"
    assert data["must_change_password"] is True


def test_last_admin_protection(admin_client, test_db):
    """System refuses to demote or disable the last remaining active Administrator."""
    admin_user = test_db.query(UserModel).filter(UserModel.username == "test_admin").first()
    assert admin_user is not None

    # Try deactivating the only admin
    res_deactivate = admin_client.patch(
        f"/admin/users/{admin_user.id}",
        json={"active": False},
    )
    assert res_deactivate.status_code == 409
    assert "last active administrator" in res_deactivate.json()["detail"].lower()

    # Try demoting the only admin to operator
    res_demote = admin_client.patch(
        f"/admin/users/{admin_user.id}",
        json={"role": "operator"},
    )
    assert res_demote.status_code == 409
    assert "last active administrator" in res_demote.json()["detail"].lower()


def test_admin_reset_user_password(admin_client, operator_user, test_db):
    """Admin can reset a user's password, which forces must_change_password."""
    op_user = test_db.query(UserModel).filter(UserModel.username == "test_operator").first()
    assert op_user is not None

    res = admin_client.post(
        f"/admin/users/{op_user.id}/reset-password",
        json={"temp_password": "NewTemporaryPassword123!"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ok"

    # Verify user record updated
    test_db.refresh(op_user)
    assert op_user.must_change_password == 1
