"""
tests/test_backend.py
Pytest unit tests for FastAPI backend endpoints using FastAPI TestClient and shared in-memory SQLite.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cloud.backend.main import app
from cloud.backend.database import get_db
from cloud.backend.models import Base, PolicyVersionModel

# StaticPool ensures all connections share the exact same in-memory database instance
SQLALCHEMY_TEST_DATABASE_URL = "sqlite://"

engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def run_around_tests():
    # Re-assert this module's DB override before each test (guards against
    # cross-module override stomping when collected with test_integration.py)
    app.dependency_overrides[get_db] = override_get_db

    # Build schema in shared in-memory DB before each test
    Base.metadata.create_all(bind=engine)
    
    # Seed initial policy record in in-memory DB
    db = TestingSessionLocal()
    if not db.query(PolicyVersionModel).first():
        seed_policy = PolicyVersionModel(
            policy_version="v1.0.0-mock",
            trained_at="2026-09-20T10:00:00Z",
            validation_score=0.915,
            previous_version="v0.9.0",
            deployed=True
        )
        db.add(seed_policy)
        db.commit()
    db.close()

    yield

    # Drop schema after each test
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_post_event_success():
    payload = {
        "camera_id": "cam_01",
        "zone_id": "zone_a",
        "event_type": "ppe_violation",
        "class": "no_helmet",
        "confidence": 0.88,
        "tracked_id": "tr_102",
        "timestamp": "2026-09-20T12:00:00Z",
        "frame_count_triggered": 15,
        "clip_captured": True
    }
    response = client.post("/events", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert "event_id" in data
    assert data["camera_id"] == "cam_01"
    assert data["zone_id"] == "zone_a"
    assert data["event_type"] == "ppe_violation"
    assert data["class"] == "no_helmet"
    assert data["confidence"] == 0.88
    assert data["bandit_action"] in ["escalate", "log_only", "adjust_threshold"]


def test_post_event_malformed_rejected():
    # Missing camera_id and confidence
    malformed_payload = {
        "zone_id": "zone_a",
        "event_type": "invalid_type",
        "class": "no_helmet"
    }
    response = client.post("/events", json=malformed_payload)
    assert response.status_code == 422


def test_post_feedback_success():
    # First create an event
    event_payload = {
        "camera_id": "cam_02",
        "zone_id": "zone_b",
        "event_type": "zone_intrusion",
        "class": "person_in_restricted_area",
        "confidence": 0.92,
        "tracked_id": "tr_205",
        "timestamp": "2026-09-20T12:05:00Z",
        "frame_count_triggered": 20,
        "clip_captured": True
    }
    event_resp = client.post("/events", json=event_payload)
    event_id = event_resp.json()["event_id"]

    # Now post operator feedback
    feedback_payload = {
        "event_id": event_id,
        "feedback": "confirmed",
        "operator_id": "op_smith_01",
        "timestamp": "2026-09-20T12:06:00Z"
    }
    fb_resp = client.post("/feedback", json=feedback_payload)
    assert fb_resp.status_code == 200
    assert fb_resp.json()["status"] == "success"
    assert fb_resp.json()["event_id"] == event_id


def test_post_feedback_nonexistent_event_rejected():
    fake_feedback = {
        "event_id": "00000000-0000-0000-0000-000000000000",
        "feedback": "false_alarm",
        "operator_id": "op_smith_01",
        "timestamp": "2026-09-20T12:06:00Z"
    }
    response = client.post("/feedback", json=fake_feedback)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_get_alerts_list():
    # Post 2 events
    for i in range(2):
        client.post("/events", json={
            "camera_id": f"cam_0{i}",
            "zone_id": "zone_a",
            "event_type": "ppe_violation",
            "class": "no_goggles",
            "confidence": 0.80 + (i * 0.05),
            "tracked_id": f"tr_{i}",
            "timestamp": f"2026-09-20T12:10:0{i}Z",
            "frame_count_triggered": 10,
            "clip_captured": False
        })

    alerts_resp = client.get("/alerts?limit=10")
    assert alerts_resp.status_code == 200
    alerts = alerts_resp.json()
    assert len(alerts) == 2


def test_get_alert_detail():
    event_resp = client.post("/events", json={
        "camera_id": "cam_detail",
        "zone_id": "zone_a",
        "event_type": "zone_intrusion",
        "class": "vehicle_intrusion",
        "confidence": 0.95,
        "tracked_id": "tr_detail_1",
        "timestamp": "2026-09-20T12:15:00Z",
        "frame_count_triggered": 30,
        "clip_captured": True
    })
    event_id = event_resp.json()["event_id"]

    detail_resp = client.get(f"/alerts/{event_id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["event_id"] == event_id
    assert detail_resp.json()["camera_id"] == "cam_detail"


def test_get_policy_history():
    response = client.get("/policy-history")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) > 0
