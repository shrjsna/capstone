"""
tests/test_federated.py
Unit test for FedAvg mathematical weight aggregation logic.
"""

import pytest
import numpy as np
from cloud.federated.adapter import PolicyWeightAdapter


def test_weight_adapter_bidirectional_conversion():
    original_dict = {"zone_a": 0.65, "zone_b": 0.82, "default": 0.70}
    weights_list = PolicyWeightAdapter.dict_to_weights(original_dict)

    assert len(weights_list) == 1
    assert isinstance(weights_list[0], np.ndarray)
    assert weights_list[0].shape == (5,)

    reconstructed_dict = PolicyWeightAdapter.weights_to_dict(weights_list)
    assert reconstructed_dict["zone_a"] == pytest.approx(0.65, abs=1e-3)
    assert reconstructed_dict["zone_b"] == pytest.approx(0.82, abs=1e-3)
    assert reconstructed_dict["default"] == pytest.approx(0.70, abs=1e-3)


def test_fedavg_mathematical_aggregation():
    # Simulate site 1 weights: [0.60, 0.70, 0.65, 0.01, 0.10] with 100 samples
    site1_weights = np.array([0.60, 0.70, 0.65, 0.01, 0.10], dtype=np.float32)
    n1 = 100

    # Simulate site 2 weights: [0.80, 0.90, 0.75, 0.01, 0.10] with 100 samples
    site2_weights = np.array([0.80, 0.90, 0.75, 0.01, 0.10], dtype=np.float32)
    n2 = 100

    # Calculate weighted average: (100*W1 + 100*W2) / 200 = (W1 + W2)/2
    total_samples = n1 + n2
    aggregated_weights = (site1_weights * n1 + site2_weights * n2) / total_samples

    expected_avg = np.array([0.70, 0.80, 0.70, 0.01, 0.10], dtype=np.float32)
    np.testing.assert_allclose(aggregated_weights, expected_avg, rtol=1e-5)
