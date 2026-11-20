"""
tests/test_audit_log.py
=======================
Tests for the append-only audit trail:
- SQLite triggers preventing UPDATE and DELETE on audit_log.
- Access control for GET /admin/audit-log (Admin-only).
- Automatic logging of security and mutating actions.
- Audit log query pagination and filtering.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from cloud.backend.models import AuditLogModel
from cloud.backend.audit import record_audit


def test_audit_log_append_only_sqlite_triggers(test_db):
    """
    SQLite triggers must abort any UPDATE or DELETE operations on audit_log table.
    Enforces tamper resistance at the database layer.
    """
    # Insert audit entry
    entry = record_audit(
        db=test_db,
        action="test.action",
        outcome="success",
        actor="test_user",
        target="system",
        detail="Original audit entry",
    )
    test_db.commit()
    audit_id = entry.id

    # Attempting to UPDATE the audit record MUST raise IntegrityError / OperationalError
    with pytest.raises((IntegrityError, OperationalError), match="audit_log is append-only"):
        test_db.execute(
            text("UPDATE audit_log SET detail = 'tampered' WHERE id = :id"),
            {"id": audit_id},
        )
        test_db.commit()

    test_db.rollback()

    # Attempting to DELETE the audit record MUST raise IntegrityError / OperationalError
    with pytest.raises((IntegrityError, OperationalError), match="audit_log is append-only"):
        test_db.execute(
            text("DELETE FROM audit_log WHERE id = :id"),
            {"id": audit_id},
        )
        test_db.commit()

    test_db.rollback()


def test_audit_log_endpoint_access_control(anon_client, operator_client, admin_client):
    """GET /admin/audit-log is strictly restricted to Admin role."""
    # Anon gets 401
    res_anon = anon_client.get("/admin/audit-log")
    assert res_anon.status_code == 401

    # Operator gets 403
    res_op = operator_client.get("/admin/audit-log")
    assert res_op.status_code == 403

    # Admin succeeds
    res_admin = admin_client.get("/admin/audit-log?limit=10")
    assert res_admin.status_code == 200
    data = res_admin.json()
    assert "items" in data
    assert "total" in data
    assert isinstance(data["items"], list)
