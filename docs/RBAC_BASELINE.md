# AEGIS Pre-RBAC Baseline Verification Report

Recorded on: 2026-10-29
Authoritative commit / folder: `C:\Games\repo-setup\repo-setup`
Backup location: `C:\Games\repo-setup\aegis_backup_before_rbac`

## 1. Test Suite Baseline
- `pytest --collect-only -q`: **151 tests collected** across backend, bandit, dashboard, federated, integration, PPE detection, process manager, and stream manager test suites.
- `pytest -q`: **151 passed, 2 warnings** in 6.61s.
- Existing warnings: StarletteDeprecationWarning regarding httpx and testclient deprecation.

## 2. Detection Parity Baseline
To guarantee the ML model and detection pipelines remain strictly unregressed throughout the RBAC implementation:

### 2.1 Zone Intrusion Pipeline Baseline Run
Command:
```powershell
python edge/zone_intrusion/tracking/zone_intrusion_pipeline.py `
  --source demo/videos/zone_intrusion_demo.mp4 `
  --zone_config edge/zone_intrusion/zones/camera_01_zones.json `
  --events_log baseline_zone_events.jsonl `
  --no-show
```
Results:
- **Total events fired**: 5
- **Class breakdown**:
  - `person_in_zone`: 5
- **Event detail log**:
  1. `person_6` (confidence: 0.32, timestamp: 2026-10-29T02:08:20Z, frame_count: 4, clip_captured: true)
  2. `person_14` (confidence: 0.23, timestamp: 2026-10-29T02:08:21Z, frame_count: 4, clip_captured: true)
  3. `person_65` (confidence: 0.38, timestamp: 2026-10-29T02:08:35Z, frame_count: 4, clip_captured: true)
  4. `person_75` (confidence: 0.35, timestamp: 2026-10-29T02:08:36Z, frame_count: 4, clip_captured: true)
  5. `person_79` (confidence: 0.25, timestamp: 2026-10-29T02:08:36Z, frame_count: 4, clip_captured: true)
- **Face blurring & clip recording**: 5 anonymized clips created in `clips/`.

### 2.2 PPE Detection (`infer.py`) Standalone Baseline Run
Command:
```powershell
python edge/ppe_detection/infer.py `
  --model edge/ppe_detection/models/ppe_final_v4.pt `
  --source demo/videos/zone_intrusion_demo.mp4 `
  --output-log baseline_infer_events.jsonl
```
Results:
- Processed 448 frames (384x640 at ~22ms/frame).
- Detections: multiple persons and helmets tracked across frames.
- Events triggered: 0 PPE violations (all personnel wear helmets in this demo clip).
- Log file and terminal summary emitted without error.

---

## 3. Core Feature Checklist & Verification Baseline

| Feature / Item | Pre-RBAC Status | Evidence / Verification Method |
|---|---|---|
| **Four Dashboard Tabs Render** | Verified Working | Confirmed `data-tab` nav items: `alerts` (Alert Feed), `stream` (Live Stream), `zones` (Draw Zone), `control` (Control Panel). All sections and DOM IDs exist in `dashboard/index.html`. |
| **Alert Feed & Filtering** | Verified Working | Loads `/alerts`, filters by camera, time range, keyword, and event type (`all`, `ppe_violation`, `zone_intrusion`). Detail view opens on alert selection. |
| **Simulate PPE / Zone Alerts** | Verified Working | `POST /events` with synthetic PPE violation or zone intrusion payloads. Generates new UUID `event_id`, invokes LinUCB bandit decisioning, and inserts row into SQLite DB. |
| **Operator Feedback** | Verified Working | `POST /feedback` records `confirmed` or `false_alarm` against event; updates bandit reward matrix. |
| **Thresholds & Policy History** | Verified Working | `GET /thresholds` returns live per-zone sensitivity thresholds. `GET /policy-history` returns version progression. |
| **Live Stream Worker** | Verified Working | `POST /stream/start` spawns background thread running YOLOv11 and ByteTrack on camera/video; MJPEG generator streams multipart frames; detection events posted to `/events`. `POST /stream/stop` cleans up threads. |
| **Zone Drawing Canvas** | Verified Working | `GET /capture-frame` retrieves frame from source; canvas supports Box and Polygon modes; `POST /zones` writes JSON config to `edge/zone_intrusion/zones/`; `GET /zones` lists zones; `DELETE /zones/{cam}/{zone}` removes file. |
| **Control Panel: Federated Learning** | Verified Working | `POST /processes/federated_demo/start` spawns Flower server on `127.0.0.1:8089` + 2 edge clients; completes 2 rounds of FedAvgRetrain; logs captured in 500-line ring buffer (`GET /processes/federated_demo/logs`). |
| **Control Panel: Zone Pipeline** | Verified Working | `POST /processes/zone_pipeline/start` executes standalone tracking pipeline on selected video; rings buffer captures logs; `POST /processes/zone_pipeline/stop` terminates subprocess. |
| **Retention Cleanup** | Verified Working | `POST /retention/cleanup` purges incident clips older than 7 days and event records exceeding retention cap. |
| **Standalone Edge Scripts** | Verified Working | `infer.py` and `zone_intrusion_pipeline.py` run independently from command line, writing JSONL logs to disk without mandatory network dependencies. |
| **Single-Command Launch** | Verified Working | `python run.py` initializes backend, launches static server on port 8000, polls `/health`, and opens browser automatically. |

