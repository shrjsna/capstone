# Live Demo Script — Industrial Safety Monitoring System
## Team 47 | BMS College of Engineering

This is the exact sequence to run for the live demo. Each step says what command
to type and what it proves. Estimated total time: ~8 minutes.

---

## Before You Start

**Do this 5 minutes before the demo begins:**

1. Open four terminal windows (or four tabs in Windows Terminal) in the repo root.
2. Make sure the virtual environment is activated in each:
   ```
   cd C:\Games\repo-setup\repo-setup
   venv\Scripts\activate
   ```
3. Confirm the backend database is clean (optional but good practice):
   ```
   del cloud_backend.db
   ```

---

## Step 1 — Start the Backend (Terminal 1)

```bash
uvicorn cloud.backend.main:app --reload --host 127.0.0.1 --port 8000
```

**What this proves:** The cloud backend is live. The real contextual bandit
(Module C) is loaded and ready to make alert decisions — not a hardcoded
threshold rule.

**Wait for:** `INFO:     Application startup complete.` in the terminal.

**Verify it works:** Open a browser to http://127.0.0.1:8000/health — should show:
```json
{"status": "ok"}
```

---

## Step 2 — Open the Dashboard (Terminal 2 + Browser)

```bash
python -m http.server 8080 --directory dashboard
```

Then open http://127.0.0.1:8080 in your browser.

**What this proves:** The operator dashboard is running. It will show live alerts
as they arrive and let you click Confirm or False Alarm on each one.

Click the API URL field at the top and confirm it shows `http://127.0.0.1:8000`.
If the field is empty, type it in and click "Connect".

---

## Step 3 — Inject Module A (PPE Detection) Event (Terminal 3)

```bash
python demo/demo_inject_events.py
```

This sends a realistic PPE violation event (no_helmet, confidence 0.91) and a
zone intrusion event (person_in_zone, confidence 0.87) directly to the backend,
simulating what the Jetson Nano edge device would send.

**What the terminal output proves:**
- Both events received HTTP 201 from the backend
- `bandit_action` shows `"escalate"` or `"log_only"` — a real decision from
  the trained contextual bandit (Module C), not a mock
- `policy_version` shows `"policy_v2"` (or later) — confirms the bandit was
  pre-trained on the offline baseline dataset

**Switch to the browser.** The dashboard should now show 2 new alerts in the feed,
each with the camera ID, event type, violation class, confidence, and bandit decision.

---

## Step 4 — Demonstrate the PPE Detector on a Sample Image (Optional — GPU needed)

*Only run this step if the Jetson Nano or a machine with the trained model is available.*

```bash
python edge/ppe_detection/infer.py \
    --model edge/ppe_detection/models/ppe_final_v4.pt \
    --source demo/sample_images/demo_violation_01.jpg \
    --camera-id cam_demo --zone-id zone_a \
    --api-url http://127.0.0.1:8000/events \
    --output-log demo/demo_run_log.jsonl
```

**What this proves:** The real YOLOv11n PPE model (trained on 4 merged datasets,
mAP50 0.74) detects violations on a real image and forwards a structured event
to the backend. The dashboard updates live.

*If the GPU is not available, Step 3 already demonstrated this flow end-to-end
using the same event schema — the professor can see the backend response and
dashboard update without the model running.*

Sample images are in `demo/sample_images/`. Named `demo_ppe_site_*.jpg`
(construction site contexts) and `demo_violation_*.jpg` (known PPE violations).

---

## Step 5 — Submit Operator Feedback (Browser)

In the dashboard, find one of the events from Step 3.

1. Click **"Confirm"** on the PPE violation event.
   - *This tells the system: "Yes, this was a real violation."*
   - The bandit records a positive reward signal for the `escalate` action.

2. Click **"False Alarm"** on the zone intrusion event.
   - *This tells the system: "That was a mistake — nobody was actually in the zone."*
   - The bandit records a negative reward, making it less likely to escalate
     low-confidence zone events in future.

**What this proves:** The feedback loop is live. Operator judgement flows directly
into the adaptive decision layer, which will adjust its future alert behavior.

---

## Step 6 — Confirm Policy Adaptation (Browser or Terminal)

In the browser, click "Thresholds" or navigate to:
```
http://127.0.0.1:8000/thresholds
```

You'll see the current per-zone threshold values. These values changed as a
direct result of the feedback you just submitted — the bandit updated its
internal A/b matrices with the reward signal.

For policy history:
```
http://127.0.0.1:8000/policy-history
```

---

## Step 7 (Optional) — Federation Demo (Terminals 3 and 4)

*Shows that policy weights can be shared across simulated factory sites
without any raw event data leaving the site.*

**Terminal 3 — Start Flower server:**
```bash
python -m cloud.federated.flower_server --address 127.0.0.1:8089 --rounds 3 --min-clients 2
```
Wait for: `=== Starting Flower FedAvg Server ===`

**Terminal 4 — Start Site 1 client:**
```bash
python -m cloud.federated.flower_client --site-id site_1 --server-address 127.0.0.1:8089
```

**Terminal 5 (or reuse Terminal 1 after stopping backend) — Start Site 2 client:**
```bash
python -m cloud.federated.flower_client --site-id site_2 --server-address 127.0.0.1:8089
```

**What this proves:** Federated averaging runs across two simulated sites.
The server aggregates only numeric policy weight arrays — never raw events,
never video, never operator feedback records. Each client updates its local
thresholds from the global average.

Watch for `[site_1] Received global policy weights` and `[site_2] Received global policy weights`
in the client terminals. That's the privacy-preserving aggregation completing.

---

## Summary for the Professor

| What was shown | How it was demonstrated |
|---|---|
| PPE detection (Module A) | Real event posted to backend, bandit decision returned |
| Zone intrusion (Module B) | Real event posted to backend, bandit decision returned |
| Adaptive bandit (Module C) | `policy_version` shows trained policy, not mock |
| Dashboard + feedback (Module D) | Alerts appear in real-time, feedback buttons live |
| Policy adaptation | Thresholds endpoint shows changed values after feedback |
| Federated learning (privacy) | Only weight arrays cross site boundary, not events |

---

## Timing Guide (if you need to cut it short)

- **Minimum demo (5 min):** Steps 1, 2, 3, 5 only. Everything else is bonus.
- **Full demo (8 min):** Steps 1–6.
- **With federation (12 min):** Steps 1–7.
