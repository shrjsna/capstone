"""
tests/test_integration.py
Full mocked pipeline integration tests — zero GPU, camera, network, or video
dependencies. Uses real code paths: real RealBanditAdapter, real backend routes,
real ContextualBandit functions, real PolicyWeightAdapter serialization.

Coverage:
  1. Full pipeline: fake event → real backend → real bandit decision
                    → feedback → confirm bandit state changed
  2. INTERFACES.md schema round-trip tests for all 4 schemas
  3. RealBanditAdapter isolation tests (verify no mock paths active)
  4. Federation weight serialization round-trip (A/b matrix fidelity)

Does NOT duplicate:
  - test_backend.py: individual route smoke tests, DB validation
  - test_bandit.py:  ContextualBandit unit tests (predict, update, retrain)
  - test_federated.py: FedAvg math, dict_to_weights/weights_to_dict round-trip
"""

import pytest
import json
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
import numpy as np

from cloud.backend.main import app
from cloud.backend.database import get_db
from cloud.backend.models import Base, PolicyVersionModel
from cloud.backend.adapter import get_bandit_adapter, RealBanditAdapter, BanditAdapter
from cloud.backend.schemas import (
    DetectionEventCreate,
    DetectionEventResponse,
    OperatorFeedbackCreate,
    OperatorFeedbackResponse,
    BanditDecisionOutput,
    PolicyUpdateRecord,
)
from cloud.decision_layer.bandit import ContextualBandit, ACTIONS, DEFAULT_THRESHOLD
from cloud.federated.adapter import PolicyWeightAdapter


# ── Shared in-memory DB setup ───────────────────────────────────────────────

INTEGRATION_DB_URL = "sqlite://"
_engine = create_engine(
    INTEGRATION_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def _override_get_db():
    db = _TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db


@pytest.fixture(autouse=True)
def reset_db():
    """Rebuild schema, seed policy record, and restore DB override before/after each test."""
    # Ensure this test module's override is active for every test
    app.dependency_overrides[get_db] = _override_get_db
    Base.metadata.create_all(bind=_engine)
    db = _TestSession()
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
    Base.metadata.drop_all(bind=_engine)
    # Restore test_backend.py's override so it isn't broken by isolation cleanup
    # (test_backend.py registers its override at module level; we re-register ours
    # here only for tests within this module, then let pytest module ordering handle
    # the final state — each test module re-asserts its own override via autouse)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client():
    return TestClient(app)


# ── Helper: minimal valid event payload ─────────────────────────────────────

def make_event_payload(
    event_type: str = "ppe_violation",
    class_name: str = "no_helmet",
    confidence: float = 0.91,
    camera_id: str = "cam_01",
    zone_id: str = "zone_a",
    frame_count: int = 5,
) -> dict:
    return {
        "camera_id": camera_id,
        "zone_id": zone_id,
        "event_type": event_type,
        "class": class_name,
        "confidence": confidence,
        "tracked_id": "person_100",
        "timestamp": "2026-09-22T10:00:00Z",
        "frame_count_triggered": frame_count,
        "clip_captured": True,
    }


# ════════════════════════════════════════════════════════════════════════════
# 1. Full pipeline integration tests
# ════════════════════════════════════════════════════════════════════════════

class TestFullPipeline:
    """
    End-to-end mocked pipeline: event → backend → real bandit → feedback
    → confirm bandit state changed. Uses real code, not reimplemented logic.
    """

    def test_ppe_event_receives_real_bandit_decision(self, client):
        """
        A PPE violation event posted to /events should return a bandit decision
        produced by RealBanditAdapter (not mock), with a policy_version from the
        real ContextualBandit (policy_v2 after warm-start retrain).
        """
        payload = make_event_payload(event_type="ppe_violation", class_name="no_helmet", confidence=0.91)
        resp = client.post("/events", json=payload)
        assert resp.status_code == 201

        data = resp.json()
        assert data["bandit_action"] in ACTIONS
        # Real adapter's policy version is "policy_v2" after warm-start; never "v1.0.0-mock"
        assert data["policy_version"] != "v1.0.0-mock", (
            f"Expected real policy_version, got '{data['policy_version']}' — "
            "adapter may still be using MockBanditAdapter"
        )
        assert isinstance(data["threshold_used"], float)
        assert 0.0 <= data["threshold_used"] <= 1.0

    def test_zone_intrusion_event_receives_real_bandit_decision(self, client):
        """Zone intrusion event goes through the same real bandit path."""
        payload = make_event_payload(
            event_type="zone_intrusion",
            class_name="person_in_zone",
            confidence=0.87,
            zone_id="zone_b",
        )
        resp = client.post("/events", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["event_type"] == "zone_intrusion"
        assert data["bandit_action"] in ACTIONS
        assert data["policy_version"] != "v1.0.0-mock"

    def test_feedback_confirmed_changes_bandit_state(self, client):
        """
        After operator submits 'confirmed' feedback, the bandit's A/b matrices
        for the action that was chosen must change (online update applied).
        This confirms the real update() path is being called, not discarded.
        """
        adapter = get_bandit_adapter()
        assert isinstance(adapter, RealBanditAdapter), "Active adapter must be RealBanditAdapter"

        payload = make_event_payload(confidence=0.91)
        event_resp = client.post("/events", json=payload)
        assert event_resp.status_code == 201
        event_id = event_resp.json()["event_id"]
        chosen_action = event_resp.json()["bandit_action"]

        # Capture A/b state immediately before feedback
        A_before = adapter.bandit.A[chosen_action].copy()
        b_before = adapter.bandit.b[chosen_action].copy()

        fb_payload = {
            "event_id": event_id,
            "feedback": "confirmed",
            "operator_id": "op_test_01",
            "timestamp": "2026-09-22T10:01:00Z",
        }
        fb_resp = client.post("/feedback", json=fb_payload)
        assert fb_resp.status_code == 200

        # A or b must have changed
        A_changed = not np.allclose(adapter.bandit.A[chosen_action], A_before)
        b_changed = not np.allclose(adapter.bandit.b[chosen_action], b_before)
        assert A_changed or b_changed, (
            f"Bandit state for action '{chosen_action}' did not change after feedback — "
            "submit_feedback() may not be calling bandit.update()"
        )

    def test_feedback_false_alarm_changes_bandit_state(self, client):
        """False alarm feedback also triggers an online update."""
        adapter = get_bandit_adapter()
        payload = make_event_payload(confidence=0.75)
        event_resp = client.post("/events", json=payload)
        event_id = event_resp.json()["event_id"]
        chosen_action = event_resp.json()["bandit_action"]

        A_before = adapter.bandit.A[chosen_action].copy()

        fb_payload = {
            "event_id": event_id,
            "feedback": "false_alarm",
            "operator_id": "op_test_02",
            "timestamp": "2026-09-22T10:02:00Z",
        }
        fb_resp = client.post("/feedback", json=fb_payload)
        assert fb_resp.status_code == 200

        A_changed = not np.allclose(adapter.bandit.A[chosen_action], A_before)
        b_changed = not np.allclose(adapter.bandit.b[chosen_action], b_before if False else adapter.bandit.b[chosen_action])
        assert not np.allclose(adapter.bandit.A[chosen_action], A_before), (
            "Bandit A matrix did not change after false_alarm feedback"
        )

    def test_multiple_events_all_get_unique_event_ids_and_bandit_decisions(self, client):
        """Five events → five unique event IDs, each with a bandit decision."""
        ids = set()
        for i in range(5):
            payload = make_event_payload(confidence=0.80 + i * 0.02, frame_count=3 + i)
            resp = client.post("/events", json=payload)
            assert resp.status_code == 201
            data = resp.json()
            ids.add(data["event_id"])
            assert data["bandit_action"] in ACTIONS

        assert len(ids) == 5, "All 5 events must get distinct UUID event_ids"

    def test_alerts_endpoint_reflects_posted_events(self, client):
        """Events posted via /events are retrievable via GET /alerts."""
        payloads = [
            make_event_payload(event_type="ppe_violation", class_name="no_helmet", confidence=0.88),
            make_event_payload(event_type="zone_intrusion", class_name="person_in_zone", confidence=0.82,
                               camera_id="cam_north", zone_id="zone_b"),
        ]
        posted_ids = set()
        for p in payloads:
            r = client.post("/events", json=p)
            assert r.status_code == 201
            posted_ids.add(r.json()["event_id"])

        alerts_resp = client.get("/alerts?limit=10")
        assert alerts_resp.status_code == 200
        alert_ids = {a["event_id"] for a in alerts_resp.json()}
        assert posted_ids.issubset(alert_ids)


# ════════════════════════════════════════════════════════════════════════════
# 2. INTERFACES.md schema round-trip tests
# ════════════════════════════════════════════════════════════════════════════

INTERFACES_EVENT_KEYS = {
    "camera_id", "zone_id", "event_type", "class", "confidence",
    "tracked_id", "timestamp", "frame_count_triggered", "clip_captured",
}

INTERFACES_FEEDBACK_KEYS = {"event_id", "feedback", "operator_id", "timestamp"}

INTERFACES_BANDIT_DECISION_KEYS = {"event_id", "action", "policy_version", "threshold_used"}

INTERFACES_POLICY_UPDATE_KEYS = {
    "policy_version", "trained_at", "validation_score", "previous_version", "deployed"
}


class TestInterfacesSchemaRoundTrips:
    """
    Schema round-trip tests: construct each schema in Python, serialize to JSON,
    deserialize back, confirm all required keys present and types correct.
    Covers all 4 schemas from INTERFACES.md.
    """

    def test_detection_event_schema_round_trip(self):
        """Schema 1: Detection Event (edge → cloud)."""
        event = {
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
        # Key completeness
        assert set(event.keys()) == INTERFACES_EVENT_KEYS
        # JSON round-trip
        serialized = json.dumps(event)
        deserialized = json.loads(serialized)
        assert deserialized == event
        # Type assertions
        assert isinstance(deserialized["confidence"], float)
        assert isinstance(deserialized["frame_count_triggered"], int)
        assert isinstance(deserialized["clip_captured"], bool)
        assert deserialized["event_type"] in ("ppe_violation", "zone_intrusion")

    def test_detection_event_zone_intrusion_variant(self):
        """Schema 1 variant: zone_intrusion with person_in_zone class."""
        event = {
            "camera_id": "cam_north_01",
            "zone_id": "zone_b",
            "event_type": "zone_intrusion",
            "class": "person_in_zone",
            "confidence": 0.93,
            "tracked_id": "person_203",
            "timestamp": "2026-09-22T10:15:45Z",
            "frame_count_triggered": 6,
            "clip_captured": True,
        }
        assert set(event.keys()) == INTERFACES_EVENT_KEYS
        assert event["frame_count_triggered"] >= 3, (
            "INTERFACES.md: frame_count_triggered should be >= 3 (debounce count)"
        )
        serialized = json.loads(json.dumps(event))
        assert serialized == event

    def test_operator_feedback_schema_round_trip(self):
        """Schema 2: Operator Feedback (dashboard → cloud)."""
        feedback = {
            "event_id": "evt_98213",
            "feedback": "confirmed",
            "operator_id": "op_04",
            "timestamp": "2026-09-05T14:33:02Z",
        }
        assert set(feedback.keys()) == INTERFACES_FEEDBACK_KEYS
        assert feedback["feedback"] in ("confirmed", "false_alarm")
        serialized = json.loads(json.dumps(feedback))
        assert serialized == feedback

    def test_operator_feedback_false_alarm_variant(self):
        """Schema 2 variant: false_alarm feedback."""
        feedback = {
            "event_id": "evt_55512",
            "feedback": "false_alarm",
            "operator_id": "op_07",
            "timestamp": "2026-09-22T10:16:00Z",
        }
        assert set(feedback.keys()) == INTERFACES_FEEDBACK_KEYS
        assert feedback["feedback"] == "false_alarm"
        pydantic_model = OperatorFeedbackCreate(**{
            "event_id": feedback["event_id"],
            "feedback": feedback["feedback"],
            "operator_id": feedback["operator_id"],
            "timestamp": feedback["timestamp"],
        })
        assert pydantic_model.feedback == "false_alarm"

    def test_bandit_decision_output_schema_round_trip(self):
        """Schema 3: Bandit Decision Output (cloud, internal)."""
        decision = {
            "event_id": "evt_98213",
            "action": "escalate",
            "policy_version": "policy_v7",
            "threshold_used": 0.75,
        }
        assert set(decision.keys()) == INTERFACES_BANDIT_DECISION_KEYS
        assert decision["action"] in ("escalate", "log_only", "adjust_threshold")
        serialized = json.loads(json.dumps(decision))
        assert serialized == decision
        # Validate through Pydantic model
        pydantic_model = BanditDecisionOutput(**decision)
        assert pydantic_model.action == "escalate"
        assert pydantic_model.threshold_used == 0.75

    def test_bandit_decision_all_actions_are_valid(self):
        """Schema 3: all three valid action values round-trip correctly."""
        for action in ("escalate", "log_only", "adjust_threshold"):
            decision = {
                "event_id": f"evt_{action}",
                "action": action,
                "policy_version": "policy_v1",
                "threshold_used": 0.75,
            }
            model = BanditDecisionOutput(**decision)
            assert model.action == action

    def test_policy_update_record_schema_round_trip(self):
        """Schema 4: Policy Update Record (for versioning/rollback)."""
        record = {
            "policy_version": "policy_v8",
            "trained_at": "2026-09-05T18:00:00Z",
            "validation_score": 0.91,
            "previous_version": "policy_v7",
            "deployed": True,
        }
        assert set(record.keys()) == INTERFACES_POLICY_UPDATE_KEYS
        assert isinstance(record["deployed"], bool)
        assert 0.0 <= record["validation_score"] <= 1.0
        serialized = json.loads(json.dumps(record))
        assert serialized == record
        # Validate through Pydantic model
        pydantic_model = PolicyUpdateRecord(**record)
        assert pydantic_model.deployed is True

    def test_policy_update_record_not_deployed_variant(self):
        """Schema 4: deployed=False case (failed validation gate)."""
        record = {
            "policy_version": "policy_v9_candidate",
            "trained_at": "2026-09-22T12:00:00Z",
            "validation_score": 0.55,
            "previous_version": "policy_v8",
            "deployed": False,
        }
        model = PolicyUpdateRecord(**record)
        assert model.deployed is False
        assert model.validation_score < 0.70  # below typical gate threshold

    def test_bandit_predict_produces_interfaces_compliant_output(self):
        """
        ContextualBandit.predict() output must satisfy INTERFACES.md Schema 3
        using exact schema key names and value ranges.
        """
        bandit = ContextualBandit(strategy="linucb", policy_version="policy_v7")
        event = {
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
        decision = bandit.predict(event, event_id="evt_98213")
        assert set(decision.keys()) == INTERFACES_BANDIT_DECISION_KEYS
        assert decision["event_id"] == "evt_98213"
        assert decision["action"] in ("escalate", "log_only", "adjust_threshold")
        assert decision["policy_version"] == "policy_v7"
        assert isinstance(decision["threshold_used"], float)


# ════════════════════════════════════════════════════════════════════════════
# 3. RealBanditAdapter isolation tests
# ════════════════════════════════════════════════════════════════════════════

class TestRealBanditAdapterIsolation:
    """
    Verify RealBanditAdapter wires correctly to the real ContextualBandit —
    not the mock. These tests work directly on the adapter without HTTP.
    """

    def test_active_adapter_is_real_not_mock(self):
        """The singleton returned by get_bandit_adapter() must be RealBanditAdapter."""
        adapter = get_bandit_adapter()
        assert isinstance(adapter, RealBanditAdapter), (
            f"Expected RealBanditAdapter, got {type(adapter).__name__}. "
            "Check get_bandit_adapter() factory in cloud/backend/adapter.py."
        )

    def test_adapter_has_real_bandit_instance(self):
        """RealBanditAdapter must expose a real ContextualBandit."""
        adapter = get_bandit_adapter()
        assert isinstance(adapter, RealBanditAdapter)
        assert hasattr(adapter, "bandit")
        assert isinstance(adapter.bandit, ContextualBandit)

    def test_adapter_policy_version_is_not_mock(self):
        """After warm-start, policy_version should be 'policy_v2', never 'v1.0.0-mock'."""
        adapter = get_bandit_adapter()
        assert isinstance(adapter, RealBanditAdapter)
        assert adapter.bandit.policy_version != "v1.0.0-mock", (
            "Bandit still shows mock policy version — warm_start() may not have run"
        )

    def test_adapter_decide_returns_bandit_decision_output(self):
        """decide() must return a BanditDecisionOutput Pydantic model."""
        adapter = get_bandit_adapter()
        event = DetectionEventCreate(**{
            "camera_id": "cam_test",
            "zone_id": "zone_test",
            "event_type": "ppe_violation",
            "class": "no_vest",
            "confidence": 0.85,
            "tracked_id": "person_1",
            "timestamp": "2026-09-22T10:00:00Z",
            "frame_count_triggered": 4,
            "clip_captured": False,
        })
        decision = adapter.decide(event, event_id="test_evt_001")
        assert isinstance(decision, BanditDecisionOutput)
        assert decision.event_id == "test_evt_001"
        assert decision.action in ACTIONS

    def test_adapter_class_name_mapping(self):
        """
        Pydantic stores 'class' as class_name internally; _event_to_dict()
        must map it back to the 'class' key that bandit.extract_features() reads.
        Without this mapping, the bandit always sees an empty class and produces
        incorrect one-hot encoding.
        """
        adapter = get_bandit_adapter()
        event = DetectionEventCreate(**{
            "camera_id": "cam_01",
            "zone_id": "zone_a",
            "event_type": "ppe_violation",
            "class": "no_gloves",
            "confidence": 0.88,
            "tracked_id": "person_5",
            "timestamp": "2026-09-22T10:00:00Z",
            "frame_count_triggered": 3,
            "clip_captured": False,
        })
        event_dict = adapter._event_to_dict(event)
        assert "class" in event_dict, (
            "'class' key missing from _event_to_dict output — bandit will not see violation class"
        )
        assert event_dict["class"] == "no_gloves", (
            f"Expected class='no_gloves', got '{event_dict.get('class')}'"
        )

    def test_adapter_submit_feedback_calls_bandit_update(self):
        """submit_feedback() must cause bandit pending_events to decrease by 1."""
        adapter = get_bandit_adapter()

        # First predict an event to register it in pending_events
        event = DetectionEventCreate(**{
            "camera_id": "cam_fb",
            "zone_id": "zone_fb",
            "event_type": "zone_intrusion",
            "class": "person_in_zone",
            "confidence": 0.90,
            "tracked_id": "person_99",
            "timestamp": "2026-09-22T10:00:00Z",
            "frame_count_triggered": 5,
            "clip_captured": True,
        })
        adapter.decide(event, event_id="evt_feedback_test_unique_001")
        assert "evt_feedback_test_unique_001" in adapter.bandit.pending_events

        feedback = OperatorFeedbackCreate(
            event_id="evt_feedback_test_unique_001",
            feedback="confirmed",
            operator_id="op_test",
            timestamp="2026-09-22T10:01:00Z",
        )
        adapter.submit_feedback(feedback)
        assert "evt_feedback_test_unique_001" not in adapter.bandit.pending_events, (
            "Event still in pending_events after feedback — bandit.update() may not have been called"
        )


# ════════════════════════════════════════════════════════════════════════════
# 4. Federation weight serialization round-trip
# ════════════════════════════════════════════════════════════════════════════

class TestFederationWeightRoundTrip:
    """
    Verify PolicyWeightAdapter.bandit_to_weights / weights_to_bandit preserve
    the full A/b matrix state exactly. This confirms that FedAvg is aggregating
    real policy parameters, not placeholder values.

    Does NOT duplicate test_federated.py's FedAvg math or dict_to_weights tests.
    """

    def test_bandit_to_weights_produces_6_arrays(self):
        """bandit_to_weights() must return 6 arrays (A+b for each of 3 actions)."""
        bandit = ContextualBandit(strategy="linucb")
        weights = PolicyWeightAdapter.bandit_to_weights(bandit)
        assert len(weights) == 6

    def test_weight_arrays_have_correct_shapes(self):
        """A arrays must be (256,), b arrays must be (16,)."""
        bandit = ContextualBandit(strategy="linucb")
        weights = PolicyWeightAdapter.bandit_to_weights(bandit)
        for i in range(3):
            assert weights[i * 2].shape == (256,), f"A_{ACTIONS[i]} wrong shape"
            assert weights[i * 2 + 1].shape == (16,), f"b_{ACTIONS[i]} wrong shape"

    def test_weight_arrays_are_all_float64(self):
        """All weight arrays must be float64 — no strings, no object arrays."""
        bandit = ContextualBandit(strategy="linucb")
        weights = PolicyWeightAdapter.bandit_to_weights(bandit)
        for i, w in enumerate(weights):
            assert w.dtype == np.float64, f"Array {i} dtype is {w.dtype}, expected float64"

    def test_round_trip_preserves_matrices_exactly(self):
        """
        Serialize a bandit → weights → new bandit → verify A/b match exactly.
        This is the key fidelity check: FedAvg must be working on the real data.
        """
        # Create a bandit and run a real update to make it non-identity
        bandit_src = ContextualBandit(strategy="linucb", random_state=42)
        event = {"event_type": "ppe_violation", "class": "no_helmet",
                 "confidence": 0.91, "frame_count_triggered": 5}
        bandit_src.predict(event, event_id="rt_test_001")
        bandit_src.update("rt_test_001", "confirmed")

        # Serialize
        weights = PolicyWeightAdapter.bandit_to_weights(bandit_src)

        # Deserialize into a fresh bandit
        bandit_dst = ContextualBandit(strategy="linucb", random_state=42)
        PolicyWeightAdapter.weights_to_bandit(weights, bandit_dst)

        # Verify exact match
        for action in ACTIONS:
            np.testing.assert_array_equal(
                bandit_src.A[action], bandit_dst.A[action],
                err_msg=f"A[{action}] mismatch after round-trip"
            )
            np.testing.assert_array_equal(
                bandit_src.b[action], bandit_dst.b[action],
                err_msg=f"b[{action}] mismatch after round-trip"
            )

    def test_only_numeric_values_in_weights(self):
        """
        Privacy check: all weight values are finite numbers.
        No event_id strings, camera IDs, feedback text, or timestamps
        can be serialized into the weight arrays.
        """
        adapter = get_bandit_adapter()
        weights = PolicyWeightAdapter.bandit_to_weights(adapter.bandit)
        for i, w in enumerate(weights):
            assert np.isfinite(w).all(), f"Non-finite values in weight array {i}: {w[~np.isfinite(w)]}"
            # No string/object dtypes
            assert w.dtype.kind in ("f", "i"), (
                f"Array {i} has non-numeric dtype {w.dtype} — "
                "strings or objects must never appear in federated weights"
            )

    def test_weights_to_bandit_graceful_on_empty_input(self):
        """weights_to_bandit() with empty input must not crash or corrupt state."""
        bandit = ContextualBandit(strategy="linucb")
        A_before = {a: bandit.A[a].copy() for a in ACTIONS}
        PolicyWeightAdapter.weights_to_bandit([], bandit)
        # State must be unchanged
        for action in ACTIONS:
            np.testing.assert_array_equal(bandit.A[action], A_before[action])
