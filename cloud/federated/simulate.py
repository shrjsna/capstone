"""
Federation Simulation — 2-Site In-Process Demo
================================================
Simulates two factory sites (Site A and Site B) running FedAvg on their
local bandit weights — all in a single Python process using Flower's
in-process simulation API (no network sockets needed).

This is the capstone demo script. Run it with:
    python -m cloud.federated.simulate

What happens:
  Round 0  : Both sites start with cold-start identity matrices
  Round 1-3: Each site retrains locally on its own event data, then FedAvg
             averages their A and b matrices into one global policy
  Final    : Global policy is printed alongside per-site validation scores

Why FedAvg works for LinUCB
---------------------------
The optimal LinUCB weight theta* = A^{-1} b is a linear function of
the data matrices. FedAvg computes a sample-weighted mean of A and b across
sites — this is equivalent to pooling all sites' data into one model,
without any raw data ever leaving a site (privacy preserving).
"""

from __future__ import annotations

import json
from typing import List, Tuple, Dict

import numpy as np
import flwr as fl

from cloud.decision_layer.bandit import ContextualBandit, ACTIONS
from cloud.federated.client import BanditFlowerClient, bandit_to_parameters


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic local datasets — simulate what each factory site has seen
# ─────────────────────────────────────────────────────────────────────────────

def _make_site_a_data() -> List[Tuple[Dict, str, str]]:
    """
    Site A: Outdoor construction site — frequent PPE violations, high confidence.
    Operators mostly confirm escalations.
    """
    data = []
    # Confirmed PPE violations → escalate is the right call
    for _ in range(12):
        data.append((
            {"event_type": "ppe_violation", "class": "no_helmet",
             "confidence": 0.88, "frame_count_triggered": 5, "clip_captured": True},
            "escalate", "confirmed"
        ))
    # False alarm adjust_threshold events
    for _ in range(4):
        data.append((
            {"event_type": "ppe_violation", "class": "no_vest",
             "confidence": 0.52, "frame_count_triggered": 2, "clip_captured": False},
            "adjust_threshold", "false_alarm"
        ))
    return data


def _make_site_b_data() -> List[Tuple[Dict, str, str]]:
    """
    Site B: Indoor warehouse — frequent zone intrusions, mixed confidence.
    Operators see many false alarms from forklifts triggering the zone detector.
    """
    data = []
    # Confirmed zone intrusions
    for _ in range(8):
        data.append((
            {"event_type": "zone_intrusion", "class": "person_in_zone",
             "confidence": 0.79, "frame_count_triggered": 6, "clip_captured": True},
            "escalate", "confirmed"
        ))
    # Forklift false alarms → log_only is the right call
    for _ in range(8):
        data.append((
            {"event_type": "zone_intrusion", "class": "person_in_zone",
             "confidence": 0.61, "frame_count_triggered": 3, "clip_captured": False},
            "log_only", "false_alarm"
        ))
    return data


# ─────────────────────────────────────────────────────────────────────────────
# In-process simulation using fl.simulation.start_simulation
# ─────────────────────────────────────────────────────────────────────────────

def run_federation(num_rounds: int = 3) -> Dict:
    """
    Run FedAvg federation simulation across 2 simulated factory sites.

    Args:
        num_rounds: Number of FedAvg aggregation rounds.

    Returns:
        dict with final global policy weights and per-site validation scores.
    """
    print("\n" + "=" * 60)
    print("  FEDERATED LEARNING SIMULATION — Industrial Safety Bandit")
    print("=" * 60)
    print(f"  Sites   : 2 (Site A — Construction, Site B — Warehouse)")
    print(f"  Strategy: FedAvg (McMahan et al., 2017)")
    print(f"  Rounds  : {num_rounds}")
    print(f"  Privacy : Only weight matrices shared — no raw event data")
    print("=" * 60 + "\n")

    site_a_data = _make_site_a_data()
    site_b_data = _make_site_b_data()

    site_data = {
        "site_factory_a": site_a_data,
        "site_warehouse_b": site_b_data,
    }
    site_ids = list(site_data.keys())

    # One fresh bandit per site
    bandits = {
        sid: ContextualBandit(strategy="linucb", policy_version=f"local_{sid}")
        for sid in site_ids
    }

    def client_fn(cid: str) -> fl.client.NumPyClient:
        """Flower calls this to get a client for a given client ID."""
        sid = site_ids[int(cid)]
        return BanditFlowerClient(
            site_id=sid,
            bandit=bandits[sid],
            local_data=site_data[sid],
        )

    # FedAvg strategy
    strategy = fl.server.strategy.FedAvg(
        min_fit_clients=2,
        min_evaluate_clients=2,
        min_available_clients=2,
        fraction_fit=1.0,
        fraction_evaluate=1.0,
    )

    # Run simulation in-process (no network sockets needed)
    history = fl.simulation.start_simulation(
        client_fn=client_fn,
        num_clients=2,
        config=fl.server.ServerConfig(num_rounds=num_rounds),
        strategy=strategy,
    )

    # ── Print per-round results ──────────────────────────────────────────────
    print("\n── Round Results ──────────────────────────────────────────")
    for rnd, metrics_list in enumerate(history.losses_distributed, 1):
        rnd_num, loss = metrics_list
        print(f"  Round {rnd_num:02d}  distributed loss = {loss:.4f}  "
              f"(val_score ≈ {1 - loss:.4f})")

    # ── Compute final global weights (FedAvg of both sites) ─────────────────
    weights_a = bandit_to_parameters(bandits["site_factory_a"])
    weights_b = bandit_to_parameters(bandits["site_warehouse_b"])
    n_a = len(site_a_data)
    n_b = len(site_b_data)
    total = n_a + n_b

    global_weights = [
        (w_a * n_a + w_b * n_b) / total
        for w_a, w_b in zip(weights_a, weights_b)
    ]

    # ── Load global weights into a fresh "global policy" bandit ─────────────
    global_bandit = ContextualBandit(strategy="linucb", policy_version="global_fedavg_v1")
    for i, action in enumerate(ACTIONS):
        global_bandit.A[action] = global_weights[2 * i]
        global_bandit.b[action] = global_weights[2 * i + 1]

    # ── Summary ─────────────────────────────────────────────────────────────
    print("\n── Final Global Policy ────────────────────────────────────")
    print(f"  policy_version : {global_bandit.policy_version}")
    print(f"  strategy       : {global_bandit.strategy}")
    for action in ACTIONS:
        theta = np.linalg.inv(global_bandit.A[action]) @ global_bandit.b[action]
        print(f"  θ̂ {action:<20} norm = {np.linalg.norm(theta):.4f}")

    print("\n── Privacy Guarantee ──────────────────────────────────────")
    print("  ✓ No raw video shared     — only weight matrices (A, b)")
    print("  ✓ No event logs shared    — each site keeps its data local")
    print("  ✓ Face blurring at edge   — before any upload (see decisions.md)")
    print("=" * 60 + "\n")

    return {
        "global_policy_version": global_bandit.policy_version,
        "num_rounds": num_rounds,
        "sites": site_ids,
        "history_losses": history.losses_distributed,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="FedAvg simulation for bandit federation")
    parser.add_argument("--rounds", type=int, default=3, help="Number of FedAvg rounds")
    args = parser.parse_args()
    result = run_federation(num_rounds=args.rounds)
    print(json.dumps({k: str(v) for k, v in result.items()}, indent=2))
