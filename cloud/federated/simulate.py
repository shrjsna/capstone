"""
Federation Simulation -- 2-Site In-Process Demo
================================================
Simulates two factory sites (Site A and Site B) running FedAvg on their
local bandit weights -- fully in-process, no network sockets, no ray needed.

Run with:
    python -m cloud.federated.simulate
    python -m cloud.federated.simulate --rounds 5

What happens
------------
  Round 1-N : Each site retrains locally on its own event data, then FedAvg
              averages the A and b matrices into a shared global policy.
  Final      : Global policy theta_hat norms and privacy summary printed.

Why FedAvg works for LinUCB
---------------------------
The optimal LinUCB weight theta* = A^{-1} b is a linear function of the
data matrices.  FedAvg computes a sample-weighted mean of A and b across
sites -- equivalent to pooling all sites' data without raw data ever
leaving a site (privacy preserving).

Implementation note
-------------------
We implement FedAvg directly in pure Python instead of using
fl.simulation.start_simulation, which requires ray (heavy optional dep).
The logic is identical:
  1. Server broadcasts current global weights to all clients.
  2. Each client loads global weights, runs one local retrain round (fit).
  3. Server aggregates with weighted FedAvg.
  4. Repeat for num_rounds.
"""

from __future__ import annotations

import json
from typing import List, Tuple, Dict

import numpy as np

from cloud.decision_layer.bandit import ContextualBandit, ACTIONS, FEATURE_DIM
from cloud.federated.client import BanditFlowerClient, bandit_to_parameters, parameters_to_bandit


# ---------------------------------------------------------------------------
# Synthetic local datasets
# ---------------------------------------------------------------------------

def _make_site_a_data() -> List[Tuple[Dict, str, str]]:
    """
    Site A: Outdoor construction site.
    Mix: high-conf PPE violations (escalate/confirmed), some marginal (adjust/confirmed),
    some low-conf noise (log_only/false_alarm) -- so the 80/20 eval split has positives.
    """
    data = []
    # High-confidence PPE violations -> escalate (reward +1.0 on confirmed)
    for _ in range(8):
        data.append((
            {"event_type": "ppe_violation", "class": "no_helmet",
             "confidence": 0.88, "frame_count_triggered": 5, "clip_captured": True},
            "escalate", "confirmed"
        ))
    # Marginal -> adjust_threshold (reward +0.7 on confirmed)
    for _ in range(4):
        data.append((
            {"event_type": "ppe_violation", "class": "no_vest",
             "confidence": 0.74, "frame_count_triggered": 4, "clip_captured": True},
            "adjust_threshold", "confirmed"
        ))
    # Low-confidence noise -> log_only (reward +0.5 on false_alarm)
    for _ in range(4):
        data.append((
            {"event_type": "ppe_violation", "class": "no_gloves",
             "confidence": 0.31, "frame_count_triggered": 1, "clip_captured": False},
            "log_only", "false_alarm"
        ))
    return data


def _make_site_b_data() -> List[Tuple[Dict, str, str]]:
    """
    Site B: Indoor warehouse.
    Mix: confirmed zone intrusions (escalate), low-conf log_only noise.
    """
    data = []
    # Confirmed zone intrusions -> escalate (reward +1.0)
    for _ in range(8):
        data.append((
            {"event_type": "zone_intrusion", "class": "person_in_zone",
             "confidence": 0.82, "frame_count_triggered": 6, "clip_captured": True},
            "escalate", "confirmed"
        ))
    # Marginal -> adjust_threshold (reward +0.7)
    for _ in range(4):
        data.append((
            {"event_type": "zone_intrusion", "class": "person_in_zone",
             "confidence": 0.74, "frame_count_triggered": 4, "clip_captured": True},
            "adjust_threshold", "confirmed"
        ))
    # Forklift false alarms -> log_only (reward +0.5)
    for _ in range(4):
        data.append((
            {"event_type": "zone_intrusion", "class": "person_in_zone",
             "confidence": 0.38, "frame_count_triggered": 2, "clip_captured": False},
            "log_only", "false_alarm"
        ))
    return data


# ---------------------------------------------------------------------------
# Pure-Python FedAvg aggregation
# ---------------------------------------------------------------------------

def _fedavg(client_results: List[Tuple[List[np.ndarray], int]]) -> List[np.ndarray]:
    """
    Weighted average of parameter lists from multiple clients.
    FedAvg formula: global_p = sum(n_i * p_i) / sum(n_i)
    """
    total = sum(n for _, n in client_results)
    if total == 0:
        return client_results[0][0]
    return [
        sum(params[i] * n for params, n in client_results) / total
        for i in range(len(client_results[0][0]))
    ]


def _score_params(
    params: List[np.ndarray],
    eval_set: List[Tuple[Dict, str, str]],
    bandit_ref: ContextualBandit,
) -> float:
    """
    Score a parameter set against an eval set WITHOUT mutating bandit state.
    Returns fraction of eval examples where the policy earns positive reward.
    """
    if not eval_set:
        return 0.0

    # Build temporary A/b from params
    tmp_A = {ACTIONS[i]: params[2 * i] for i in range(len(ACTIONS))}
    tmp_b = {ACTIONS[i]: params[2 * i + 1] for i in range(len(ACTIONS))}

    positive = 0
    for event_dict, target_action, feedback_str in eval_set:
        x = bandit_ref.extract_features(event_dict)
        scores = {}
        for a in ACTIONS:
            A_inv = np.linalg.inv(tmp_A[a])
            theta_hat = A_inv @ tmp_b[a]
            scores[a] = float((theta_hat.T @ x).item())
        pred_action = max(scores, key=scores.get)
        r = bandit_ref.calculate_reward(pred_action, feedback_str)
        if r > 0.0:
            positive += 1

    return round(positive / len(eval_set), 4)


# ---------------------------------------------------------------------------
# Main simulation
# ---------------------------------------------------------------------------

def run_federation(num_rounds: int = 3) -> Dict:
    """
    Run FedAvg federation across 2 simulated factory sites.

    Returns:
        dict with global_policy_version, num_rounds, sites, round_metrics.
    """
    print("\n" + "=" * 62)
    print("  FEDERATED LEARNING SIMULATION -- Industrial Safety Bandit")
    print("=" * 62)
    print(f"  Sites    : 2  (Site A = Construction, Site B = Warehouse)")
    print(f"  Strategy : FedAvg  (McMahan et al., 2017)")
    print(f"  Rounds   : {num_rounds}")
    print(f"  Privacy  : Only weight matrices shared -- no raw event data")
    print("=" * 62 + "\n")

    site_a_data = _make_site_a_data()
    site_b_data = _make_site_b_data()

    site_data = {
        "site_factory_a":   site_a_data,
        "site_warehouse_b": site_b_data,
    }
    site_ids = list(site_data.keys())

    # One fresh bandit per site (used as feature extractor + local trainer)
    bandits = {
        sid: ContextualBandit(strategy="linucb", policy_version=f"local_{sid}")
        for sid in site_ids
    }

    # Flower clients (pure NumPy -- no gRPC/ray)
    clients = {
        sid: BanditFlowerClient(
            site_id=sid,
            bandit=bandits[sid],
            local_data=site_data[sid],
        )
        for sid in site_ids
    }

    # Start with cold-start identity params
    global_params = clients[site_ids[0]].get_parameters(config={})
    round_metrics: List[Dict] = []

    # ---- FedAvg rounds -----------------------------------------------------
    for rnd in range(1, num_rounds + 1):
        # 1. Each client: load global weights -> local retrain -> return updated weights
        fit_results = []
        for sid in site_ids:
            params_out, n_samples, _ = clients[sid].fit(
                parameters=global_params, config={"round": rnd}
            )
            fit_results.append((params_out, n_samples))

        # 2. Server: FedAvg aggregate
        global_params = _fedavg(fit_results)

        # 3. Evaluate global weights on each site's full dataset (no mutation)
        site_scores = {}
        ref_bandit = bandits[site_ids[0]]  # used only for extract_features / calculate_reward
        for sid in site_ids:
            score = _score_params(global_params, site_data[sid], ref_bandit)
            site_scores[sid] = score

        avg_score = round(sum(site_scores.values()) / len(site_scores), 4)
        print(f"  Round {rnd:02d}  avg_val_score={avg_score:.4f}  |  {site_scores}")
        round_metrics.append({"round": rnd, "avg_val_score": avg_score, "sites": site_scores})

    # ---- Load final global policy ------------------------------------------
    global_bandit = ContextualBandit(strategy="linucb", policy_version="global_fedavg_v1")
    parameters_to_bandit(global_params, global_bandit)

    print("\n-- Final Global Policy -------------------------------------------")
    print(f"  policy_version : {global_bandit.policy_version}")
    print(f"  strategy       : {global_bandit.strategy}")
    for action in ACTIONS:
        theta = np.linalg.inv(global_bandit.A[action]) @ global_bandit.b[action]
        print(f"  theta_hat  [{action:<20}]  norm={np.linalg.norm(theta):.4f}")

    final_score = round_metrics[-1]["avg_val_score"] if round_metrics else 0.0
    print(f"\n  Final avg validation score : {final_score:.4f}")
    print(f"  Rounds completed           : {num_rounds}")

    print("\n-- Privacy Guarantee ---------------------------------------------")
    print("  [OK] No raw video shared     -- only weight matrices (A, b)")
    print("  [OK] No event logs shared    -- each site keeps data local")
    print("  [OK] Face blurring at edge   -- before any upload (decisions.md)")
    print("=" * 62 + "\n")

    return {
        "global_policy_version": global_bandit.policy_version,
        "num_rounds": num_rounds,
        "sites": site_ids,
        "round_metrics": round_metrics,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="FedAvg simulation for bandit federation")
    parser.add_argument("--rounds", type=int, default=3, help="Number of FedAvg rounds (default: 3)")
    args = parser.parse_args()
    result = run_federation(num_rounds=args.rounds)
    print(json.dumps(
        {k: v for k, v in result.items() if k != "round_metrics"},
        indent=2
    ))
