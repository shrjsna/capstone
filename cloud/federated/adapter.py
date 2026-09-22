"""
cloud/federated/adapter.py
Serialization adapter for Federated Learning policy weight vectors.

STRICT PRIVACY GUARANTEE:
Only numeric policy weights/parameters cross site boundaries.
Raw detection events, feedback records, and video streams NEVER cross this boundary.

Integration status (2026-09-22):
  PolicyWeightAdapter now serializes the real ContextualBandit A/b matrices
  (cloud/decision_layer/bandit.py) rather than the previous 5-element placeholder.
  This captures the full learned policy state for genuine FedAvg aggregation.

  Weight vector format per site:
    For each of the 3 actions (escalate, log_only, adjust_threshold):
      - A_action: flattened (16×16) precision matrix  → 256 float64 values
      - b_action: flattened (16×1) response vector    → 16  float64 values
    Total: 3 × (256 + 16) = 816 values across 6 arrays

    weights[0] = A_escalate        (256,)
    weights[1] = b_escalate        (16,)
    weights[2] = A_log_only        (256,)
    weights[3] = b_log_only        (16,)
    weights[4] = A_adjust_threshold (256,)
    weights[5] = b_adjust_threshold (16,)
"""

from typing import List, Dict, Any, TYPE_CHECKING
import numpy as np

if TYPE_CHECKING:
    from cloud.decision_layer.bandit import ContextualBandit

ACTIONS = ["escalate", "log_only", "adjust_threshold"]
FEATURE_DIM = 16


class PolicyWeightAdapter:
    """
    Adapter for serializing/deserializing ContextualBandit policy state as
    NumPy weight arrays suitable for Flower FedAvg aggregation.

    PRIVACY NOTE: Only the numeric A/b matrices are transmitted.
    No event data, timestamps, feedback text, camera IDs, or operator
    information is included in any weight vector.
    """

    @staticmethod
    def bandit_to_weights(bandit: "ContextualBandit") -> List[np.ndarray]:
        """
        Serialize a live ContextualBandit instance into a list of NumPy arrays
        for Flower FL transmission.

        Returns 6 arrays: [A_escalate, b_escalate, A_log_only, b_log_only,
                            A_adjust_threshold, b_adjust_threshold]
        """
        weights = []
        for action in ACTIONS:
            weights.append(bandit.A[action].flatten().astype(np.float64))   # (256,)
            weights.append(bandit.b[action].flatten().astype(np.float64))   # (16,)
        return weights

    @staticmethod
    def weights_to_bandit(weights: List[np.ndarray], bandit: "ContextualBandit") -> None:
        """
        Deserialize Flower weight arrays back into a live ContextualBandit,
        updating its A/b matrices in place.

        Args:
            weights: 6-element list from bandit_to_weights() or FedAvg aggregation.
            bandit: ContextualBandit instance to update in-place.
        """
        if not weights or len(weights) < 6:
            return  # Graceful no-op on malformed payload

        for i, action in enumerate(ACTIONS):
            A_flat = weights[i * 2]
            b_flat = weights[i * 2 + 1]
            bandit.A[action] = A_flat.reshape(FEATURE_DIM, FEATURE_DIM).astype(np.float64)
            bandit.b[action] = b_flat.reshape(FEATURE_DIM, 1).astype(np.float64)

    # ── Legacy compatibility: threshold-dict format ──────────────────────────
    # Retained so flower_client.py (which uses dict_to_weights/weights_to_dict
    # on its local threshold dict) keeps working without changes to the network
    # layer. The threshold dict is a simple summary extracted from bandit.thresholds;
    # it is NOT used for the real A/b federated aggregation path above.

    @staticmethod
    def dict_to_weights(thresholds_dict: Dict[str, float]) -> List[np.ndarray]:
        """
        Legacy: convert a flat threshold dictionary to a 5-element weight vector.
        Used by flower_client.py for its local-state fit() step.
        Format: [zone_a, zone_b, default, learning_rate, exploration_rate]
        """
        zone_a = thresholds_dict.get("zone_a", 0.70)
        zone_b = thresholds_dict.get("zone_b", 0.75)
        default_val = thresholds_dict.get("default", 0.70)
        weights_array = np.array([zone_a, zone_b, default_val, 0.01, 0.10], dtype=np.float32)
        return [weights_array]

    @staticmethod
    def weights_to_dict(weights: List[np.ndarray]) -> Dict[str, float]:
        """
        Legacy: convert a 5-element weight vector back into a threshold dictionary.
        Used by flower_client.py to apply received global weights locally.
        """
        if not weights or len(weights) == 0:
            return {"zone_a": 0.70, "zone_b": 0.75, "default": 0.70}
        arr = weights[0].flatten()
        return {
            "zone_a": float(round(arr[0], 3)),
            "zone_b": float(round(arr[1], 3)),
            "default": float(round(arr[2], 3)),
        }
