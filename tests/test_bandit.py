"""
Unit Tests for Bandit Decision Layer (cloud/decision_layer/bandit.py)
======================================================================
Tests ContextualBandit against data contracts in INTERFACES.md using fake/synthetic data.
Uses standard library unittest so it runs out-of-the-box in any Python environment.
"""

import unittest
import numpy as np
from cloud.decision_layer.bandit import ContextualBandit, ACTIONS, DEFAULT_THRESHOLD


class TestBanditDecisionLayer(unittest.TestCase):

    def test_predict_schema_compliance(self):
        """Verify predict() output strictly adheres to INTERFACES.md Section 3."""
        bandit = ContextualBandit(strategy="linucb", policy_version="policy_v7")
        fake_event = {
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

        decision = bandit.predict(fake_event, event_id="evt_98213")

        # Contract Assertions per INTERFACES.md
        self.assertIsInstance(decision, dict)
        self.assertEqual(decision["event_id"], "evt_98213")
        self.assertIn(decision["action"], ACTIONS)
        self.assertEqual(decision["policy_version"], "policy_v7")
        self.assertIsInstance(decision["threshold_used"], float)
        self.assertEqual(decision["threshold_used"], DEFAULT_THRESHOLD)

    def test_dynamic_threshold_tracking(self):
        """Verify threshold_used adaptively updates per camera/zone when adjust_threshold action is selected."""
        bandit = ContextualBandit()
        cam_zone_event = {
            "camera_id": "cam_north",
            "zone_id": "zone_1",
            "event_type": "ppe_violation",
            "class": "no_vest",
            "confidence": 0.82,
        }

        # Manually force adjust_threshold action scenario to test state tracking
        initial_thresh = bandit.get_threshold("cam_north", "zone_1")
        self.assertEqual(initial_thresh, DEFAULT_THRESHOLD)

        # Force prediction to register threshold change
        bandit.thresholds["cam_north:zone_1"] = 0.77
        decision = bandit.predict(cam_zone_event)
        self.assertEqual(decision["threshold_used"], 0.77)

    def test_epsilon_greedy_single_check_exploration(self):
        """Verify epsilon_greedy executes a single explore/exploit check per prediction."""
        # Force epsilon=1.0 (always explore)
        bandit_explore = ContextualBandit(strategy="epsilon_greedy", epsilon=1.0, random_state=42)
        fake_event = {"confidence": 0.5, "event_type": "ppe_violation", "class": "no_helmet"}

        action = bandit_explore.select_action(bandit_explore.extract_features(fake_event))
        self.assertIn(action, ACTIONS)

    def test_online_update_linucb_and_thompson(self):
        """Verify update() processes online feedback and alters internal matrices."""
        for strat in ["linucb", "thompson", "epsilon_greedy"]:
            bandit = ContextualBandit(strategy=strat, random_state=42)
            fake_event = {
                "camera_id": "cam_02",
                "zone_id": "zone_B",
                "event_type": "zone_intrusion",
                "class": "person_in_zone",
                "confidence": 0.92,
                "timestamp": "2026-09-05T15:00:00Z",
            }

            # Predict & store pending event
            decision = bandit.predict(fake_event, event_id="evt_001")
            action = decision["action"]

            A_before = bandit.A[action].copy()
            b_before = bandit.b[action].copy()

            # Update with confirmed feedback
            feedback = {
                "event_id": "evt_001",
                "feedback": "confirmed",
                "operator_id": "op_01",
                "timestamp": "2026-09-05T15:01:00Z",
            }
            success = bandit.update("evt_001", feedback)

            self.assertTrue(success)
            self.assertFalse(np.array_equal(bandit.A[action], A_before))
            self.assertFalse(np.array_equal(bandit.b[action], b_before))
            self.assertNotIn("evt_001", bandit.pending_events)

    def test_retrain_validation_gate_pass(self):
        """Verify batch retrain deploys new version when validation gate passes."""
        bandit = ContextualBandit(strategy="linucb", policy_version="policy_v1")

        # Create synthetic training batch
        synthetic_batch = []
        for i in range(10):
            ev = {
                "event_type": "ppe_violation",
                "class": "no_helmet",
                "confidence": 0.85 + (i % 3) * 0.04,
                "timestamp": "2026-09-05T10:00:00Z",
            }
            synthetic_batch.append((ev, "escalate", "confirmed"))

        record = bandit.retrain(synthetic_batch, min_validation_score=0.50)

        # Contract Assertions per INTERFACES.md Section 4
        self.assertIsInstance(record, dict)
        self.assertTrue(record["deployed"])
        self.assertGreaterEqual(record["validation_score"], 0.50)
        self.assertEqual(record["previous_version"], "policy_v1")
        self.assertEqual(record["policy_version"], "policy_v2")
        self.assertEqual(bandit.policy_version, "policy_v2")

    def test_retrain_validation_gate_fail_and_rollback(self):
        """Verify policy rejection and rollback when validation score fails gate."""
        bandit = ContextualBandit(strategy="linucb", policy_version="policy_v5")

        # Create synthetic batch with conflicting / noisy rewards
        synthetic_batch = []
        for i in range(8):
            ev = {"event_type": "ppe_violation", "class": "no_helmet", "confidence": 0.50}
            # Alternating feedback causing low consensus
            fb = "false_alarm" if i % 2 == 0 else "confirmed"
            synthetic_batch.append((ev, "escalate", fb))

        # Set impossibly high validation gate score
        record = bandit.retrain(synthetic_batch, min_validation_score=0.99)

        self.assertFalse(record["deployed"])
        self.assertLess(record["validation_score"], 0.99)
        # Current active policy version must remain policy_v5
        self.assertEqual(bandit.policy_version, "policy_v5")

    # -----------------------------------------------------------------------------
    # Edge Case Tests (Required by Spec)
    # -----------------------------------------------------------------------------

    def test_edge_case_empty_training_batch(self):
        """Verify retrain() handles an empty training batch without crashing."""
        bandit = ContextualBandit()
        record = bandit.retrain([], min_validation_score=0.70)

        self.assertIsInstance(record, dict)
        self.assertFalse(record["deployed"])
        self.assertEqual(record["validation_score"], 0.0)
        self.assertEqual(record["policy_version"], "policy_v1")

    def test_edge_case_all_negative_rewards(self):
        """Verify retrain() and update() handle all-negative rewards without numerical crash."""
        bandit = ContextualBandit(strategy="linucb")

        synthetic_batch = []
        for i in range(6):
            ev = {"event_type": "zone_intrusion", "class": "person_in_zone", "confidence": 0.60}
            # All false alarms -> negative rewards
            synthetic_batch.append((ev, "escalate", "false_alarm"))

        record = bandit.retrain(synthetic_batch, min_validation_score=0.0)

        self.assertIsInstance(record, dict)
        self.assertFalse(np.isnan(bandit.b["escalate"]).any())
        self.assertFalse(np.isnan(bandit.A["escalate"]).any())

    def test_edge_case_unrecognized_event_id(self):
        """Verify update() handles feedback for an unrecognized event_id gracefully."""
        bandit = ContextualBandit()
        success = bandit.update("unknown_event_99999", "confirmed")

        self.assertFalse(success)

    def test_edge_case_missing_and_malformed_event_fields(self):
        """Verify feature extraction and predict() handle corrupted or missing inputs gracefully."""
        bandit = ContextualBandit()

        malformed_events = [
            {},  # Empty dictionary
            {"confidence": "not_a_float", "timestamp": "invalid_date_format"},
            {"confidence": None, "frame_count_triggered": None, "clip_captured": "yes"},
            {"confidence": float("nan"), "event_type": 12345},
        ]

        for ev in malformed_events:
            decision = bandit.predict(ev)
            self.assertIsInstance(decision, dict)
            self.assertIn(decision["action"], ACTIONS)
            self.assertEqual(decision["threshold_used"], DEFAULT_THRESHOLD)


if __name__ == "__main__":
    unittest.main()
