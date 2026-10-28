"""
Federated Learning Client — BanditFlowerClient
================================================
Wraps a ContextualBandit instance as a Flower NumPyClient so its learned
weight matrices (A, b) can participate in FedAvg aggregation.

How it works
------------
Each deployment site runs one instance of this client.
The Flower server calls get_parameters() to collect local weights, runs
FedAvg to average them across all sites, then calls set_parameters() to
push the aggregated global weights back.

Parameters serialised (6 numpy arrays, in fixed order):
  [0] A_escalate          (d x d)
  [1] b_escalate          (d x 1)
  [2] A_log_only          (d x d)
  [3] b_log_only          (d x 1)
  [4] A_adjust_threshold  (d x d)
  [5] b_adjust_threshold  (d x 1)

Design decision documented in docs/decisions.md:
  2026-10-28 — Federation simulates 2+ sites on one machine; only weights
  (not raw video or event data) are ever shared, preserving data privacy.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np

import flwr as fl

from cloud.decision_layer.bandit import ACTIONS, ContextualBandit


def bandit_to_parameters(bandit: ContextualBandit) -> List[np.ndarray]:
    """Serialise all bandit weight matrices into a flat list of numpy arrays."""
    params = []
    for action in ACTIONS:
        params.append(bandit.A[action].copy())
        params.append(bandit.b[action].copy())
    return params  # length = 2 * len(ACTIONS) = 6


def parameters_to_bandit(params: List[np.ndarray], bandit: ContextualBandit) -> None:
    """Load a flat list of numpy arrays back into a bandit's weight matrices (in-place)."""
    for i, action in enumerate(ACTIONS):
        bandit.A[action] = params[2 * i].copy()
        bandit.b[action] = params[2 * i + 1].copy()


class BanditFlowerClient(fl.client.NumPyClient):
    """
    Flower client wrapping a single ContextualBandit deployment site.

    Args:
        site_id:      Human-readable name for this site (e.g. "site_factory_a").
        bandit:       Pre-initialised ContextualBandit for this site.
        local_data:   Local training batch  [(event_dict, action, feedback_str), ...]
                      Collected from real or simulated operator feedback at this site.
    """

    def __init__(
        self,
        site_id: str,
        bandit: ContextualBandit,
        local_data: List[Tuple[Dict, str, str]],
    ) -> None:
        self.site_id = site_id
        self.bandit = bandit
        self.local_data = local_data

    # ── Flower API ──────────────────────────────────────────────────────────

    def get_parameters(self, config: Dict) -> List[np.ndarray]:
        """Return current local weight matrices to the server."""
        return bandit_to_parameters(self.bandit)

    def fit(
        self,
        parameters: List[np.ndarray],
        config: Dict,
    ) -> Tuple[List[np.ndarray], int, Dict]:
        """
        1. Load the global weights pushed down by the server.
        2. Run one local retrain round on this site's feedback data.
        3. Return the updated local weights back to the server.
        """
        # Load global weights
        parameters_to_bandit(parameters, self.bandit)

        # Local training — one retrain round on site-local feedback
        if self.local_data:
            self.bandit.retrain(
                training_batch=self.local_data,
                min_validation_score=0.0,   # Gate off during FL rounds — server aggregates
            )

        return bandit_to_parameters(self.bandit), len(self.local_data), {"site": self.site_id}

    def evaluate(
        self,
        parameters: List[np.ndarray],
        config: Dict,
    ) -> Tuple[float, int, Dict]:
        """
        Evaluate the global aggregated weights on this site's local data.
        Returns (loss, num_examples, metrics).
        Loss = 1 - validation_score (lower is better, Flower convention).
        """
        parameters_to_bandit(parameters, self.bandit)

        if not self.local_data:
            return 1.0, 0, {"site": self.site_id, "validation_score": 0.0}

        record = self.bandit.retrain(
            training_batch=self.local_data,
            min_validation_score=0.0,
        )
        val_score = record.get("validation_score", 0.0)
        loss = round(1.0 - val_score, 4)

        return loss, len(self.local_data), {
            "site": self.site_id,
            "validation_score": val_score,
        }
