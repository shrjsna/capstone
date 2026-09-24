# Demo Troubleshooting Guide

Real failure modes observed during testing, plus the likely ones for a live
presentation.

---

## Backend

### `[Errno 10048] address already in use` on port 8000
A previous uvicorn process is still running.

**Fix (Windows):**
```
netstat -ano | findstr :8000
taskkill /F /PID <PID shown in last column>
```
Then retry `uvicorn cloud.backend.main:app --reload --host 127.0.0.1 --port 8000`.
If you want to avoid hunting the PID, use a different port and pass it everywhere:
```
uvicorn cloud.backend.main:app --host 127.0.0.1 --port 8001
# then add --api-url http://127.0.0.1:8001/events to infer.py calls
# and update the API URL field in the dashboard to http://127.0.0.1:8001
```

### Backend starts then immediately exits
Usually a Python import error. Run without `--reload` to see the full traceback:
```
python -m uvicorn cloud.backend.main:app --host 127.0.0.1 --port 8000
```

### `422 Unprocessable Entity` on POST /events
The payload is missing a required field or has the wrong type. The most common
mistake: sending `class_name` instead of `class` — the JSON key must be exactly
`"class"`. Check the body against `INTERFACES.md` schema 1.

### `404 Not Found` on POST /feedback
The `event_id` in the feedback payload doesn't exist in SQLite. This happens if:
- The database was wiped (`del cloud_backend.db`) after the event was posted.
- The event was posted to a different server instance.
Fix: re-post the event first, then submit feedback with the fresh event_id.

### `database is locked` error
Two processes (e.g. a stale uvicorn + a new one) are accessing the same SQLite
file simultaneously. Kill all uvicorn processes and delete `cloud_backend.db`,
then restart fresh.

---

## Dashboard

### Dashboard shows "No Safety Alerts Detected" and never refreshes
Backend is not running or is on a different port than what the dashboard shows
in the API URL field.
- Confirm uvicorn is running: `curl http://127.0.0.1:8000/health` should return `{"status":"ok"}`.
- Check the API URL field in the top bar of the dashboard — it defaults to
  `http://127.0.0.1:8000`. If your backend is on 8001, change it to match.

### CORS error in browser console
Only happens if you open `index.html` as a `file://` URL instead of through
the HTTP server. Always use:
```
python -m http.server 8080 --directory dashboard
```
then open `http://localhost:8080` — not `file://`.

### "Failed to send feedback" alert when clicking Confirm / False Alarm
The event_id from the alert card is no longer in the database. Delete
`cloud_backend.db`, restart the backend, and re-post a fresh event first.

---

## Module A — PPE Detection (infer.py)

### `FileNotFoundError: Model file not found at edge/ppe_detection/models/ppe_final_v4.pt`
The model weights file is not in the repo (excluded by .gitignore). You need to
have it locally. Confirm: `dir edge\ppe_detection\models\`. If missing, copy it
from wherever it was trained/stored.

### infer.py runs but posts no events to the backend
- The debounce filter (default: 3 consecutive frames) means a still image only
  gives 1 frame of detection — the event never fires.
- **Solution for still images in the demo**: use `--debounce 1`.
- Alternatively run on a short video clip (MP4) where the violation appears in
  multiple consecutive frames.

### `--source 0` opens the wrong camera
Most laptops have camera index 0 = built-in webcam, 1 = external USB camera.
Test before the presentation: `python edge/ppe_detection/infer.py --model edge/ppe_detection/models/ppe_final_v4.pt --source 0 --show`
If the wrong camera opens, try `--source 1`.

### YOLO prints `WARNING: NMS time limit 0.550s exceeded`
Normal under load — it means inference took slightly too long for one frame.
Not a failure. If it persists, add `--conf 0.35` to skip marginal detections.

---

## Module B — Zone Intrusion (zone_intrusion_pipeline.py)

### `ConnectionRefusedError` when posting to backend
Backend is not running. Start it first; then start zone_intrusion_pipeline.py.

### The zone polygon is not drawing over my camera feed
The zone config (`zones/camera_01_zones.json`) has coordinates calibrated for a
1050×1000 frame. If your camera resolution differs, the polygon will appear in
the wrong position but the zone-check logic still uses those exact pixel
coordinates. Recalibrate `polygon` in the JSON for your camera.

### Pipeline posts no events even though a person is visible in the zone
- Default `--debounce_frames 4` — the person must be continuously in-zone for
  4 consecutive frames before an event fires. Normal for a live feed.
- Check that `zone_id` in the events log matches the zone config's `"zone_id"`.

---

## Federation (Flower)

### `DEPRECATED FEATURE` warnings from flower_server.py and flower_client.py
The installed Flower version emits `DEPRECATED FEATURE: flwr.server.start_server()` and
`DEPRECATED FEATURE: flwr.client.start_numpy_client()` warnings at startup. These are
cosmetic — both functions still work correctly and the 2-round FedAvg demo completes
without errors. The rounds proceed normally: `[ROUND 1] aggregate_fit: received 2 results
and 0 failures`. Safe to ignore for the presentation.

### Port Conflict (`gRPC transport error: Address already in use`) on flower_server.py
A previous server process is still alive. Kill it:
```
netstat -ano | findstr :8089
taskkill /F /PID <PID>
```
Or use a different port: `--address 127.0.0.1:8090` and `--server-address 127.0.0.1:8090`.

### Server waits forever and never starts Round 1
Not enough clients connected. Server requires `--min-clients 2` to start.
Open two separate terminals, each running flower_client.py with a different
`--site-id`, before the server can proceed.

### Client crashes with `AttributeError: args.site-id`
This is a known bug in the original `flower_client.py` error handler:
`args.site-id` should be `args.site_id` (underscore, not hyphen).
It only triggers when the gRPC connection fails — if the server is running
correctly, this code path won't be reached. Workaround: start the server
first, wait for it to print `gRPC server running`, then start clients.

---

## General

### `ModuleNotFoundError: No module named 'cloud'` or `'edge'`
You are not running from the repo root, or the virtual environment is not
active.
```
# Always run from repo root:
cd C:\Games\repo-setup\repo-setup
venv\Scripts\activate
```

### Tests pass but live server behaves differently
The test suite uses an in-memory SQLite DB. The live server creates
`cloud_backend.db` on disk. Stale data in the on-disk DB can cause confusion.
Delete `cloud_backend.db` and restart to get a clean state.
