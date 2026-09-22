"""
cloud/federated/adapter.py
Serialization adapter for Federated Learning policy weight vectors.

STRICT PRIVACY GUARANTEE:
Only numeric policy weights/parameters cross site boundaries.
Raw detection events, feedback records, and video streams NEVER cross this boundary.
"""

from typing import List, Dict, Any
import numpy as np


class PolicyWeightAdapter:
    """
    Adapter for converting between local bandit policy parameters and NumPy arrays used by Flower FL.
    """

    @staticmethod
    def dict_to_weights(thresholds_dict: Dict[str, float]) -> List[np.ndarray]:
        """
        Converts policy threshold dictionary to a list of NumPy arrays (Flower weight format).
        Placeholder format: 5 float values [zone_a, zone_b, default, learning_rate, exploration_rate]
        """
        zone_a = thresholds_dict.get("zone_a", 0.70)
        zone_b = thresholds_dict.get("zone_b", 0.75)
        default_val = thresholds_dict.get("default", 0.70)

        # 5-parameter numerical weight vector
        weights_array = np.array([zone_a, zone_b, default_val, 0.01, 0.10], dtype=np.float32)
        return [weights_array]

    @staticmethod
    def weights_to_dict(weights: List[np.ndarray]) -> Dict[str, float]:
        """
        Converts Flower NumPy weight arrays back into policy threshold dictionary.
        """
        if not weights or len(weights) == 0:
            return {"zone_a": 0.70, "zone_b": 0.75, "default": 0.70}

        arr = weights[0].flatten()
        return {
            "zone_a": float(round(arr[0], 3)),
            "zone_b": float(round(arr[1], 3)),
            "default": float(round(arr[2], 3)),
        }
