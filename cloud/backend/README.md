# Cloud Backend (`cloud/backend/`)

## 1. Context Recap
The Cloud Backend serves as the centralized API layer in the Edge-Cloud Collaborative AI Safety System. It performs three critical system functions:
- Receives real-time **Detection Events** (`POST /events`) emitted by edge modules (A: PPE Compliance, B: Restricted-Zone Intrusion).
- Interacts with the **Contextual Bandit Decision Layer** via `BanditAdapter` to decide on immediate actions (`escalate` / `log_only`) and apply dynamic zone thresholds.
- Receives human **Operator Feedback** (`POST /feedback`) from the frontend dashboard, storing reward signals that drive policy adaptation.
- Serves the live alert feed (`GET /alerts`) and policy update history (`GET /policy-history`) to the operations console.

---

## 2. How to Run Locally

### Prerequisites
- Python 3.11+
- Virtual environment activated (`python --version`)

### Installation & Setup
```bash
# Install backend dependencies
pip install fastapi uvicorn sqlalchemy pydantic httpx pytest

# Start the FastAPI server (from repository root)
uvicorn cloud.backend.main:app --reload --host 127.0.0.1 --port 8000
```

The API will be available at `http://127.0.0.1:8000`. Interactive OpenAPI documentation is accessible at `http://127.0.0.1:8000/docs`.

---

## 3. API Endpoints Catalog

### `GET /health`
Sanity check endpoint for demo monitoring.
- **Response** `200 OK`:
  ```json
  {"status": "ok"}
  ```

---

### `POST /events`
Receives detection events from edge devices (`infer.py`). Assigns a server-side UUID `event_id`, queries `BanditAdapter` for decisioning, and persists to SQLite. Matches **Detection Event Schema**.

- **Request Body**:
  ```json
  {
    "camera_id": "cam_north_01",
    "zone_id": "zone_a",
    "event_type": "ppe_violation",
    "class": "no_helmet",
    "confidence": 0.88,
    "tracked_id": "tr_4091",
    "timestamp": "2026-09-20T12:00:00Z",
    "frame_count_triggered": 18,
    "clip_captured": true
  }
  ```
- **Response** `201 Created`:
  ```json
  {
    "event_id": "c62f928e-8a9d-4e9b-9c2b-65e1d904fa18",
    "camera_id": "cam_north_01",
    "zone_id": "zone_a",
    "event_type": "ppe_violation",
    "class": "no_helmet",
    "confidence": 0.88,
    "tracked_id": "tr_4091",
    "timestamp": "2026-09-20T12:00:00Z",
    "frame_count_triggered": 18,
    "clip_captured": true,
    "bandit_action": "escalate",
    "policy_version": "v1.0.0-mock",
    "threshold_used": 0.70
  }
  ```

---

### `POST /feedback`
Receives operator feedback from the dashboard. Validates `event_id` exists in DB, persists feedback, and forwards reward signal to `BanditAdapter`. Matches **Operator Feedback Schema**.

- **Request Body**:
  ```json
  {
    "event_id": "c62f928e-8a9d-4e9b-9c2b-65e1d904fa18",
    "feedback": "confirmed",
    "operator_id": "op_smith_04",
    "timestamp": "2026-09-20T12:01:30Z"
  }
  ```
- **Response** `200 OK`:
  ```json
  {
    "status": "success",
    "event_id": "c62f928e-8a9d-4e9b-9c2b-65e1d904fa18",
    "feedback": "confirmed",
    "operator_id": "op_smith_04",
    "timestamp": "2026-09-20T12:01:30Z"
  }
  ```

---

### `GET /alerts`
Returns recent events joined with bandit decision data for the dashboard's live feed. Supports pagination.

- **Query Parameters**:
  - `limit` (int, default=50, max=500)
  - `offset` (int, default=0)
- **Response** `200 OK`: Array of `DetectionEventResponse` items.

---

### `GET /alerts/{event_id}`
Returns details for a single specific alert.
- **Response** `200 OK`: Single `DetectionEventResponse` object.
- **Response** `404 Not Found`: If `event_id` is invalid.

---

### `GET /policy-history`
Returns history of policy update records. Matches **Policy Update Record Schema**.

---

## 4. Integrating the Real Bandit (`BanditAdapter` Contract)

To replace the demo `MockBanditAdapter` with Person C's real decision layer:

### Contract Interface (`cloud/backend/adapter.py`)
Any adapter must subclass `BanditAdapter` and implement three methods:
```python
class RealBanditAdapter(BanditAdapter):
    def decide(self, event: DetectionEventCreate, event_id: str) -> BanditDecisionOutput:
        # Pass event features to Person C's contextual bandit model
        # Return BanditDecisionOutput(event_id=event_id, action=..., policy_version=..., threshold_used=...)
        pass

    def submit_feedback(self, feedback: OperatorFeedbackCreate) -> None:
        # Pass (event_id, feedback) as reward signal to Person C's bandit model online learning step
        pass

    def get_zone_thresholds(self) -> Dict[str, float]:
        # Return current learned per-zone threshold values dict
        pass
```

### Where to Swap
In `cloud/backend/adapter.py`, update the factory function `get_bandit_adapter()`:
```python
# Swap this line in cloud/backend/adapter.py:
def get_bandit_adapter() -> BanditAdapter:
    return RealBanditAdapter()  # Replaces MockBanditAdapter()
```

### Mock Logic Behavior
The active `MockBanditAdapter` uses simulated zone threshold dynamics for demonstration purposes:
- Initial threshold is `0.70` for `zone_a` and `0.75` for `zone_b`.
- If `confidence >= zone_threshold`, returns `action="escalate"`; otherwise `action="log_only"`.
- On `"confirmed"` feedback, thresholds are lowered by `0.02` (min `0.40`).
- On `"false_alarm"` feedback, thresholds are increased by `0.03` (max `0.95`).

---

## 5. Common Errors & Troubleshooting

1. **Port Already in Use (`[Errno 10048] address already in use`)**
   - *Cause*: Another process is listening on port 8000.
   - *Fix*: Check running processes (`netstat -ano | findstr :8000` on Windows) or specify a different port when starting uvicorn:
     `uvicorn cloud.backend.main:app --port 8080`

2. **Schema Validation Error (`422 Unprocessable Entity`) on `POST /events`**
   - *Cause*: Field name mismatch or missing required field (e.g. sending `class_name` instead of JSON property `"class"`, or missing ISO8601 `timestamp`).
   - *Fix*: Ensure edge POST payload matches `INTERFACES.md` schema exactly. The Pydantic model maps JSON `"class"` to Python attribute `class_name`.

3. **`404 Not Found` on `POST /feedback`**
   - *Cause*: Dashboard submitted feedback for an `event_id` that was not saved in SQLite.
   - *Fix*: Ensure the alert was generated by `POST /events` prior to feedback submission.

4. **Database Lock Errors (`sqlite3.OperationalError: database is locked`)**
   - *Cause*: Concurrent writing to local SQLite file during testing.
   - *Fix*: `cloud/backend/database.py` sets `connect_args={"check_same_thread": False}`. For local development, remove or reset the DB file `cloud_backend.db` if corrupted.

5. **CORS Errors When Dashboard Accesses Backend**
   - *Cause*: Browser blocking fetch calls from `http://localhost:8080` to `http://localhost:8000`.
   - *Fix*: Backend includes `CORSMiddleware` with `allow_origins=["*"]`. Ensure backend is running and CORS middleware is not removed.
