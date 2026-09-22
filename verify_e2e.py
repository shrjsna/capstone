"""
verify_e2e.py — End-to-end pipeline verification (Step 3).

Runs the full pipeline in-process using FastAPI TestClient so no live server
is needed, but exercises the REAL code paths: real backend routes, real
RealBanditAdapter, real ContextualBandit.

Steps verified:
  1. Backend health check
  2. Module A simulated event (ppe_violation) → POST /events
  3. Module B simulated event (zone_intrusion) → POST /events
  4. GET /alerts — confirm both events present with correct fields
  5. Confirm real Bandit Decision Output on each event (non-mock policy_version)
  6a. POST /feedback "confirmed" for event 1 (via API)
  6b. POST /feedback "false_alarm" for event 2 (via API)
  7. Confirm bandit state changed after feedback (threshold or policy version)
  8. Federation privacy check: serialize bandit weights, confirm ONLY numeric
     arrays, NO event data, NO feedback strings, NO camera IDs
  9. Print pass/fail summary
"""

import sys
import json
import os
import importlib

# Ensure repo root on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from cloud.backend.main import app
from cloud.backend.database import get_db
from cloud.backend.models import Base, PolicyVersionModel
from cloud.backend.adapter import get_bandit_adapter, RealBanditAdapter
from cloud.federated.adapter import PolicyWeightAdapter
import numpy as np

# ── In-memory DB override ───────────────────────────────────────────────────
TEST_DB_URL = "sqlite://"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
Base.metadata.create_all(bind=engine)

# Seed policy record
db = TestingSessionLocal()
if not db.query(PolicyVersionModel).first():
    db.add(PolicyVersionModel(
        policy_version="v1.0.0-mock",
        trained_at="2026-09-22T10:00:00Z",
        validation_score=0.915,
        previous_version="v0.9.0",
        deployed=True
    ))
    db.commit()
db.close()

client = TestClient(app)

PASS = "  ✓ PASS"
FAIL = "  ✗ FAIL"
results = []

def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((name, condition, detail))
    print(f"{status}  {name}")
    if detail:
        print(f"         {detail}")
    return condition


print("\n" + "="*60)
print("END-TO-END PIPELINE VERIFICATION")
print("="*60)

# ── Step 1: Health check ────────────────────────────────────────────────────
print("\n[Step 1] Backend health check")
r = client.get("/health")
check("GET /health → 200", r.status_code == 200, f"response: {r.json()}")

# ── Step 2: Module A PPE violation event ───────────────────────────────────
print("\n[Step 2] Module A — POST ppe_violation event")
ppe_payload = {
    "camera_id": "cam_01",
    "zone_id": "zone_a",
    "event_type": "ppe_violation",
    "class": "no_helmet",
    "confidence": 0.91,
    "tracked_id": "person_142",
    "timestamp": "2026-09-22T10:15:00Z",
    "frame_count_triggered": 5,
    "clip_captured": True
}
r_ppe = client.post("/events", json=ppe_payload)
check("POST /events (PPE) → 201", r_ppe.status_code == 201)
ppe_data = r_ppe.json()
ppe_event_id = ppe_data.get("event_id", "")
check("event_id assigned (UUID)", len(ppe_event_id) == 36, f"event_id={ppe_event_id}")
check("camera_id matches", ppe_data.get("camera_id") == "cam_01")
check("class field correct", ppe_data.get("class") == "no_helmet")
check("bandit_action present", ppe_data.get("bandit_action") in ["escalate", "log_only", "adjust_threshold"],
      f"action={ppe_data.get('bandit_action')}")
check("policy_version is real (not v1.0.0-mock)", ppe_data.get("policy_version") != "v1.0.0-mock",
      f"policy_version={ppe_data.get('policy_version')}")
check("threshold_used is float ≥ 0 and ≤ 1", isinstance(ppe_data.get("threshold_used"), float) and
      0.0 <= ppe_data.get("threshold_used", -1) <= 1.0,
      f"threshold_used={ppe_data.get('threshold_used')}")
print(f"         PPE event full response: {json.dumps(ppe_data, indent=4)}")

# ── Step 3: Module B Zone intrusion event ─────────────────────────────────
print("\n[Step 3] Module B — POST zone_intrusion event")
zone_payload = {
    "camera_id": "cam_north_01",
    "zone_id": "zone_b",
    "event_type": "zone_intrusion",
    "class": "person_in_zone",
    "confidence": 0.87,
    "tracked_id": "person_203",
    "timestamp": "2026-09-22T10:15:45Z",
    "frame_count_triggered": 6,
    "clip_captured": True
}
r_zone = client.post("/events", json=zone_payload)
check("POST /events (Zone) → 201", r_zone.status_code == 201)
zone_data = r_zone.json()
zone_event_id = zone_data.get("event_id", "")
check("event_id assigned (UUID)", len(zone_event_id) == 36)
check("event_type correct", zone_data.get("event_type") == "zone_intrusion")
check("bandit_action present", zone_data.get("bandit_action") in ["escalate", "log_only", "adjust_threshold"],
      f"action={zone_data.get('bandit_action')}")
print(f"         Zone event full response: {json.dumps(zone_data, indent=4)}")

# ── Step 4: GET /alerts — both events present ──────────────────────────────
print("\n[Step 4] GET /alerts — confirm both events in feed")
r_alerts = client.get("/alerts?limit=10")
check("GET /alerts → 200", r_alerts.status_code == 200)
alerts = r_alerts.json()
check("2 events in alerts list", len(alerts) == 2, f"found {len(alerts)} alerts")
alert_ids = {a["event_id"] for a in alerts}
check("PPE event in alerts", ppe_event_id in alert_ids)
check("Zone event in alerts", zone_event_id in alert_ids)
check("All alerts have bandit_action", all(a.get("bandit_action") for a in alerts))

# ── Step 5: Bandit Decision Output verification ────────────────────────────
print("\n[Step 5] Bandit Decision Output — confirm real Module C, not mock")
adapter = get_bandit_adapter()
check("Adapter is RealBanditAdapter (not mock)", isinstance(adapter, RealBanditAdapter),
      f"type={type(adapter).__name__}")
check("Bandit policy_version is not v1.0.0-mock",
      adapter.bandit.policy_version != "v1.0.0-mock",
      f"policy_version={adapter.bandit.policy_version}")

# Capture threshold state BEFORE feedback
thresholds_before = adapter.get_zone_thresholds().copy()
pending_before = len(adapter.bandit.pending_events)
print(f"         Thresholds before feedback: {thresholds_before}")
print(f"         Pending events in bandit (awaiting feedback): {pending_before}")

# ── Step 6a: Feedback "confirmed" for PPE event ────────────────────────────
print("\n[Step 6a] POST /feedback 'confirmed' for PPE event")
fb_confirmed = {
    "event_id": ppe_event_id,
    "feedback": "confirmed",
    "operator_id": "op_demo_01",
    "timestamp": "2026-09-22T10:16:00Z"
}
r_fb1 = client.post("/feedback", json=fb_confirmed)
check("POST /feedback confirmed → 200", r_fb1.status_code == 200)
fb1_resp = r_fb1.json()
check("feedback status success", fb1_resp.get("status") == "success")
check("feedback event_id matches", fb1_resp.get("event_id") == ppe_event_id)
print(f"         Feedback response: {json.dumps(fb1_resp, indent=4)}")

# ── Step 6b: Feedback "false_alarm" for Zone event ─────────────────────────
print("\n[Step 6b] POST /feedback 'false_alarm' for Zone event")
fb_false_alarm = {
    "event_id": zone_event_id,
    "feedback": "false_alarm",
    "operator_id": "op_demo_02",
    "timestamp": "2026-09-22T10:16:15Z"
}
r_fb2 = client.post("/feedback", json=fb_false_alarm)
check("POST /feedback false_alarm → 200", r_fb2.status_code == 200)
print(f"         Feedback response: {json.dumps(r_fb2.json(), indent=4)}")

# ── Step 7: Confirm bandit state changed after feedback ────────────────────
print("\n[Step 7] Confirm bandit internal state changed after feedback")
pending_after = len(adapter.bandit.pending_events)
check("Pending events decreased (feedback consumed)", pending_after < pending_before or pending_before == 0,
      f"pending before={pending_before}, after={pending_after}")

# Verify A/b matrices changed for at least one action
# Pick the action that the PPE event used (it was stored in pending then consumed)
any_matrix_changed = False
import numpy as np
for action in ["escalate", "log_only", "adjust_threshold"]:
    # After update, A[action] should differ from identity eye(16) if it was used
    if not np.allclose(adapter.bandit.A[action], np.eye(16)):
        any_matrix_changed = True
        break
check("Bandit A/b matrices updated (non-identity after feedback)", any_matrix_changed,
      "At least one action's A matrix differs from initial identity")

# ── Step 8: Federation privacy check ──────────────────────────────────────
print("\n[Step 8] Federation privacy check")
weights = PolicyWeightAdapter.bandit_to_weights(adapter.bandit)
check("6 weight arrays returned", len(weights) == 6, f"got {len(weights)} arrays")
check("All weights are numpy arrays", all(isinstance(w, np.ndarray) for w in weights),
      "confirmed all are np.ndarray")
check("A_escalate shape (256,)", weights[0].shape == (256,), f"shape={weights[0].shape}")
check("b_escalate shape (16,)", weights[1].shape == (16,), f"shape={weights[1].shape}")
check("All values are finite floats (no NaN/Inf)", 
      all(np.isfinite(w).all() for w in weights), "all values finite")

# Confirm no string data in weights (privacy: no event IDs, camera IDs, etc.)
all_numeric = all(w.dtype in [np.float32, np.float64] for w in weights)
check("All weight arrays are numeric dtype (no strings/objects)", all_numeric,
      f"dtypes={[w.dtype for w in weights]}")

# Confirm round-trip: serialize → deserialize → check matrices match
from cloud.decision_layer.bandit import ContextualBandit
bandit_copy = ContextualBandit(strategy="linucb", policy_version="policy_v1")
PolicyWeightAdapter.weights_to_bandit(weights, bandit_copy)
round_trip_ok = True
for action in ["escalate", "log_only", "adjust_threshold"]:
    if not np.allclose(bandit_copy.A[action], adapter.bandit.A[action]):
        round_trip_ok = False
        break
    if not np.allclose(bandit_copy.b[action], adapter.bandit.b[action]):
        round_trip_ok = False
        break
check("Weight round-trip preserves exact A/b values", round_trip_ok)

# ── Summary ─────────────────────────────────────────────────────────────────
print("\n" + "="*60)
passed = sum(1 for _, ok, _ in results if ok)
failed = sum(1 for _, ok, _ in results if not ok)
print(f"E2E VERIFICATION SUMMARY: {passed} passed, {failed} failed")
print("="*60)

if failed > 0:
    print("\nFailed checks:")
    for name, ok, detail in results:
        if not ok:
            print(f"  - {name}: {detail}")
    sys.exit(1)
else:
    print("\nAll checks passed. End-to-end pipeline verified.")
    sys.exit(0)
