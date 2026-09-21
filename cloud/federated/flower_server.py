"""
cloud/federated/flower_server.py
Flower server implementation running FedAvg aggregation strategy for multi-site policy training.
"""

import argparse
import sys
import flwr as fl


def main():
    parser = argparse.ArgumentParser(description="Flower FedAvg Policy Aggregation Server")
    parser.add_argument("--address", type=str, default="127.0.0.1:8089", help="Server gRPC address")
    parser.add_argument("--rounds", type=int, default=3, help="Number of FL rounds")
    parser.add_argument("--min-clients", type=int, default=2, help="Minimum clients required for round")
    args = parser.parse_args()

    print(f"=== Starting Flower FedAvg Server on {args.address} ===")
    print(f"=== Config: {args.rounds} rounds, min {args.min_clients} clients per round ===")
    print("=== Privacy Guarantee: Only policy weight vectors are aggregated ===")

    # Define FedAvg strategy
    strategy = fl.server.strategy.FedAvg(
        fraction_fit=1.0,
        fraction_evaluate=1.0,
        min_fit_clients=args.min_clients,
        min_evaluate_clients=args.min_clients,
        min_available_clients=args.min_clients,
    )

    # Start Flower server
    try:
        fl.server.start_server(
            server_address=args.address,
            config=fl.server.ServerConfig(num_rounds=args.rounds),
            strategy=strategy,
        )
    except Exception as e:
        print(f"[Error starting Flower server]: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
