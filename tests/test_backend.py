"""
Backend API Tests
==================
Integration tests for cloud/backend/main.py using FastAPI's TestClient.
The 'client' fixture uses a context manager so the app lifespan fires
(bandit is initialised) before any test runs.
"""

import pytest
from fastapi.testclient import TestClient

from cloud.backend.main import app, alerts, feedback_history, bandit as _bandit_ref


# ── Shared fixture — lifespan fires once per session ───────────────────────────
@pytest.fixture(scope="module")
def client():
    """Start the FastAPI app (triggering lifespan / bandit init) for all backend tests."""
    with TestClient(app) as c:
        yield c


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_event(
    camera_id="cam_01",
    zone_id="zone_A",
    confidence=0.87,
    event_type="ppe_violation",
    cls="no_helmet",
    event_id=None,
):
    payload = {
        "camera_id": camera_id,
        "zone_id": zone_id,
        "event_type": event_type,
        "class": cls,
        "confidence": confidence,
        "tracked_id": "person_001",
        "timestamp": "2026-09-05T14:32:10Z",
        "frame_count_triggered": 4,
        "clip_captured": True,
    }
    if event_id:
        payload["event_id"] = event_id
    return payload


def _clear_state():
    """Reset in-memory stores between tests that need a clean slate."""
    alerts.clear()
    feedback_history.clear()
    # Also drain any pending bandit events so duplicate-ID checks don't bleed across tests
    from cloud.backend.main import bandit
    if bandit is not None:
        bandit.pending_events.clear()


# ══════════════════════════════════════════════════════════════════
# 1. Health check
# ══════════════════════════════════════════════════════════════════

class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "policy_version" in body
        assert "timestamp" in body


# ══════════════════════════════════════════════════════════════════
# 2. POST /events
# ══════════════════════════════════════════════════════════════════

class TestPostEvent:
    def test_event_returns_201_and_valid_schema(self, client):
        resp = client.post("/events", json=_make_event())
        assert resp.status_code == 201
        body = resp.json()
        assert "event_id" in body
        assert body["action"] in ("escalate", "log_only", "adjust_threshold")
        assert "policy_version" in body
        assert isinstance(body["threshold_used"], float)

    def test_event_with_explicit_event_id_echoes_it(self, client):
        resp = client.post("/events", json=_make_event(event_id="explicit_001"))
        assert resp.status_code == 201
        assert resp.json()["event_id"] == "explicit_001"

    def test_duplicate_event_id_returns_409(self, client):
        client.post("/events", json=_make_event(event_id="dup_api_001"))
        resp = client.post("/events", json=_make_event(event_id="dup_api_001"))
        assert resp.status_code == 409

    def test_zone_intrusion_event_accepted(self, client):
        resp = client.post(
            "/events",
            json=_make_event(event_type="zone_intrusion", cls="person_in_zone", confidence=0.93),
        )
        assert resp.status_code == 201

    def test_invalid_event_type_rejected(self, client):
        payload = _make_event()
        payload["event_type"] = "bad_type"
        resp = client.post("/events", json=payload)
        assert resp.status_code == 422

    def test_confidence_out_of_range_rejected(self, client):
        payload = _make_event()
        payload["confidence"] = 1.5
        resp = client.post("/events", json=payload)
        assert resp.status_code == 422

    def test_event_is_stored_in_alert_feed(self, client):
        _clear_state()
        resp = client.post("/events", json=_make_event(event_id="stored_001"))
        assert resp.status_code == 201
        alert_resp = client.get("/alerts/stored_001")
        assert alert_resp.status_code == 200
        alert = alert_resp.json()
        assert alert["event_id"] == "stored_001"
        assert alert["status"] == "pending"


# ══════════════════════════════════════════════════════════════════
# 3. POST /feedback
# ══════════════════════════════════════════════════════════════════

class TestPostFeedback:
    def test_confirmed_feedback_returns_200(self, client):
        client.post("/events", json=_make_event(event_id="fb_conf_001"))
        resp = client.post(
            "/feedback",
            json={
                "event_id": "fb_conf_001",
                "feedback": "confirmed",
                "operator_id": "op_01",
                "timestamp": "2026-09-05T14:33:00Z",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] is True

    def test_false_alarm_feedback_returns_200(self, client):
        client.post("/events", json=_make_event(event_id="fb_fa_001"))
        resp = client.post(
            "/feedback",
            json={
                "event_id": "fb_fa_001",
                "feedback": "false_alarm",
                "operator_id": "op_02",
                "timestamp": "2026-09-05T14:34:00Z",
            },
        )
        assert resp.status_code == 200

    def test_feedback_marks_alert_acknowledged(self, client):
        _clear_state()
        client.post("/events", json=_make_event(event_id="fb_ack_001"))
        client.post(
            "/feedback",
            json={"event_id": "fb_ack_001", "feedback": "confirmed", "operator_id": "op_03"},
        )
        alert_resp = client.get("/alerts/fb_ack_001")
        assert alert_resp.json()["status"] == "acknowledged"
        assert alert_resp.json()["feedback"] == "confirmed"

    def test_unknown_event_id_returns_404(self, client):
        resp = client.post(
            "/feedback",
            json={"event_id": "nonexistent_xyz", "feedback": "confirmed", "operator_id": "op_01"},
        )
        assert resp.status_code == 404

    def test_invalid_feedback_value_rejected(self, client):
        client.post("/events", json=_make_event(event_id="fb_invalid_001"))
        resp = client.post(
            "/feedback",
            json={"event_id": "fb_invalid_001", "feedback": "maybe", "operator_id": "op_01"},
        )
        assert resp.status_code == 422

    def test_double_feedback_returns_404_second_time(self, client):
        """After first update(), event leaves pending_events — second feedback must 404."""
        client.post("/events", json=_make_event(event_id="fb_double_001"))
        client.post(
            "/feedback",
            json={"event_id": "fb_double_001", "feedback": "confirmed", "operator_id": "op_01"},
        )
        resp2 = client.post(
            "/feedback",
            json={"event_id": "fb_double_001", "feedback": "false_alarm", "operator_id": "op_01"},
        )
        assert resp2.status_code == 404


# ══════════════════════════════════════════════════════════════════
# 4. GET /alerts
# ══════════════════════════════════════════════════════════════════

class TestGetAlerts:
    def test_alerts_returns_list(self, client):
        resp = client.get("/alerts")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_status_filter_pending(self, client):
        _clear_state()
        client.post("/events", json=_make_event(event_id="filter_p_001"))
        client.post("/events", json=_make_event(event_id="filter_p_002"))
        # Acknowledge one
        client.post(
            "/feedback",
            json={"event_id": "filter_p_001", "feedback": "confirmed", "operator_id": "op_01"},
        )
        resp = client.get("/alerts?status_filter=pending")
        statuses = [r["status"] for r in resp.json()]
        assert all(s == "pending" for s in statuses)

    def test_status_filter_acknowledged(self, client):
        _clear_state()
        client.post("/events", json=_make_event(event_id="filter_a_001"))
        client.post(
            "/feedback",
            json={"event_id": "filter_a_001", "feedback": "false_alarm", "operator_id": "op_01"},
        )
        resp = client.get("/alerts?status_filter=acknowledged")
        assert all(r["status"] == "acknowledged" for r in resp.json())

    def test_limit_parameter_respected(self, client):
        _clear_state()
        for i in range(10):
            client.post("/events", json=_make_event(event_id=f"limit_test_{i:03d}"))
        resp = client.get("/alerts?limit=3")
        assert len(resp.json()) <= 3

    def test_get_single_alert_not_found(self, client):
        resp = client.get("/alerts/does_not_exist_xyz")
        assert resp.status_code == 404


# ══════════════════════════════════════════════════════════════════
# 5. GET /policy
# ══════════════════════════════════════════════════════════════════

class TestGetPolicy:
    def test_policy_returns_expected_keys(self, client):
        resp = client.get("/policy")
        assert resp.status_code == 200
        body = resp.json()
        for key in ("policy_version", "previous_version", "strategy", "pending_decisions"):
            assert key in body, f"Missing key: {key}"


# ══════════════════════════════════════════════════════════════════
# 6. POST /retrain
# ══════════════════════════════════════════════════════════════════

class TestRetrain:
    def test_retrain_fails_without_enough_feedback(self, client):
        _clear_state()
        resp = client.post("/retrain", json={"min_validation_score": 0.70})
        assert resp.status_code == 422

    def test_retrain_succeeds_with_sufficient_feedback(self, client):
        _clear_state()
        # Submit 10 events with confirmed feedback to build history
        for i in range(10):
            eid = f"retrain_evt_{i:03d}"
            client.post(
                "/events",
                json=_make_event(event_id=eid, confidence=0.90),
            )
            client.post(
                "/feedback",
                json={"event_id": eid, "feedback": "confirmed", "operator_id": "op_01"},
            )

        resp = client.post("/retrain", json={"min_validation_score": 0.50})
        assert resp.status_code == 200
        body = resp.json()
        assert "policy_version" in body
        assert "validation_score" in body
        assert "deployed" in body
        assert isinstance(body["deployed"], bool)


# ══════════════════════════════════════════════════════════════════
# 7. POST /rollback
# ══════════════════════════════════════════════════════════════════

class TestRollback:
    def test_rollback_returns_version(self, client):
        resp = client.post("/rollback")
        assert resp.status_code == 200
        body = resp.json()
        assert "rolled_back_to" in body
        assert body["rolled_back_to"].startswith("policy_v")
