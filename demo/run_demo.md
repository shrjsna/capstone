# Live Demo Script — Industrial Safety Monitoring System
**Team 47 | BMS College of Engineering**
*All commands below were verified end-to-end during integration testing.*

---

## Before You Start (5 minutes before the demo)

1. Open **5 terminal windows** (or tabs) in the repo root.
   In every terminal, activate the virtual environment first:
   ```
   cd C:\Games\repo-setup\repo-setup
   venv\Scripts\activate
   ```
   If PowerShell blocks activation with `running scripts is disabled`, use this instead:
   ```
   venv\Scripts\python.exe <your-command>
   ```
   Or open Command Prompt (cmd.exe) where activation works without the policy restriction.
2. Delete any stale database to start clean:
   ```
   del cloud_backend.db
   ```
3. Confirm the model weights file is present:
   ```
   dir edge\ppe_detection\models\ppe_final_v4.pt
   ```
   Must show `16.0 MB`. If missing, copy it now — the demo cannot run without it.
   See `demo/backup_plan.md`.

---

## Step 1 — Start the Backend (Terminal 1)

```bash
uvicorn cloud.backend.main:app --reload --host 127.0.0.1 --port 8000
```

**Wait for:**
```
INFO:     Application startup complete.
```
*This confirms the FastAPI server, SQLite database, and real contextual bandit
(Module C) are all initialised. The bandit loads its pre-trained policy_v1
baseline automatically.*

**Verify it's alive** — open a new terminal tab and run:
```bash
curl http://127.0.0.1:8000/health
```
Expected: `{"status":"ok"}`

---

## Step 2 — Open the Dashboard (Terminal 2 + Browser)

```bash
python -m http.server 8080 --directory dashboard
```

Then open your browser at: **http://localhost:8080**

*What to show: the dark industrial operations console loads. The alert feed is
empty — it will fill as events arrive. The threshold meters show the bandit's
current per-zone sensitivity.*

---

## Step 3 — PPE Detection: Module A (Terminal 3)

Run inference on each curated demo image. The `--debounce 1` flag makes the
detector fire on a single frame (normal for still images; live video uses the
default of 3).

### Image 1 — No Helmet (confidence 0.9214 — highest scoring in test set)
```bash
python edge/ppe_detection/infer.py \
    --model edge/ppe_detection/models/ppe_final_v4.pt \
    --source "demo/images/demo_no_helmet_01_conf92.jpg" \
    --camera-id cam_demo_01 \
    --zone-id zone_A \
    --debounce 1 \
    --api-url http://127.0.0.1:8000/events \
    --output-log demo/events_ppe.jsonl
```
*What this proves: the YOLOv11n model detects a no-helmet violation with 0.92
confidence, the event is forwarded to the backend, and the contextual bandit
(Module C) makes a real-time action decision (escalate / log_only /
adjust_threshold) based on its trained policy.*

### Image 2 — No Vest (confidence 0.9630 — top scoring no_vest image)
```bash
python edge/ppe_detection/infer.py \
    --model edge/ppe_detection/models/ppe_final_v4.pt \
    --source "demo/images/demo_no_vest_01_conf96.jpg" \
    --camera-id cam_demo_01 \
    --zone-id zone_A \
    --debounce 1 \
    --api-url http://127.0.0.1:8000/events \
    --output-log demo/events_ppe.jsonl
```
*What this proves: the same pipeline handles multiple PPE violation classes.*

### Image 3 — No Gloves (confidence 0.8466)
```bash
python edge/ppe_detection/infer.py \
    --model edge/ppe_detection/models/ppe_final_v4.pt \
    --source "demo/images/demo_no_gloves_01_conf84.jpg" \
    --camera-id cam_demo_01 \
    --zone-id zone_A \
    --debounce 1 \
    --api-url http://127.0.0.1:8000/events \
    --output-log demo/events_ppe.jsonl
```

**After each image run:** switch to the browser. Each event should appear as a
new card in the dashboard feed within 2 seconds (the dashboard polls every 2s).
Each card shows the violation class, confidence, camera ID, and the bandit's
decision.

---

## Step 4 — Zone Intrusion: Module B (Terminal 3, same terminal)

### Option A — Video file (preferred if available)
```bash
python -m edge.zone_intrusion.tracking.zone_intrusion_pipeline \
    --source demo/videos/zone_intrusion_demo.mp4 \
    --zone_config edge/zone_intrusion/zones/camera_01_zones.json \
    --debounce_frames 4 \
    --events_log demo/zone_intrusion_events.jsonl
```
*Note: This does NOT have an `--api-url` flag — Module B logs to JSONL. To get
it into the dashboard for the demo, use Option B in parallel or afterwards.*

*What to point at: the terminal prints `EVENT FIRED:` with a JSON object matching
`INTERFACES.md` schema exactly — same `event_type`, `confidence`, `tracked_id`,
`timestamp` fields.*

### Option B — Dashboard inject button (fallback, or use to show it in the feed)
In the browser at `http://localhost:8080`, click **"+ Zone Intrusion"**.
This calls `POST /events` directly with a realistic zone_intrusion payload.
The bandit makes a real decision and the event appears in the feed immediately.

*What this proves: the backend accepts zone intrusion events on the same
`/events` endpoint as PPE events. Module D is module-agnostic.*

---

## Step 5 — Dashboard Feedback (Browser)

In the dashboard at `http://localhost:8080`:

1. Find the **no_helmet** event card.
2. Click **"Confirm"**.
   - *What this proves: confirmed violations strengthen the bandit's escalate
     policy — it will escalate similar future events more aggressively.*
3. Find the **zone_intrusion** event card.
4. Click **"False Alarm"**.
   - *What this proves: false alarms penalise the escalate action, reducing
     alert fatigue over time — the system self-adjusts without manual tuning.*

**Verify the feedback reached the backend:**
```bash
curl http://127.0.0.1:8000/thresholds
```
The threshold values reflect the bandit's updated internal state.

---

## Step 6 — Confirm Bandit Policy Adaptation (Terminal 3)

```bash
curl http://127.0.0.1:8000/policy-history
```
Shows the current policy version and validation score.

```bash
curl http://127.0.0.1:8000/thresholds
```
Shows live per-zone thresholds that changed as a result of the feedback in Step 5.

*What this proves: Module C (the contextual bandit) adapted its policy in real
time from operator feedback — this is the "self-maintaining" behaviour described
in the project abstract.*

---

## Step 7 — Federated Learning Demo (Terminals 4 and 5)

### Terminal 4 — Start Flower Server
```bash
python -m cloud.federated.flower_server --address 127.0.0.1:8089 --rounds 2 --min-clients 2
```
**Wait for:** `Flower ECE: gRPC server running (2 rounds), SSL is disabled`

### Terminal 5 — Start Site 1 Client
```bash
python -m cloud.federated.flower_client --site-id site_1 --server-address 127.0.0.1:8089
```

### Back to Terminal 4 (or open Terminal 6) — Start Site 2 Client
```bash
python -m cloud.federated.flower_client --site-id site_2 --server-address 127.0.0.1:8089
```

**Wait for (server terminal):**
```
[ROUND 1]
aggregate_fit: received 2 results and 0 failures
[ROUND 2]
aggregate_fit: received 2 results and 0 failures
[SUMMARY]
Run finished 2 round(s) in ~20s
```

*What this proves: two simulated factory sites (site_1 and site_2) share
their policy weights with the Flower server, which applies FedAvg to produce
a global policy. Crucially — only numeric weight floats cross the network
boundary. No raw events, no video, no operator feedback leave the local site.
This is the privacy-preserving federated learning story.*

*Point at the client terminal output — it shows `Updated local thresholds:
{'zone_a': 0.68, 'zone_b': 0.72, 'default': 0.68}` — numeric policy
parameters only.*

---

## Live Webcam Cheat-Sheet

Replace any `--source "demo/images/..."` or `--source demo/videos/...` with
`--source 0` to use the live webcam.

| Original command arg | Live webcam replacement |
|---|---|
| `--source "demo/images/demo_no_helmet_01_conf92.jpg"` | `--source 0` |
| `--source demo/videos/zone_intrusion_demo.mp4` | `--source 0` |

**Test your camera index before presentation day:**
```bash
python edge/ppe_detection/infer.py \
    --model edge/ppe_detection/models/ppe_final_v4.pt \
    --source 0 \
    --show
```
If the wrong camera opens (or you get a black screen), try `--source 1`.

For Module B with webcam:
```bash
python -m edge.zone_intrusion.tracking.zone_intrusion_pipeline \
    --source 0 \
    --zone_config edge/zone_intrusion/zones/camera_01_zones.json
```

**Drop `--debounce 1` when using a live camera** — the default debounce of 3
consecutive frames is appropriate for live video and prevents false one-frame
alerts.

---

## Timing Guide

| Step | Realistic time |
|---|---|
| Setup + backend start | 1–2 min |
| Dashboard open | 30 sec |
| 3 PPE images + events in dashboard | 2–3 min |
| Zone intrusion (video or button) | 1 min |
| Dashboard feedback (Confirm + False Alarm) | 1 min |
| Bandit state check (curl thresholds) | 30 sec |
| Federation (start server + 2 clients, 2 rounds) | ~2–3 min (rounds complete in ~15s once both clients connect) |
| **Total** | **~9–11 min** |

*Timing verified 2026-09-23: federation 2 rounds ran in 15.48s once both clients connected.*
