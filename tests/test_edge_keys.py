"""
tests/test_edge_keys.py
=======================
Tests for edge service keys and edge producer access control:
- Issuing, listing, and revoking edge keys.
- Edge key credential verification on POST /events.
- Rejection of edge keys on operator and admin endpoints (least privilege).
- Immediate invalidation on revocation.
"""

from datetime import datetime, timezone
import pytest
from cloud.backend.models import EdgeKeyModel


def test_edge_key_lifecycle(admin_client, operator_client, anon_client):
    """Admin can issue and revoke edge keys; secrets are never re-exposed."""
    # Operator cannot issue edge keys
    res_op = operator_client.post("/admin/edge-keys", json={"label": "edge-cam-01"})
    assert res_op.status_code == 403

    # Admin issues key
    res_issue = admin_client.post("/admin/edge-keys", json={"label": "edge-cam-01"})
    assert res_issue.status_code == 201
    issued_data = res_issue.json()
    assert issued_data["status"] == "ok"
    prefix = issued_data["key_prefix"]
    api_key = issued_data["api_key"]
    assert api_key.startswith(f"aegis_edge_{prefix}_")

    # List edge keys: secret is not shown
    res_list = admin_client.get("/admin/edge-keys")
    assert res_list.status_code == 200
    keys = res_list.json()
    assert any(k["key_prefix"] == prefix for k in keys)
    for k in keys:
        assert "api_key" not in k
        assert "secret" not in k

    # Use edge key to submit detection event (POST /events)
    event_payload = {
        "camera_id": "cam_edge_1",
        "zone_id": "zone_1",
        "event_type": "ppe_violation",
        "class": "no_helmet",
        "confidence": 0.90,
        "tracked_id": "tr_edge_99",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "frame_count_triggered": 5,
        "clip_captured": False,
    }
    res_event = anon_client.post(
        "/events",
        json=event_payload,
        headers={"X-API-Key": api_key},
    )
    assert res_event.status_code == 201

    # Edge key CANNOT access operator or admin routes
    res_alerts = anon_client.get("/alerts", headers={"X-API-Key": api_key})
    assert res_alerts.status_code == 403

    res_stream = anon_client.post("/stream/start", json={"source": "0"}, headers={"X-API-Key": api_key})
    assert res_stream.status_code == 403

    # Revoke edge key
    res_revoke = admin_client.post(f"/admin/edge-keys/{prefix}/revoke")
    assert res_revoke.status_code == 200

    # Submitting with revoked edge key immediately fails with 401
    res_revoked_event = anon_client.post(
        "/events",
        json=event_payload,
        headers={"X-API-Key": api_key},
    )
    assert res_revoked_event.status_code == 401
