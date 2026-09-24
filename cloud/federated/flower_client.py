"""
cloud/federated/flower_client.py
Flower FL site client representing an edge site participating in policy aggregation.
"""

import argparse
import sys
import numpy as np
import flwr as fl
from cloud.federated.adapter import PolicyWeightAdapter


class BanditSiteClient(fl.client.NumPyClient):
    def __init__(self, site_id: str):
        self.site_id = site_id
        # Initialize local site policy thresholds with site-specific slight variation
        if site_id == "site_1":
            self.thresholds = {"zone_a": 0.68, "zone_b": 0.72, "default": 0.68}
        elif site_id == "site_2":
            self.thresholds = {"zone_a": 0.74, "zone_b": 0.78, "default": 0.74}
        else:
            self.thresholds = {"zone_a": 0.70, "zone_b": 0.75, "default": 0.70}

    def get_parameters(self, config):
        print(f"[{self.site_id}] Providing local policy weights to Flower server...")
        return PolicyWeightAdapter.dict_to_weights(self.thresholds)

    def fit(self, parameters, config):
        print(f"[{self.site_id}] Received global policy weights from server. Training local adaptation step...")
        # Convert received global parameters to local format
        global_thresholds = PolicyWeightAdapter.weights_to_dict(parameters)
        
        # Simulate local online gradient step on local feedback
        for k in self.thresholds:
            # Shift slightly towards global weight
            self.thresholds[k] = round(0.5 * self.thresholds[k] + 0.5 * global_thresholds[k], 3)

        updated_weights = PolicyWeightAdapter.dict_to_weights(self.thresholds)
        num_examples = 100  # Number of local detection samples in site batch
        print(f"[{self.site_id}] Updated local thresholds: {self.thresholds}")
        return updated_weights, num_examples, {}

    def evaluate(self, parameters, config):
        print(f"[{self.site_id}] Evaluating global policy parameters locally...")
        # Calculate synthetic evaluation metric (loss)
        loss = 0.05
        num_examples = 100
        metrics = {"accuracy": 0.94}
        return float(loss), num_examples, metrics


def main():
    parser = argparse.ArgumentParser(description="Flower Federated Learning Site Client")
    parser.add_argument("--site-id", type=str, required=True, help="Unique identifier for site (e.g. site_1, site_2)")
    parser.add_argument("--server-address", type=str, default="127.0.0.1:8089", help="Flower server gRPC address")
    args = parser.parse_args()

    print(f"=== Starting Federated Client [{args.site_id}] connecting to {args.server_address} ===")
    client = BanditSiteClient(site_id=args.site_id)
    
    try:
        fl.client.start_numpy_client(
            server_address=args.server_address,
            client=client
        )
    except Exception as e:
        print(f"[{args.site_id} Client Error]: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
