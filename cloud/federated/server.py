"""
Federated Learning Server — FedAvg over Bandit Weights
=======================================================
Runs the Flower server with a FedAvg aggregation strategy.
Aggregates bandit weight matrices (A, b) from all participating sites
and redistributes the global averaged policy.

Usage (in a real multi-machine setup):
    python -m cloud.federated.server --rounds 3 --min-clients 2

For the capstone demo, use simulate.py instead — it runs the server and
all clients in-process without needing separate processes or network sockets.
"""

from __future__ import annotations

from typing import List, Optional, Tuple, Union

import numpy as np

import flwr as fl
from flwr.common import Metrics


def weighted_average(metrics: List[Tuple[int, Metrics]]) -> Metrics:
    """
    Custom Flower metric aggregation function.
    Computes a sample-weighted average of validation_score across all sites.
    """
    total_samples = sum(n for n, _ in metrics)
    if total_samples == 0:
        return {"validation_score": 0.0}

    weighted_score = sum(
        n * m.get("validation_score", 0.0)
        for n, m in metrics
    ) / total_samples

    return {"validation_score": round(weighted_score, 4)}


def build_strategy(
    min_fit_clients: int = 2,
    min_evaluate_clients: int = 2,
    min_available_clients: int = 2,
) -> fl.server.strategy.FedAvg:
    """
    Build a FedAvg strategy for bandit weight aggregation.

    FedAvg (McMahan et al., 2017):
      global_A = mean(A_site1, A_site2, ...) weighted by local dataset size
      global_b = mean(b_site1, b_site2, ...) weighted by local dataset size

    This is mathematically sound for linear bandit weight matrices because
    the optimal LinUCB weights are linear combinations of the data matrices.
    """
    return fl.server.strategy.FedAvg(
        min_fit_clients=min_fit_clients,
        min_evaluate_clients=min_evaluate_clients,
        min_available_clients=min_available_clients,
        evaluate_metrics_aggregation_fn=weighted_average,
        fit_metrics_aggregation_fn=weighted_average,
    )


def start_server(
    server_address: str = "0.0.0.0:8080",
    num_rounds: int = 3,
    min_clients: int = 2,
) -> fl.server.History:
    """
    Start the Flower federation server.

    Args:
        server_address: host:port to bind (default 0.0.0.0:8080).
        num_rounds:     Number of FedAvg rounds to run.
        min_clients:    Minimum sites needed before a round begins.

    Returns:
        Flower History object with per-round metrics.
    """
    strategy = build_strategy(
        min_fit_clients=min_clients,
        min_evaluate_clients=min_clients,
        min_available_clients=min_clients,
    )

    print(f"[Federation Server] Starting on {server_address} — {num_rounds} rounds, min {min_clients} clients")

    history = fl.server.start_server(
        server_address=server_address,
        config=fl.server.ServerConfig(num_rounds=num_rounds),
        strategy=strategy,
    )

    return history


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="FedAvg server for bandit weight federation")
    parser.add_argument("--address",   default="0.0.0.0:8080")
    parser.add_argument("--rounds",    type=int, default=3)
    parser.add_argument("--min-clients", type=int, default=2)
    args = parser.parse_args()
    start_server(args.address, args.rounds, args.min_clients)
