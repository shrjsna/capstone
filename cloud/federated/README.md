# Federated Learning Layer (`cloud/federated/`)

## 1. Context Recap & Privacy Guarantee
The Federated Learning layer provides collaborative policy training across multiple edge sites (e.g. factory plants or warehouse facilities) using **Flower** and the **FedAvg** (Federated Averaging) algorithm.

### Strict Data Privacy Guarantee
> [!IMPORTANT]
> **Only policy weight vectors cross site boundaries.**
> Raw video streams, edge detection event logs, and human operator feedback records **NEVER** leave local site boundaries. Sites share only aggregated numerical model parameters, fulfilling strict industrial security and privacy requirements.

---

## 2. How to Run Demo Locally (Multi-Site Demo)

To run a full federated training loop across 2-3 simulated sites on a single machine:

### Terminal 1: Start the Flower FedAvg Server
```bash
python -m cloud.federated.flower_server --address 127.0.0.1:8089 --rounds 3 --min-clients 2
```

### Terminal 2: Start Site Client 1
```bash
python -m cloud.federated.flower_client --site-id site_1 --server-address 127.0.0.1:8089
```

### Terminal 3: Start Site Client 2
```bash
python -m cloud.federated.flower_client --site-id site_2 --server-address 127.0.0.1:8089
```

Once 2 clients connect, the server will execute 3 rounds of FedAvg aggregation, updating global policy weights and returning updated global model thresholds to both site clients.

---

## 3. Placeholder Weight Format & Integration Guide

### Weight Format (`cloud/federated/adapter.py`)
Currently, policy parameter vectors are serialized as a 1D NumPy float32 array:
```python
# Array shape: (5,)
[zone_a_threshold, zone_b_threshold, default_threshold, learning_rate, exploration_rate]
```

### Swapping to Real Module C Serialization
When Person C's decision layer provides full weight serialization:
1. Update `PolicyWeightAdapter.dict_to_weights()` to serialize Person C's PyTorch/Numpy policy model parameters into a list of NumPy arrays (`List[np.ndarray]`).
2. Update `PolicyWeightAdapter.weights_to_dict()` to deserialize global arrays back into Person C's decision model.
3. No changes to `flower_server.py` or `flower_client.py` network code will be necessary.

---

## 4. Common Errors & Troubleshooting

1. **`ConnectionRefusedError` on Client Startup**
   - *Cause*: Client started before server was listening on `127.0.0.1:8089`.
   - *Fix*: Start `flower_server.py` first and verify it outputs `=== Starting Flower FedAvg Server ===`.

2. **Server Waiting Indefinitely for Clients**
   - *Cause*: Server `--min-clients` set to 2, but only 1 client instance was launched.
   - *Fix*: Open a second terminal window and launch `--site-id site_2`.

3. **Port Conflict (`gRPC transport error: Address already in use`)**
   - *Cause*: Previous instance of `flower_server.py` is still running in the background.
   - *Fix*: Stop previous server process or specify a different port:
     ```bash
     python -m cloud.federated.flower_server --address 127.0.0.1:8090
     ```
     (And connect clients with `--server-address 127.0.0.1:8090`).
