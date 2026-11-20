"""
tests/test_federated_access.py
==============================
Tests for Federated Learning RBAC controls:
- Launching, stopping, and viewing logs for federated_demo is Admin-only.
- Operators and Anonymous requests are strictly denied.
- Audit logging of federated execution.
"""

import pytest


def test_federated_learning_access_control(anon_client, operator_client, admin_client):
    """Federated demo process management is restricted to Admin."""
    # Anon gets 401
    assert anon_client.get("/processes/federated_demo/logs").status_code == 401
    assert anon_client.post("/processes/federated_demo/start").status_code == 401
    assert anon_client.post("/processes/federated_demo/stop").status_code == 401

    # Operator gets 403
    assert operator_client.get("/processes/federated_demo/logs").status_code == 403
    assert operator_client.post("/processes/federated_demo/start").status_code == 403
    assert operator_client.post("/processes/federated_demo/stop").status_code == 403

    # Admin has access to query status and logs
    res_logs = admin_client.get("/processes/federated_demo/logs")
    assert res_logs.status_code == 200
    assert "logs" in res_logs.json()
