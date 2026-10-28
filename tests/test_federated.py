"""
Federation Tests
================
Unit tests for cloud/federated/client.py — BanditFlowerClient.
Tests serialisation, deserialisation, local fit, and evaluate.
Does NOT start a real Flower server (no network). All in-process.
"""

import unittest
import numpy as np

from cloud.decision_layer.bandit import ContextualBandit, ACTIONS, FEATURE_DIM
from cloud.federated.client import (
    BanditFlowerClient,
    bandit_to_parameters,
    parameters_to_bandit,
)


def _make_trained_bandit(policy_version: str = "policy_v1") -> ContextualBandit:
    """Return a bandit with some non-identity matrices from synthetic data."""
    b = ContextualBandit(strategy="linucb", policy_version=policy_version, random_state=0)
    ev = {"event_type": "ppe_violation", "class": "no_helmet", "confidence": 0.85,
          "frame_count_triggered": 4, "clip_captured": True}
    for i in range(5):
        eid = f"test_evt_{i}"
        b.predict(ev, event_id=eid)
        b.update(eid, "confirmed")
    return b


def _make_local_data():
    return [
        ({"event_type": "ppe_violation", "class": "no_helmet", "confidence": 0.87,
          "frame_count_triggered": 5, "clip_captured": True},
         "escalate", "confirmed"),
    ] * 6


class TestParameterSerialisation(unittest.TestCase):

    def test_bandit_to_parameters_length(self):
        """Should return 6 arrays: (A, b) x 3 actions."""
        b = ContextualBandit()
        params = bandit_to_parameters(b)
        self.assertEqual(len(params), 6)

    def test_bandit_to_parameters_shapes(self):
        """A arrays are (d,d), b arrays are (d,1)."""
        b = ContextualBandit()
        params = bandit_to_parameters(b)
        d = FEATURE_DIM
        for i in range(3):
            self.assertEqual(params[2 * i].shape,     (d, d), f"A[{i}] wrong shape")
            self.assertEqual(params[2 * i + 1].shape, (d, 1), f"b[{i}] wrong shape")

    def test_round_trip_identity(self):
        """parameters_to_bandit(bandit_to_parameters(b)) should restore exact values."""
        original = _make_trained_bandit()
        params = bandit_to_parameters(original)

        restored = ContextualBandit()
        parameters_to_bandit(params, restored)

        for action in ACTIONS:
            self.assertTrue(np.allclose(original.A[action], restored.A[action]),
                            f"A[{action}] mismatch after round-trip")
            self.assertTrue(np.allclose(original.b[action], restored.b[action]),
                            f"b[{action}] mismatch after round-trip")

    def test_parameters_are_copies_not_views(self):
        """Mutating returned params must not affect the original bandit."""
        b = _make_trained_bandit()
        params = bandit_to_parameters(b)
        A_before = b.A["escalate"].copy()

        params[0] *= 999   # mutate returned array

        self.assertTrue(np.allclose(b.A["escalate"], A_before),
                        "bandit_to_parameters returned a view, not a copy")


class TestBanditFlowerClient(unittest.TestCase):

    def _make_client(self, site_id="site_test"):
        bandit = ContextualBandit(strategy="linucb", policy_version="policy_v1", random_state=1)
        data = _make_local_data()
        return BanditFlowerClient(site_id=site_id, bandit=bandit, local_data=data), bandit

    def test_get_parameters_returns_list(self):
        client, _ = self._make_client()
        params = client.get_parameters(config={})
        self.assertIsInstance(params, list)
        self.assertEqual(len(params), 6)

    def test_fit_returns_correct_structure(self):
        """fit() must return (params, num_examples, metrics_dict)."""
        client, _ = self._make_client()
        init_params = client.get_parameters(config={})
        result = client.fit(init_params, config={})
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 3)
        params_out, n_samples, metrics = result
        self.assertIsInstance(params_out, list)
        self.assertEqual(len(params_out), 6)
        self.assertEqual(n_samples, len(_make_local_data()))
        self.assertIn("site", metrics)

    def test_fit_updates_weights(self):
        """After fit(), returned weights should differ from identity (local training happened)."""
        client, bandit = self._make_client()
        identity_params = [np.eye(FEATURE_DIM)] * 3 + [np.zeros((FEATURE_DIM, 1))] * 3
        # Build correctly ordered params: A0, b0, A1, b1, A2, b2
        flat = []
        for i in range(3):
            flat.append(np.eye(FEATURE_DIM))
            flat.append(np.zeros((FEATURE_DIM, 1)))

        params_out, _, _ = client.fit(flat, config={})
        # At least one A matrix should now differ from identity
        any_changed = any(
            not np.allclose(params_out[2 * i], np.eye(FEATURE_DIM))
            for i in range(3)
        )
        self.assertTrue(any_changed, "fit() did not update any weight matrix")

    def test_evaluate_returns_correct_structure(self):
        """evaluate() must return (loss, num_examples, metrics_dict)."""
        client, _ = self._make_client()
        params = client.get_parameters(config={})
        result = client.evaluate(params, config={})
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 3)
        loss, n_samples, metrics = result
        self.assertIsInstance(loss, float)
        self.assertGreaterEqual(loss, 0.0)
        self.assertLessEqual(loss, 1.0)
        self.assertIn("validation_score", metrics)

    def test_evaluate_empty_data(self):
        """evaluate() with no local data must not crash and return loss=1.0."""
        bandit = ContextualBandit()
        client = BanditFlowerClient(site_id="empty_site", bandit=bandit, local_data=[])
        params = client.get_parameters(config={})
        loss, n, metrics = client.evaluate(params, config={})
        self.assertEqual(loss, 1.0)
        self.assertEqual(n, 0)

    def test_fedavg_weight_averaging(self):
        """Manual FedAvg of two bandits should produce weight between the two."""
        b1 = ContextualBandit(random_state=0)
        b2 = ContextualBandit(random_state=1)

        # Give them different data so weights differ
        ev = {"event_type": "ppe_violation", "class": "no_helmet", "confidence": 0.9}
        for i in range(4):
            eid = f"site1_evt_{i}"
            b1.predict(ev, event_id=eid)
            b1.update(eid, "confirmed")

        ev2 = {"event_type": "zone_intrusion", "class": "person_in_zone", "confidence": 0.7}
        for i in range(4):
            eid = f"site2_evt_{i}"
            b2.predict(ev2, event_id=eid)
            b2.update(eid, "false_alarm")

        p1 = bandit_to_parameters(b1)
        p2 = bandit_to_parameters(b2)

        # FedAvg: equal sample sizes → simple mean
        averaged = [(a + b) / 2.0 for a, b in zip(p1, p2)]

        # Load into new bandit
        b_global = ContextualBandit()
        from cloud.federated.client import parameters_to_bandit
        parameters_to_bandit(averaged, b_global)

        # Global A["escalate"] should be between b1 and b2 (element-wise mean)
        expected = (b1.A["escalate"] + b2.A["escalate"]) / 2.0
        self.assertTrue(np.allclose(b_global.A["escalate"], expected),
                        "FedAvg manual average did not produce the expected mean")


if __name__ == "__main__":
    unittest.main()
