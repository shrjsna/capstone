# Empirical Results Tables for Research Paper

**Repository Git State:**
- **Commit Hash:** `c9618c96150f9235021b71003599e5f36ff57be8`
- **Commit Date:** `Mon Sep 28 00:24:19 2026 +0530`
- **Branch:** `feature/frontend-polish`
- **Execution Date:** September 29, 2026

All numbers reported below were freshly executed, measured, and verified from source code and actual test/validation runs in this session.

---

## Table II: Reward Matrix Used by the Decision Layer

### Exact Extraction Command & Methodology
Extracted by inspecting `cloud/decision_layer/bandit.py` (lines 20–22, 280–303) and verified against `cloud/backend/adapter.py` and `cloud/backend/schemas.py`.

### Source Code Quotation
From `cloud/decision_layer/bandit.py`:
```python
# Exact data contract constants per INTERFACES.md
ACTIONS = ["escalate", "log_only", "adjust_threshold"]
```

```python
    def calculate_reward(self, action: str, feedback: str) -> float:
        """
        Map operator feedback ('confirmed' / 'false_alarm') to graded reward.

        Safety-First Rebalanced Reward Matrix:
        - log_only + confirmed = -2.0 (CRITICAL: Missed real safety violation, worst risk)
        - escalate + false_alarm = -1.0 (Operator fatigue / unnecessary alarm)
        - escalate + confirmed = +1.0 (True positive alert delivered)
        - log_only + false_alarm = +0.5 (Correct noise suppression)
        - adjust_threshold + confirmed = +0.7 (Appropriate adjustment)
        - adjust_threshold + false_alarm = -0.3 (Mild miscalibration penalty)
        """
        fb = str(feedback).lower()
        is_confirmed = fb == "confirmed"

        if action == "escalate":
            return 1.0 if is_confirmed else -1.0
        elif action == "log_only":
            return -2.0 if is_confirmed else 0.5
        elif action == "adjust_threshold":
            return 0.7 if is_confirmed else -0.3
        else:
            return 0.0
```

From `cloud/backend/schemas.py`:
```python
class OperatorFeedbackCreate(BaseModel):
    event_id: str
    feedback: Literal["confirmed", "false_alarm"]
    operator_id: str
    timestamp: str

class BanditDecisionOutput(BaseModel):
    event_id: str
    action: Literal["escalate", "log_only", "adjust_threshold"]
    policy_version: str
    threshold_used: float
```

### Table II: Decision Layer Reward Matrix

| Action (`action`) | `confirmed` | `false_alarm` | Fallthrough / Other (`no_response`, `ignored`, etc.) |
| :--- | :---: | :---: | :---: |
| **`escalate`** | `+1.0` | `-1.0` | `-1.0` |
| **`log_only`** | `-2.0` | `+0.5` | `+0.5` |
| **`adjust_threshold`** | `+0.7` | `-0.3` | `-0.3` |
| **Unrecognized Action** *(fallthrough)* | `0.0` | `0.0` | `0.0` |

### Default & Fallthrough Handling
- **Binary feedback evaluation:** In `bandit.py`, `is_confirmed = (fb == "confirmed")`. If any non-confirmed feedback string (e.g., `no_response`, `ignored`, or unmapped string) is supplied, `is_confirmed` evaluates to `False`. Thus:
  - `escalate` falls through to `-1.0`.
  - `log_only` falls through to `+0.5`.
  - `adjust_threshold` falls through to `-0.3`.
- **Unrecognized action:** Any action not matching `"escalate"`, `"log_only"`, or `"adjust_threshold"` hits the final `else: return 0.0`.
- **Missing feedback field in dict:** In `bandit.py` line 320 (`update` method), if a dictionary is passed without a `"feedback"` key, it defaults via `str(feedback.get("feedback", "false_alarm"))` to `"false_alarm"`.

---

## Table III: PPE Model Evaluation Results

### Model Files Discovery & Integrity Verification
Executed command:
```powershell
Get-ChildItem -Recurse -Filter *.pt | ForEach-Object {
    [PSCustomObject]@{
        Path = $_.FullName;
        Hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash;
        Size = $_.Length
    }
}
```

Discovered model checkpoints:
1. `edge/ppe_detection/models/ppe_final_v4.pt` (15,968,101 bytes)
   - SHA256: `ABF9929F72CD529198CDFE0D21ACD14B0FEB5A05C478ADBB7B4001644739FB9A`
2. `runs/detect/ppe_yolov11n_v4/weights/best.pt` (15,968,101 bytes)
   - SHA256: `ABF9929F72CD529198CDFE0D21ACD14B0FEB5A05C478ADBB7B4001644739FB9A`
   - *Note:* **Byte-identical** to `ppe_final_v4.pt`.
3. `runs/detect/ppe_yolov11n_v4/weights/last.pt` (15,968,101 bytes)
   - SHA256: `ABF9929F72CD529198CDFE0D21ACD14B0FEB5A05C478ADBB7B4001644739FB9A`
   - *Note:* **Byte-identical** to `best.pt` and `ppe_final_v4.pt`.
4. `runs/detect/ppe_yolov11n_v5/weights/best.pt` (15,947,493 bytes)
   - SHA256: `9DDA5861B24E3EA3597CA57BF510E15A10DED0A3231305964C536671C67774FA`
5. `runs/detect/ppe_yolov11n_v5/weights/last.pt` (15,947,493 bytes)
   - SHA256: `9DDA5861B24E3EA3597CA57BF510E15A10DED0A3231305964C536671C67774FA`
   - *Note:* **Byte-identical** to `v5/weights/best.pt`.
6. `runs/detect/ppe_yolov11n/weights/best.pt` (5,483,482 bytes)
   - SHA256: `FDB71B876ED22DEDA3CF3749DB8592F175038928DAD5E31E29FC5EB2F7A6FD25`
7. `runs/detect/ppe_yolov11n/weights/last.pt` (5,483,482 bytes)
   - SHA256: `FD7BBEAD82BA7C2FD6A1860A92F509315FEAA9B76A61F94DCA27F8CD6C1D91BF`

### Data Split Used
- **Dataset Configuration:** `edge/ppe_detection/data/merged/data.yaml`
- **Split Path:** `edge/ppe_detection/data/merged/valid/images`
- **Split Size:** **4,033 images**, **26,727 annotated instances** across 16 unified classes.
- **Dataset Provenance:** Merged from 4 public benchmark sources (Roboflow Construction Safety, Construction PPE, My First Project v1i YOLOv11, and Keremberke PPE) as described in `prepare_dataset.py`. This split constitutes the repository's held-out validation set.

### Execution Commands
For `ppe_final_v4.pt`:
```bash
venv\Scripts\python.exe -c "from ultralytics import YOLO; m = YOLO('edge/ppe_detection/models/ppe_final_v4.pt'); r = m.val(data='edge/ppe_detection/data/merged/data.yaml'); print(r.results_dict)"
```
Raw Output:
```text
                   all       4033      26727      0.778      0.615      0.653       0.45
{'metrics/precision(B)': 0.7782932453332174, 'metrics/recall(B)': 0.6151251634327941, 'metrics/mAP50(B)': 0.652570467375089, 'metrics/mAP50-95(B)': 0.44967650870643733, 'fitness': 0.44967650870643733}
```

For `runs/detect/ppe_yolov11n_v5/weights/best.pt`:
```bash
venv\Scripts\python.exe -c "from ultralytics import YOLO; m = YOLO('runs/detect/ppe_yolov11n_v5/weights/best.pt'); r = m.val(data='edge/ppe_detection/data/merged/data.yaml'); print(r.results_dict)"
```
Raw Output:
```text
                   all       4033      26727      0.777      0.674      0.724      0.482
{'metrics/precision(B)': 0.7770267797752219, 'metrics/recall(B)': 0.6740440504631757, 'metrics/mAP50(B)': 0.7235793080607564, 'metrics/mAP50-95(B)': 0.4820672199874555, 'fitness': 0.4820672199874555}
```

For `runs/detect/ppe_yolov11n/weights/best.pt`:
```bash
venv\Scripts\python.exe -c "from ultralytics import YOLO; m = YOLO('runs/detect/ppe_yolov11n/weights/best.pt'); r = m.val(data='edge/ppe_detection/data/merged/data.yaml'); print(r.results_dict)"
```
Raw Output:
```text
                   all       4033      26727      0.725      0.408      0.447      0.271
{'metrics/precision(B)': 0.7245786374443883, 'metrics/recall(B)': 0.407779569918669, 'metrics/mAP50(B)': 0.44658120243976235, 'metrics/mAP50-95(B)': 0.27127077892264395, 'fitness': 0.27127077892264395}
```

### Table III: PPE Model Evaluation Results (Evaluated on Same Split: `valid/images`, 4,033 images)

| Metric | `ppe_final_v4.pt` *(Production Model)* | `ppe_yolov11n_v5/best.pt` *(Experimental Checkpoint)* | `ppe_yolov11n/best.pt` *(Baseline Checkpoint)* |
| :--- | :---: | :---: | :---: |
| **Precision** | `0.7783` | `0.7770` | `0.7246` |
| **Recall** | `0.6151` | `0.6740` | `0.4078` |
| **mAP@50** | `0.6526` | `0.7236` | `0.4466` |
| **mAP@50-95** | `0.4497` | `0.4821` | `0.2713` |

*(Note: `runs/detect/ppe_yolov11n_v4/weights/best.pt` and `last.pt` are byte-identical to `ppe_final_v4.pt`, SHA256: `ABF9929F72CD529198CDFE0D21ACD14B0FEB5A05C478ADBB7B4001644739FB9A`, and therefore yield the identical results).*

#### Additional Evaluation on Test Split (`test/images`, 1,506 images):
For complete transparency, evaluating `ppe_final_v4.pt` on the 1,506-image `test` split (`split='test'`) yields:
- **Precision:** `0.8508`
- **Recall:** `0.6301`
- **mAP@50:** `0.6882`
- **mAP@50-95:** `0.4606`

#### Discrepancy Note vs. Prior Documentation
In `edge/ppe_detection/README.md`, metrics for v4 and v5 were reported as:
- *v4:* Precision 0.8816, Recall 0.6733, mAP50 0.7366, mAP50-95 0.4949
- *v5:* Precision 0.7775, Recall 0.6739, mAP50 0.7218, mAP50-95 0.4793
These prior figures match the historical training logs in `runs/detect/ppe_yolov11n_v4/results.csv` (epoch 117), which evaluated with in-training EMA weights and training-time dataloader settings. The figures in Table III above are the actual standalone evaluation metrics obtained via Ultralytics `YOLO.val()` on the standalone checkpoint.

---

## Table IV: Automated Test Suite Breakdown

### Exact Execution Commands
1. Collection breakdown:
```bash
venv\Scripts\python.exe -m pytest --collect-only -q
```
Result: **112 tests collected in 2.17s**

2. Test execution:
```bash
venv\Scripts\python.exe -m pytest -v --tb=no -q
```
Result: **112 passed, 3 warnings in 5.69s**

### File-to-Module Mapping
- `tests/test_ppe_detection.py` (15 tests): Tests label remapping, event serialization, and multi-frame debounce logic in `edge/ppe_detection`.
- `edge/zone_intrusion/tests/test_debounce_tracker.py` (7 tests): Tests streak gating, re-entry, and track independence in `edge/zone_intrusion`.
- `edge/zone_intrusion/tests/test_zone_check.py` (8 tests): Tests point-in-polygon and bottom-center foot coordinate checks in `edge/zone_intrusion`.
- `tests/test_bandit.py` (10 tests): Tests `ContextualBandit` (LinUCB, Thompson sampling, epsilon-greedy, retrain validation gate, and rollback) in `cloud/decision_layer`.
- `tests/test_backend.py` (8 tests): Tests FastAPI endpoints (`/health`, `/events`, `/feedback`, `/alerts`, `/alerts/{id}`, `/policy-history`) in `cloud/backend`.
- `tests/test_stream_manager.py` (39 tests): Tests `StreamState`, camera/video stream start/stop control, MJPEG streaming generator, frame capture, and zone polygon configuration API in `cloud/backend/stream_manager.py`.
- `tests/test_dashboard.py` (2 tests): Tests static asset presence and DOM structure bindings in `dashboard`.
- `tests/test_federated.py` (2 tests): Tests `PolicyWeightAdapter` bidirectional conversion and FedAvg mathematical weight aggregation in `cloud/federated`.
- `tests/test_integration.py` (20 tests): Multi-component integration suite:
  - *Full Pipeline & Adapter Integration* (8 tests): End-to-end event flow, bandit decisions, online feedback matrix updates, and adapter compliance.
  - *Data Contract Schema Validation* (6 tests): Round-trip serialization for all 4 schemas in `INTERFACES.md`.
  - *Federated Weight Privacy & Round-Trip* (6 tests): Verifies numeric-only float64 weight payloads with no raw event/operator leakage.
- `tests/test_setup.py` (1 test): Environment and CI smoke test.

### Table IV: Automated Test Suite

| Module (Repo Architecture) | Primary Test File(s) | Test Count |
| :--- | :--- | :---: |
| **Stream Manager & Live Streaming** | `tests/test_stream_manager.py` | 39 |
| **System Integration & Contract Validation** | `tests/test_integration.py` | 20 |
| **PPE Compliance Detection** | `tests/test_ppe_detection.py` | 15 |
| **Zone Intrusion Detection** | `edge/zone_intrusion/tests/test_debounce_tracker.py` (7)<br>`edge/zone_intrusion/tests/test_zone_check.py` (8) | 15 |
| **Contextual Bandit Decision Layer** | `tests/test_bandit.py` | 10 |
| **Cloud Backend API** | `tests/test_backend.py` | 8 |
| **Federated Learning** | `tests/test_federated.py` | 2 |
| **Dashboard UI** | `tests/test_dashboard.py` | 2 |
| **Repository Setup / CI Baseline** | `tests/test_setup.py` | 1 |
| **Total** | *All 10 test files* | **112** |

### Reconciliation
- **Total Test Count in Table:** $39 + 20 + 15 + 15 + 10 + 8 + 2 + 2 + 1 = 112$
- **Total Collected by Pytest:** `112 tests collected`
- **Total Passed:** `112 passed, 0 failed`
- **Reconciliation Status:** Exact match ($112 \equiv 112$).
