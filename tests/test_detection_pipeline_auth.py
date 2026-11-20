"""
tests/test_detection_pipeline_auth.py
=====================================
Tests for Detection Pipeline Authentication and Integrity:
- Producers authenticate detection events with Edge Key or Internal Secret.
- Anonymous callers cannot inject events or operator feedback.
- Stream worker internal credential propagation.
- Operator feedback authentication.
"""

from datetime import datetime, timezone
import pytest
from cloud.backend.auth import INTERNAL_STREAM_KEY


def test_events_endpoint_rbac(anon_client, operator_client, admin_client, edge_client):
    """POST /events requires Admin or Edge role; Anon is 401, Operator is 403."""
    event_payload = {
        "camera_id": "cam_auth_test",
        "zone_id": "zone_1",
        "event_type": "ppe_violation",
        "class": "no_hardhat",
        "confidence": 0.88,
        "tracked_id": "track_42",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "frame_count_triggered": 10,
        "clip_captured": False,
    }

    # Anon is rejected with 401
    res_anon = anon_client.post("/events", json=event_payload)
    assert res_anon.status_code == 401

    # Operator is rejected with 403 (Operators do not generate ML events)
    res_op = operator_client.post("/events", json=event_payload)
    assert res_op.status_code == 403

    # Edge client succeeds
    res_edge = edge_client.post("/events", json=event_payload)
    assert res_edge.status_code == 201

    # Admin client succeeds
    res_admin = admin_client.post("/events", json=event_payload)
    assert res_admin.status_code == 201


def test_internal_stream_key_auth(anon_client):
    """Producers running with in-memory INTERNAL_STREAM_KEY are authenticated as Edge."""
    event_payload = {
        "camera_id": "cam_internal_worker",
        "zone_id": "zone_restricted",
        "event_type": "zone_intrusion",
        "class": "person_in_restricted_area",
        "confidence": 0.92,
        "tracked_id": "track_99",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "frame_count_triggered": 10,
        "clip_captured": False,
    }

    res = anon_client.post(
        "/events",
        json=event_payload,
        headers={"X-API-Key": INTERNAL_STREAM_KEY},
    )
    assert res.status_code == 201


def test_feedback_endpoint_rbac(anon_client, edge_client, operator_client, admin_client):
    """POST /feedback requires Operator or Admin role."""
    feedback_payload = {
        "event_id": "00000000-0000-0000-0000-000000000000",
        "feedback": "confirmed",
        "operator_id": "test_op",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Anon gets 401
    assert anon_client.post("/feedback", json=feedback_payload).status_code == 401

    # Edge gets 403
    assert edge_client.post("/feedback", json=feedback_payload).status_code == 403

    # Operator and Admin succeed (returns 404 because event does not exist in DB, proving RBAC check passed)
    res_op = operator_client.post("/feedback", json=feedback_payload)
    assert res_op.status_code == 404

    res_admin = admin_client.post("/feedback", json=feedback_payload)
    assert res_admin.status_code == 404
