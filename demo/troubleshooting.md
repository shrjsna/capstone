# Demo Troubleshooting Guide

Real specific failures you might see during a live run, and how to fix them fast.

---

## Backend Failures

### "Address already in use" / "[Errno 10048]" when starting uvicorn

**Cause:** Another process is already listening on port 8000, often from a
previous demo run that wasn't cleanly stopped.

**Fix (Windows):**
```
netstat -ano | findstr :8000
```
Find the PID in the last column, then:
```
taskkill /F /PID <PID>
```
Then retry `uvicorn cloud.backend.main:app --reload --host 127.0.0.1 --port 8000`.

Alternatively, use a different port:
```
uvicorn cloud.backend.main:app --host 127.0.0.1 --port 8001
```
Then update the dashboard API URL field to `http://127.0.0.1:8001`.

---

### Backend starts but immediately crashes with "ImportError: No module named 'fastapi'"

**Cause:** The virtual environment is not activated, or the packages were not
installed into the active environment.

**Fix:**
```
venv\Scripts\activate
venv\Scripts\python.exe -m pip list | findstr fastapi
```
If fastapi is not listed:
```
venv\Scripts\python.exe -m pip install fastapi uvicorn sqlalchemy pydantic
```

---

### "422 Unprocessable Entity" when posting an event

**Cause:** The JSON payload has a wrong field name or missing required field.
The most common mistake is using `"class_name"` instead of `"class"` (the
JSON key must be `"class"` exactly, per INTERFACES.md).

**Fix:** Check the request body matches this exact shape:
```json
{
  "camera_id": "cam_01",
  "zone_id": "zone_a",
  "event_type": "ppe_violation",
  "class": "no_helmet",
  "confidence": 0.91,
  "tracked_id": "person_042",
  "timestamp": "2026-09-22T10:15:00Z",
  "frame_count_triggered": 5,
  "clip_captured": true
}
```
Use `demo/demo_inject_events.py` which sends the correct payload.

---

### "404 Not Found" when posting feedback

**Cause:** The event_id in the feedback request doesn't exist in the database.
This happens if:
- The database was cleared between the event POST and the feedback POST.
- The feedback is using a hardcoded event_id from a previous run.

**Fix:** Use the event_id from the current run's POST /events response.
`demo_inject_events.py` prints the event IDs; copy the fresh ones.

---

### Database lock error / "sqlite3.OperationalError: database is locked"

**Cause:** Two processes are writing to `cloud_backend.db` simultaneously,
or the file is corrupted from a previous crashed run.

**Fix:** Stop all processes, delete the database file, and restart:
```
del cloud_backend.db
uvicorn cloud.backend.main:app --reload --host 127.0.0.1 --port 8000
```
The database is re-created automatically on startup.

---

## Dashboard Failures

### Dashboard loads but shows "Error fetching alerts" or blank feed

**Cause 1:** Backend is not running. Check Terminal 1 shows
`Application startup complete`.

**Cause 2:** Wrong API URL in the dashboard. The URL field should be
`http://127.0.0.1:8000` (no trailing slash). Click the field and verify.

**Cause 3:** CORS blocked. This only happens if you open index.html as a
`file://` URL instead of through the Python HTTP server.
Fix: run `python -m http.server 8080 --directory dashboard` and open
`http://127.0.0.1:8080` (not `file://...`).

---

### Feedback buttons do nothing / "404 feedback error" in browser console

**Cause:** The alert card's event_id is no longer in the database (database
was cleared after the alerts loaded).

**Fix:** Reload the dashboard page to refresh the alert list, then submit
feedback again.

---

## PPE Inference Failures (when using infer.py directly)

### "FileNotFoundError: Model file not found at edge/ppe_detection/models/ppe_final_v4.pt"

**Cause:** The model weights file isn't in the expected location. Weights are
in `.gitignore` and not in the repo — they must be present locally.

**Fix:** Check if the file exists:
```
dir edge\ppe_detection\models\
```
If missing, locate `ppe_final_v4.pt` on the team's shared drive and copy it
to `edge/ppe_detection/models/ppe_final_v4.pt`. If you're offline without the
model, use `demo/demo_inject_events.py` for the demo instead — it demonstrates
the same end-to-end flow.

---

### infer.py runs but no events appear in dashboard

**Cause 1:** `--api-url` flag was not provided, or points to the wrong port.
Check the infer.py command includes `--api-url http://127.0.0.1:8000/events`.

**Cause 2:** The image has no detectable PPE violations. The model only fires
events for violation classes (`no_helmet`, `no_vest`, `no_gloves`, etc.).
Use one of the `demo/sample_images/demo_violation_*.jpg` images which are
from the dataset used to train the model.

**Cause 3:** Confidence threshold too high. Lower it:
```
--conf 0.20
```

---

## Federated Learning Failures

### "ConnectionRefusedError" on client startup

**Cause:** The Flower server isn't running yet or isn't listening on the
expected port.

**Fix:** Start `flower_server.py` first and wait for
`=== Starting Flower FedAvg Server ===` before starting clients.

---

### Server waits forever and never starts rounds

**Cause:** `--min-clients 2` is set but only 1 client connected, or a client
crashed on startup.

**Fix:** Open a second terminal and start a second client with `--site-id site_2`.
Both clients must connect before the server starts Round 1.

---

### "gRPC transport error: Address already in use" on flower_server.py

**Cause:** A previous server process is still running on port 8089.

**Fix:** Find and kill the old server process, or use a different port:
```
python -m cloud.federated.flower_server --address 127.0.0.1:8090 --rounds 3 --min-clients 2
python -m cloud.federated.flower_client --site-id site_1 --server-address 127.0.0.1:8090
python -m cloud.federated.flower_client --site-id site_2 --server-address 127.0.0.1:8090
```

---

## General

### "ModuleNotFoundError: No module named 'cloud'" anywhere

**Cause:** The virtual environment is not activated, or you're running from
the wrong directory.

**Fix:** Always run commands from the **repo root** (`C:\Games\repo-setup\repo-setup`)
with the virtual environment active:
```
venv\Scripts\activate
```

---

### Tests fail with import errors after pulling latest

**Cause:** New dependencies were added to `requirements.txt`.

**Fix:**
```
venv\Scripts\python.exe -m pip install -r requirements.txt
```
