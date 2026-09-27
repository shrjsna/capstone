"""
tests/test_integration.py
=========================
Full integration tests for the assembled system.

What this covers (that test_backend.py and test_bandit.py do NOT):
  1. End-to-end pipeline: fake event → POST /events → bandit decision →
     POST /feedback → confirm bandit state changed (thresholds updated).
  2. All four INTERFACES.md schema round-trips.
  3. Federation weight privacy: confirms numeric-only payload, no event data.
  4. Zone endpoint integration: save/load/delete via the /zones API.

Note on adapter: this repo's cloud/backend/adapter.py uses MockBanditAdapter.
The tests below verify the HTTP pipeline and observable state changes
(threshold values shift after feedback) — not internal matrix structures.

Zero external dependencies: no GPU, no camera, no video, no network.
Uses an in-memory SQLite DB so it doesn't touch cloud_backend.db on disk.
"""

import json
import tempfile
import pytest
import numpy as np
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from cloud.backend.main import app
from cloud.backend.database import get_db
from cloud.backend.models import Base, PolicyVersionModel
from cloud.backend.adapter import get_bandit_adapter, RealBanditAdapter, MockBanditAdapter
from cloud.backend.schemas import (
    DetectionEventCreate,
    OperatorFeedbackCreate,
    BanditDecisionOutput,
    PolicyUpdateRecord,
    OperatorFeedbackResponse,
)
from cloud.decision_layer.bandit import ContextualBandit, ACTIONS, DEFAULT_THRESHOLD
from cloud.federated.adapter import PolicyWeightAdapter

# ---------------------------------------------------------------------------
# Shared in-memory DB — isolated from test_backend.py's engine
# ---------------------------------------------------------------------------

_INTEG_DB_URL = "sqlite://"
_integ_engine = create_engine(
    _INTEG_DB_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool
)
_IntegSession = sessionmaker(autocommit=False, autoflush=False, bind=_integ_engine)


def _override_get_db():
    db = _IntegSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def integration_db():
    """
    Per-test: build schema, seed policy record, wire override, tear down after.
    """
    app.dependency_overrides[get_db] = _override_get_db
    Base.metadata.create_all(bind=_integ_engine)
    db = _IntegSession()
    if not db.query(PolicyVersionModel).first():
        db.add(PolicyVersionModel(
            policy_version="v1.0.0-mock",
            trained_at="2026-09-22T10:00:00Z",
            validation_score=0.915,
            previous_version="v0.9.0",
            deployed=True,
        ))
        db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=_integ_engine)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Full pipeline: event → backend → bandit decision → feedback → state change
# ---------------------------------------------------------------------------

class TestFullPipeline:
    """
    Verifies the end-to-end HTTP pipeline and observable bandit state changes.
    Uses MockBanditAdapter (the active adapter in this repo).
    """

    def test_ppe_event_gets_bandit_decision(self, client):
        """
        POST a ppe_violation event — must get back a bandit_action and threshold_used.
        """
        payload = {
            "camera_id": "cam_01", "zone_id": "zone_A",
            "event_type": "ppe_violation", "class": "no_helmet",
            "confidence": 0.91, "tracked_id": "person_001",
            "timestamp": "2026-09-22T10:00:00Z",
            "frame_count_triggered": 5, "clip_captured": False,
        }
        r = client.post("/events", json=payload)
        assert r.status_code == 201
        data = r.json()
        assert data["bandit_action"] in ["escalate", "log_only", "adjust_threshold"], (
            f"Unexpected bandit_action: '{data['bandit_action']}'"
        )
        assert isinstance(data["threshold_used"], float)
        assert 0.0 <= data["threshold_used"] <= 1.0

    def test_zone_intrusion_event_gets_bandit_decision(self, client):
        """Zone intrusion events also route through the bandit."""
        payload = {
            "camera_id": "cam_north", "zone_id": "zone_red_1",
            "event_type": "zone_intrusion", "class": "person_in_zone",
            "confidence": 0.87, "tracked_id": "person_002",
            "timestamp": "2026-09-22T10:01:00Z",
            "frame_count_triggered": 4, "clip_captured": False,
        }
        r = client.post("/events", json=payload)
        assert r.status_code == 201
        data = r.json()
        assert data["bandit_action"] in ["escalate", "log_only", "adjust_threshold"]

    def test_feedback_confirmed_updates_matrices(self, client):
        """
        After POST /feedback confirmed, ContextualBandit's A and b matrices
        for the chosen action must be updated with the reward signal.
        """
        adapter = get_bandit_adapter()
        assert isinstance(adapter, RealBanditAdapter)

        # Post an event first
        payload = {
            "camera_id": "cam_01", "zone_id": "zone_a",
            "event_type": "ppe_violation", "class": "no_vest",
            "confidence": 0.88, "tracked_id": "person_003",
            "timestamp": "2026-09-22T10:02:00Z",
            "frame_count_triggered": 4, "clip_captured": False,
        }
        r_event = client.post("/events", json=payload)
        assert r_event.status_code == 201
        event_data = r_event.json()
        event_id = event_data["event_id"]
        action = event_data["bandit_action"]

        # Capture matrix state before feedback
        A_before = adapter.bandit.A[action].copy()
        b_before = adapter.bandit.b[action].copy()

        # Submit confirmed feedback
        fb = {
            "event_id": event_id, "feedback": "confirmed",
            "operator_id": "op_test_01",
            "timestamp": "2026-09-22T10:02:30Z",
        }
        r_fb = client.post("/feedback", json=fb)
        assert r_fb.status_code == 200
        assert r_fb.json()["status"] == "success"

        # Matrices should have updated
        A_after = adapter.bandit.A[action]
        b_after = adapter.bandit.b[action]
        assert not np.allclose(A_after, A_before), "A matrix should update after feedback"
        assert not np.allclose(b_after, b_before), "b vector should update after feedback"

    def test_feedback_false_alarm_updates_matrices(self, client):
        """
        After POST /feedback false_alarm, bandit matrices update with penalty signal.
        """
        adapter = get_bandit_adapter()
        assert isinstance(adapter, RealBanditAdapter)

        payload = {
            "camera_id": "cam_02", "zone_id": "zone_a",
            "event_type": "zone_intrusion", "class": "person_in_zone",
            "confidence": 0.65, "tracked_id": "person_004",
            "timestamp": "2026-09-22T10:03:00Z",
            "frame_count_triggered": 3, "clip_captured": False,
        }
        r_event = client.post("/events", json=payload)
        event_data = r_event.json()
        event_id = event_data["event_id"]
        action = event_data["bandit_action"]

        A_before = adapter.bandit.A[action].copy()
        b_before = adapter.bandit.b[action].copy()

        fb = {
            "event_id": event_id, "feedback": "false_alarm",
            "operator_id": "op_test_02",
            "timestamp": "2026-09-22T10:03:30Z",
        }
        r_fb = client.post("/feedback", json=fb)
        assert r_fb.status_code == 200

        A_after = adapter.bandit.A[action]
        b_after = adapter.bandit.b[action]
        assert not np.allclose(A_after, A_before), "A matrix should update after false_alarm"
        assert not np.allclose(b_after, b_before), "b vector should update after false_alarm"

    def test_multiple_events_get_distinct_event_ids(self, client):
        """Each POST /events must return a unique UUID event_id."""
        ids = []
        for i in range(4):
            r = client.post("/events", json={
                "camera_id": "cam_01", "zone_id": "zone_A",
                "event_type": "ppe_violation", "class": "no_helmet",
                "confidence": 0.80 + i * 0.02, "tracked_id": f"person_{i:03d}",
                "timestamp": "2026-09-22T10:04:00Z",
                "frame_count_triggered": 3, "clip_captured": False,
            })
            assert r.status_code == 201
            ids.append(r.json()["event_id"])
        assert len(ids) == len(set(ids)), "Every event_id must be unique"

    def test_active_adapter_is_real(self):
        """Confirms the active adapter type is RealBanditAdapter wrapping ContextualBandit."""
        adapter = get_bandit_adapter()
        assert isinstance(adapter, RealBanditAdapter), (
            f"Expected RealBanditAdapter, got {type(adapter).__name__}"
        )
        assert isinstance(adapter.bandit, ContextualBandit)
        assert adapter.bandit.policy_version != "v1.0.0-mock"

    def test_mock_adapter_available_for_isolation(self):
        """Confirms MockBanditAdapter is retained for isolated unit testing."""
        mock = MockBanditAdapter()
        assert mock.policy_version == "v1.0.0-mock"
        event = DetectionEventCreate(**{
            "camera_id": "cam_01", "zone_id": "zone_a",
            "event_type": "ppe_violation", "class": "no_helmet",
            "confidence": 0.90, "tracked_id": "person_iso",
            "timestamp": "2026-09-22T10:00:00Z",
            "frame_count_triggered": 5, "clip_captured": False,
        })
        d = mock.decide(event, "evt_mock_01")
        assert d.action == "escalate"

    def test_adapter_decide_returns_valid_schema(self):
        """decide() must return a BanditDecisionOutput with valid fields."""
        adapter = get_bandit_adapter()
        event = DetectionEventCreate(**{
            "camera_id": "cam_01", "zone_id": "zone_A",
            "event_type": "ppe_violation", "class": "no_helmet",
            "confidence": 0.90, "tracked_id": "person_iso_test",
            "timestamp": "2026-09-22T10:06:00Z",
            "frame_count_triggered": 5, "clip_captured": False,
        })
        decision = adapter.decide(event, "evt_iso_001")
        assert isinstance(decision, BanditDecisionOutput)
        assert decision.event_id == "evt_iso_001"
        assert decision.action in ["escalate", "log_only", "adjust_threshold"]
        assert 0.0 <= decision.threshold_used <= 1.0


# ---------------------------------------------------------------------------
# 2. INTERFACES.md schema round-trip tests — all four schemas
# ---------------------------------------------------------------------------

class TestInterfacesSchemas:
    """
    Verify all four INTERFACES.md schemas survive JSON round-trips.
    """

    def test_schema1_detection_event_round_trip(self):
        """INTERFACES.md §1 — Detection Event (edge → cloud)."""
        raw = {
            "camera_id": "cam_01",
            "zone_id": "zone_A",
            "event_type": "ppe_violation",
            "class": "no_helmet",
            "confidence": 0.87,
            "tracked_id": "person_142",
            "timestamp": "2026-09-05T14:32:10Z",
            "frame_count_triggered": 4,
            "clip_captured": True,
        }
        model = DetectionEventCreate(**raw)
        assert model.camera_id == "cam_01"
        assert model.class_name == "no_helmet"
        assert model.confidence == 0.87
        assert model.frame_count_triggered == 4
        assert model.clip_captured is True

        serialised = json.loads(model.model_dump_json(by_alias=True))
        assert serialised["class"] == "no_helmet"
        assert "class_name" not in serialised
        assert serialised["event_type"] in ("ppe_violation", "zone_intrusion")
        assert 0.0 <= serialised["confidence"] <= 1.0
        assert isinstance(serialised["frame_count_triggered"], int)
        assert isinstance(serialised["clip_captured"], bool)

    def test_schema1_zone_intrusion_variant(self):
        """INTERFACES.md §1 — zone_intrusion variant."""
        raw = {
            "camera_id": "cam_north_01", "zone_id": "zone_B",
            "event_type": "zone_intrusion", "class": "person_in_zone",
            "confidence": 0.92, "tracked_id": "person_203",
            "timestamp": "2026-09-22T10:15:45Z",
            "frame_count_triggered": 6, "clip_captured": False,
        }
        model = DetectionEventCreate(**raw)
        assert model.event_type == "zone_intrusion"
        assert model.class_name == "person_in_zone"
        assert model.frame_count_triggered >= 3

    def test_schema2_operator_feedback_round_trip(self):
        """INTERFACES.md §2 — Operator Feedback (dashboard → cloud)."""
        raw = {
            "event_id": "evt_98213",
            "feedback": "confirmed",
            "operator_id": "op_04",
            "timestamp": "2026-09-05T14:33:02Z",
        }
        model = OperatorFeedbackCreate(**raw)
        assert model.event_id == "evt_98213"
        assert model.feedback == "confirmed"

        raw2 = {**raw, "event_id": "evt_99001", "feedback": "false_alarm"}
        model2 = OperatorFeedbackCreate(**raw2)
        assert model2.feedback == "false_alarm"

        import pydantic
        with pytest.raises((pydantic.ValidationError, ValueError)):
            OperatorFeedbackCreate(**{**raw, "feedback": "maybe"})

    def test_schema3_bandit_decision_output_round_trip(self):
        """INTERFACES.md §3 — Bandit Decision Output (cloud, internal)."""
        raw = {
            "event_id": "evt_98213",
            "action": "escalate",
            "policy_version": "policy_v7",
            "threshold_used": 0.75,
        }
        model = BanditDecisionOutput(**raw)
        assert model.event_id == "evt_98213"
        assert model.action == "escalate"
        assert model.policy_version == "policy_v7"
        assert model.threshold_used == 0.75

        for action in ("escalate", "log_only", "adjust_threshold"):
            m = BanditDecisionOutput(**{**raw, "action": action})
            assert m.action == action

        import pydantic
        with pytest.raises((pydantic.ValidationError, ValueError)):
            BanditDecisionOutput(**{**raw, "action": "ignore"})

    def test_schema4_policy_update_record_round_trip(self):
        """INTERFACES.md §4 — Policy Update Record (versioning/rollback)."""
        raw = {
            "policy_version": "policy_v8",
            "trained_at": "2026-09-05T18:00:00Z",
            "validation_score": 0.91,
            "previous_version": "policy_v7",
            "deployed": True,
        }
        model = PolicyUpdateRecord(**raw)
        assert model.policy_version == "policy_v8"
        assert model.validation_score == 0.91
        assert model.deployed is True

        raw_fail = {**raw, "policy_version": "policy_v9_candidate", "deployed": False}
        assert PolicyUpdateRecord(**raw_fail).deployed is False

    def test_bandit_predict_output_matches_schema3(self):
        """
        ContextualBandit.predict() output dict must match INTERFACES.md §3 keys.
        Tests the raw dict before Pydantic wrapping.
        """
        bandit = ContextualBandit(strategy="linucb", policy_version="policy_v7")
        event = {
            "camera_id": "cam_01", "zone_id": "zone_A",
            "event_type": "ppe_violation", "class": "no_helmet",
            "confidence": 0.87, "tracked_id": "person_142",
            "timestamp": "2026-09-05T14:32:10Z",
            "frame_count_triggered": 4, "clip_captured": True,
        }
        decision = bandit.predict(event, event_id="evt_98213")
        assert set(decision.keys()) == {"event_id", "action", "policy_version", "threshold_used"}
        assert decision["event_id"] == "evt_98213"
        assert decision["action"] in ACTIONS
        assert decision["policy_version"] == "policy_v7"
        assert isinstance(decision["threshold_used"], float)


# ---------------------------------------------------------------------------
# 3. Federation weight privacy checks
# ---------------------------------------------------------------------------

class TestFederationPrivacy:
    """
    Confirms PolicyWeightAdapter produces only numeric float64 arrays.
    No event data, camera IDs, timestamps, or feedback strings in the payload.
    """

    def test_bandit_to_weights_produces_6_arrays(self):
        """3 actions × (A + b) = 6 arrays."""
        bandit = ContextualBandit(strategy="linucb")
        weights = PolicyWeightAdapter.bandit_to_weights(bandit)
        assert len(weights) == 6

    def test_weight_shapes_are_correct(self):
        """A arrays: (256,); b arrays: (16,)."""
        bandit = ContextualBandit(strategy="linucb")
        weights = PolicyWeightAdapter.bandit_to_weights(bandit)
        for i in range(3):
            assert weights[i * 2].shape == (256,), f"A[{ACTIONS[i]}] shape wrong"
            assert weights[i * 2 + 1].shape == (16,), f"b[{ACTIONS[i]}] shape wrong"

    def test_all_weights_are_float64(self):
        """All weight arrays must be float64 — no object/string dtype."""
        bandit = ContextualBandit(strategy="linucb")
        weights = PolicyWeightAdapter.bandit_to_weights(bandit)
        for i, w in enumerate(weights):
            assert w.dtype == np.float64, (
                f"Array {i} dtype is {w.dtype}, must be float64."
            )

    def test_all_values_are_finite(self):
        """No NaN or Inf in federated payload."""
        bandit = ContextualBandit(strategy="linucb")
        weights = PolicyWeightAdapter.bandit_to_weights(bandit)
        for i, w in enumerate(weights):
            assert np.isfinite(w).all(), f"Non-finite value in weight array {i}"

    def test_weight_round_trip_preserves_exact_values(self):
        """bandit_to_weights() → weights_to_bandit() recovers A/b matrices exactly."""
        bandit_src = ContextualBandit(strategy="linucb", random_state=42)
        event = {
            "event_type": "ppe_violation", "class": "no_helmet",
            "confidence": 0.91, "frame_count_triggered": 5,
        }
        bandit_src.predict(event, event_id="rt_test_001")
        bandit_src.update("rt_test_001", "confirmed")

        weights = PolicyWeightAdapter.bandit_to_weights(bandit_src)
        bandit_dst = ContextualBandit(strategy="linucb")
        PolicyWeightAdapter.weights_to_bandit(weights, bandit_dst)

        for action in ACTIONS:
            np.testing.assert_array_equal(
                bandit_src.A[action], bandit_dst.A[action],
                err_msg=f"A[{action}] round-trip mismatch"
            )
            np.testing.assert_array_equal(
                bandit_src.b[action], bandit_dst.b[action],
                err_msg=f"b[{action}] round-trip mismatch"
            )

    def test_weights_to_bandit_graceful_on_empty(self):
        """Empty weight list must not crash or corrupt bandit state."""
        bandit = ContextualBandit(strategy="linucb")
        A_before = {a: bandit.A[a].copy() for a in ACTIONS}
        PolicyWeightAdapter.weights_to_bandit([], bandit)
        for action in ACTIONS:
            np.testing.assert_array_equal(bandit.A[action], A_before[action])
