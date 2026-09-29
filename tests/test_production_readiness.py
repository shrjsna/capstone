"""
tests/test_production_readiness.py
==================================
Comprehensive automated security, validation, and operational test suite
for the AEGIS production-readiness pass:
1. API Authentication & Token verification across all state-changing endpoints.
2. Strict input validation (path traversal, command injection, malformed IDs).
3. CORS configuration validation.
4. Stream concurrency and resource safeguards.
5. Data retention and storage cleanup logic.
6. Alert history multi-parameter filtering and feedback state joining.
7. Zone polygon coordinate persistence in /zones catalog.
"""

import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cloud.backend.main import app, ZONES_DIR
from cloud.backend.config import get_settings, REPO_ROOT
from cloud.backend.database import get_db
from cloud.backend.models import Base, EventModel, FeedbackModel
from cloud.backend.security import verify_api_key
from cloud.backend.retention import cleanup_old_records
from cloud.backend.stream_manager import (
    start_stream,
    stop_stream,
    stream_status,
    generate_mjpeg_frames,
    MAX_MJPEG_CLIENTS,
)

# Test In-Memory Database with StaticPool
TEST_DB_URL = "sqlite://"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_test_environment(monkeypatch):
    """Set up clean database tables and isolate test dependencies."""
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_db

    # Ensure test settings use standard test secret
    settings = get_settings()
    settings.API_KEY = "test-secret-key-123"
    settings.AUTH_ENABLED = True

    yield

    Base.metadata.drop_all(bind=test_engine)
    app.dependency_overrides.pop(get_db, None)


# ===========================================================================
# 1. Authentication & Security Tests
# ===========================================================================

class TestAuthentication:
    """Validate API key authentication across all state-changing endpoints."""

    @pytest.fixture(autouse=True)
    def enforce_auth(self):
        """Explicitly remove any auth bypass fixture for authentication testing."""
        app.dependency_overrides.pop(verify_api_key, None)
        yield

    def test_unauthenticated_state_changing_endpoints_rejected(self):
        """All state-changing endpoints must return 401 when no auth header is provided."""
        client = TestClient(app)

        endpoints = [
            ("POST", "/events", {"camera_id": "c1", "zone_id": "z1", "event_type": "ppe_violation", "class": "no_helmet", "confidence": 0.9, "tracked_id": "t1", "timestamp": "2026-09-29T12:00:00Z", "frame_count_triggered": 5}),
            ("POST", "/feedback", {"event_id": "ev_01", "feedback": "confirmed", "operator_id": "op_test", "timestamp": "2026-09-29T12:01:00Z"}),
            ("POST", "/zones", {"camera_id": "c1", "zone_id": "z1", "polygon": [[0, 0], [10, 0], [10, 10]]}),
            ("DELETE", "/zones/c1/z1", None),
            ("POST", "/stream/start", {"source": "0", "mode": "ppe"}),
            ("POST", "/stream/stop", None),
            ("POST", "/processes/federated_demo/start", None),
            ("POST", "/processes/federated_demo/stop", None),
            ("POST", "/retention/cleanup", {"max_age_days": 7}),
        ]

        for method, path, payload in endpoints:
            if method == "POST":
                res = client.post(path, json=payload)
            elif method == "DELETE":
                res = client.delete(path)
            assert res.status_code == 401, f"{method} {path} should be 401 without auth, got {res.status_code}"
            assert "Unauthorized" in res.json().get("detail", "")

    def test_invalid_api_key_rejected(self):
        """Requests with incorrect API key must be rejected with 401."""
        client = TestClient(app)
        headers = {"X-API-Key": "completely-wrong-key"}
        res = client.post("/events", json={"camera_id": "c1", "zone_id": "z1", "event_type": "ppe_violation", "class": "no_helmet", "confidence": 0.9, "tracked_id": "t1", "timestamp": "2026-09-29T12:00:00Z", "frame_count_triggered": 5}, headers=headers)
        assert res.status_code == 401
        assert "Invalid API key" in res.json()["detail"]

    def test_valid_api_key_accepted_via_header_or_bearer(self):
        """Requests with correct API key via X-API-Key or Bearer token succeed."""
        client = TestClient(app)

        # 1. Via X-API-Key
        headers1 = {"X-API-Key": "test-secret-key-123"}
        payload = {
            "camera_id": "cam_auth_01",
            "zone_id": "zone_auth_a",
            "event_type": "ppe_violation",
            "class": "no_vest",
            "confidence": 0.85,
            "tracked_id": "tr_99",
            "timestamp": "2026-09-29T12:00:00Z",
            "frame_count_triggered": 4,
            "clip_captured": False,
        }
        res1 = client.post("/events", json=payload, headers=headers1)
        assert res1.status_code == 201
        ev_id = res1.json()["event_id"]

        # 2. Via Authorization: Bearer
        headers2 = {"Authorization": "Bearer test-secret-key-123"}
        fb_payload = {
            "event_id": ev_id,
            "feedback": "confirmed",
            "operator_id": "op_admin_test",
            "timestamp": "2026-09-29T12:01:00Z",
        }
        res2 = client.post("/feedback", json=fb_payload, headers=headers2)
        assert res2.status_code == 200
        assert res2.json()["status"] == "success"

    def test_read_only_endpoints_open(self):
        """Read-only monitoring endpoints must remain open without auth headers."""
        client = TestClient(app)
        assert client.get("/health").status_code == 200
        assert client.get("/alerts").status_code == 200
        assert client.get("/zones").status_code == 200
        assert client.get("/thresholds").status_code == 200
        assert client.get("/policy-history").status_code == 200
        assert client.get("/processes").status_code == 200
        assert client.get("/stream/status").status_code == 200


# ===========================================================================
# 2. Input Validation & Path Traversal Rejection Tests
# ===========================================================================

class TestInputValidation:
    """Ensure strict validation rejects directory traversal, shell chars, and malformed inputs."""

    def test_zone_save_path_traversal_rejected(self):
        client = TestClient(app)
        headers = {"X-API-Key": "test-secret-key-123"}

        # Traversal in camera_id
        res1 = client.post("/zones", json={"camera_id": "../../etc", "zone_id": "z1", "polygon": [[0, 0], [10, 0], [10, 10]]}, headers=headers)
        assert res1.status_code == 422

        # Traversal in zone_id
        res2 = client.post("/zones", json={"camera_id": "cam01", "zone_id": "../passwd", "polygon": [[0, 0], [10, 0], [10, 10]]}, headers=headers)
        assert res2.status_code == 422

    def test_zone_delete_path_traversal_rejected(self):
        client = TestClient(app)
        headers = {"X-API-Key": "test-secret-key-123"}
        res = client.delete("/zones/..%2F..%2Fetc/shadow", headers=headers)
        assert res.status_code in (404, 405, 422)

    def test_stream_start_unsafe_source_rejected(self):
        client = TestClient(app)
        headers = {"X-API-Key": "test-secret-key-123"}

        # Traversal in local video path
        res1 = client.post("/stream/start", json={"source": "../../boot.ini", "mode": "ppe"}, headers=headers)
        assert res1.status_code == 422

        # Shell characters in URL
        res2 = client.post("/stream/start", json={"source": "rtsp://192.168.1.1/live; rm -rf /", "mode": "ppe"}, headers=headers)
        assert res2.status_code == 422

    def test_stream_start_unsafe_model_path_rejected(self):
        client = TestClient(app)
        headers = {"X-API-Key": "test-secret-key-123"}
        res = client.post("/stream/start", json={"source": "0", "mode": "ppe", "model_path": "../../secret.pt"}, headers=headers)
        assert res.status_code == 422

    def test_feedback_invalid_operator_id_rejected(self):
        client = TestClient(app)
        headers = {"X-API-Key": "test-secret-key-123"}
        # Operator ID with shell metacharacters
        res = client.post("/feedback", json={"event_id": "ev_01", "feedback": "confirmed", "operator_id": "op;rm -rf", "timestamp": "2026-09-29T12:00:00Z"}, headers=headers)
        assert res.status_code == 422


# ===========================================================================
# 3. CORS Configuration Tests
# ===========================================================================

class TestCORSConfiguration:
    """Validate explicit origin filtering."""

    def test_cors_headers_on_allowed_origin(self):
        client = TestClient(app)
        res = client.options(
            "/health",
            headers={
                "Origin": "http://127.0.0.1:8000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert res.status_code == 200
        assert res.headers.get("access-control-allow-origin") == "http://127.0.0.1:8000"

    def test_cors_headers_reject_disallowed_origin(self):
        client = TestClient(app)
        res = client.options(
            "/health",
            headers={
                "Origin": "http://malicious-site.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        # Starlette CORS middleware does NOT echo back unauthorized origins
        assert res.headers.get("access-control-allow-origin") != "http://malicious-site.com"


# ===========================================================================
# 4. Data Retention & Storage Cleanup Tests
# ===========================================================================

class TestDataRetention:
    """Validate age-based event and clip cleanup."""

    def test_aged_events_cleanup(self, tmp_path):
        db = TestingSession()
        now = datetime.now(timezone.utc)

        # 1. Create an event 10 days old (should be pruned)
        old_time = (now - timedelta(days=10)).isoformat()
        e_old = EventModel(
            event_id="ev_old_10d",
            camera_id="cam_01",
            zone_id="zone_01",
            event_type="ppe_violation",
            class_name="no_helmet",
            confidence=0.9,
            tracked_id="tr_1",
            timestamp=old_time,
            frame_count_triggered=5,
            clip_captured=False,
        )
        db.add(e_old)

        # 2. Create a recent event (should be kept)
        recent_time = (now - timedelta(hours=2)).isoformat()
        e_new = EventModel(
            event_id="ev_new_2h",
            camera_id="cam_01",
            zone_id="zone_01",
            event_type="ppe_violation",
            class_name="no_vest",
            confidence=0.88,
            tracked_id="tr_2",
            timestamp=recent_time,
            frame_count_triggered=6,
            clip_captured=False,
        )
        db.add(e_new)
        db.commit()

        # 3. Create dummy clips in temp directory
        clips_dir = tmp_path / "clips"
        clips_dir.mkdir()
        old_clip = clips_dir / "old_clip.mp4"
        old_clip.write_bytes(b"dummy clip data 12345")
        # Set mtime to 12 days ago
        past_epoch = (now - timedelta(days=12)).timestamp()
        import os
        os.utime(str(old_clip), (past_epoch, past_epoch))

        new_clip = clips_dir / "new_clip.mp4"
        new_clip.write_bytes(b"recent clip data 67890")

        # Execute cleanup with 7-day retention
        result = cleanup_old_records(db, max_age_days=7, clips_dir=clips_dir)

        assert result["events_pruned"] >= 1
        assert result["clips_deleted"] == 1
        assert not old_clip.exists(), "Old clip was not deleted"
        assert new_clip.exists(), "Recent clip was erroneously deleted"

        # Verify database state
        assert db.query(EventModel).filter(EventModel.event_id == "ev_old_10d").first() is None
        assert db.query(EventModel).filter(EventModel.event_id == "ev_new_2h").first() is not None
        db.close()

    def test_retention_cleanup_api_endpoint(self):
        client = TestClient(app)
        headers = {"X-API-Key": "test-secret-key-123"}
        res = client.post("/retention/cleanup", json={"max_age_days": 14, "max_events": 2000}, headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"
        assert data["retention_days"] == 14
        assert "events_pruned" in data


# ===========================================================================
# 5. Alert History Filtering & Feedback Status Tests
# ===========================================================================

class TestAlertFeedFeatures:
    """Validate query filtering and feedback join."""

    def test_filter_alerts_by_type_and_camera(self):
        db = TestingSession()
        db.query(EventModel).delete()
        db.commit()

        e1 = EventModel(event_id="e1", camera_id="cam_east", zone_id="z_a", event_type="ppe_violation", class_name="no_helmet", confidence=0.8, tracked_id="t1", timestamp="2026-09-29T10:00:00Z", frame_count_triggered=3, clip_captured=False)
        e2 = EventModel(event_id="e2", camera_id="cam_west", zone_id="z_b", event_type="zone_intrusion", class_name="person_in_zone", confidence=0.9, tracked_id="t2", timestamp="2026-09-29T11:00:00Z", frame_count_triggered=4, clip_captured=False)
        db.add_all([e1, e2])
        db.commit()
        db.close()

        client = TestClient(app)

        # Filter by camera_id
        r_cam = client.get("/alerts?camera_id=cam_east")
        assert r_cam.status_code == 200
        assert len(r_cam.json()) == 1
        assert r_cam.json()[0]["camera_id"] == "cam_east"

        # Filter by event_type
        r_type = client.get("/alerts?event_type=zone_intrusion")
        assert r_type.status_code == 200
        assert len(r_type.json()) == 1
        assert r_type.json()[0]["event_type"] == "zone_intrusion"

    def test_alert_response_includes_feedback_state(self):
        db = TestingSession()
        db.query(FeedbackModel).delete()
        db.query(EventModel).delete()

        e = EventModel(event_id="ev_fb_test", camera_id="cam_01", zone_id="z1", event_type="ppe_violation", class_name="no_helmet", confidence=0.8, tracked_id="t1", timestamp="2026-09-29T10:00:00Z", frame_count_triggered=3, clip_captured=False)
        db.add(e)
        db.commit()

        fb = FeedbackModel(event_id="ev_fb_test", feedback="confirmed", operator_id="op_tester", timestamp="2026-09-29T10:05:00Z")
        db.add(fb)
        db.commit()
        db.close()

        client = TestClient(app)
        res = client.get("/alerts")
        assert res.status_code == 200
        alerts = res.json()
        assert len(alerts) >= 1
        alert = next(a for a in alerts if a["event_id"] == "ev_fb_test")
        assert alert["feedback"] == "confirmed"


# ===========================================================================
# 6. Zone Polygon Catalog Tests (Bug Fix Verification)
# ===========================================================================

class TestZonePolygonPersistence:
    """Confirm /zones returns polygon points so frontend 'Load' button works."""

    def test_zones_endpoint_returns_polygon_coordinates(self):
        client = TestClient(app)
        headers = {"X-API-Key": "test-secret-key-123"}

        poly = [[100, 150], [300, 150], [300, 400], [100, 400]]
        save_res = client.post("/zones", json={"camera_id": "cam_catalog_test", "zone_id": "zone_box_1", "polygon": poly, "frame_width": 640, "frame_height": 480}, headers=headers)
        assert save_res.status_code == 201

        list_res = client.get("/zones")
        assert list_res.status_code == 200
        zones = list_res.json()

        target = next((z for z in zones if z["camera_id"] == "cam_catalog_test" and z["zone_id"] == "zone_box_1"), None)
        assert target is not None, "Saved zone not found in /zones catalog"
        assert target["polygon"] == poly, f"Expected {poly}, got {target.get('polygon')}"
        assert target["point_count"] == 4

        # Clean up
        client.delete("/zones/cam_catalog_test/zone_box_1", headers=headers)
