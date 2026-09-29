# Industrial Safety Monitoring System
### Edge-Cloud Collaborative AI System for Real-Time Video Analytics
Team 47 — BMS College of Engineering | Guide: Dr. Swetha P C

## What This Is
A single industrial safety camera system that detects PPE violations and
restricted-zone intrusions, and adapts its own alerting behavior over time
using operator feedback — without needing manual threshold tuning, without
full retraining cycles, and without raw video ever leaving a deployment site.

## Architecture (high level)
```
EDGE (Jetson Nano)                     CLOUD (FastAPI)                FEDERATED (Flower)
 PPE detection (YOLOv11n)      →       Contextual bandit        →     Local weights only
 Zone intrusion (RT-DETR/                (decision layer)              → FedAvg
   YOLOv11n + ByteTrack)       →       Dashboard + feedback loop       → Global policy
 Face-blur before upload               Incremental retrain +           → Redistributed
                                          validation gate
```

See `docs/decisions.md` for why each design choice was made.

## Repo Structure
- `edge/` — PPE detection + zone intrusion (Jetson Nano, inference only)
- `cloud/` — bandit decision layer, FastAPI backend, federated setup
- `dashboard/` — operator alert feed + feedback UI
- `tests/` — module tests (must pass before any PR merges — see CONTRIBUTING.md)
- `docs/` — decisions log, architecture diagrams, presentation notes
- `INTERFACES.md` — the shared event schema all modules must follow

## Team Split
| Person | Module |
|---|---|
| A | PPE detection (`edge/ppe_detection/`) |
| B | Zone intrusion (`edge/zone_intrusion/`) |
| C | Bandit decision layer (`cloud/decision_layer/`) |
| D | Backend + dashboard + federation (`cloud/backend/`, `cloud/federated/`, `dashboard/`) |

## Before You Touch Any Code
Read `CONTRIBUTING.md`. It covers branching, testing requirements, PR rules,
and how we avoid stepping on each other while working simultaneously.

## Current Status
<!-- Update this section as the project progresses -->
- [x] `INTERFACES.md` locked and agreed
- [x] PPE detection — baseline trained
- [x] Zone intrusion — detection + tracking working
- [x] Bandit — offline-trained baseline policy
- [x] Backend — event ingestion + feedback endpoint live
- [x] Dashboard — alert feed + feedback buttons + live stream + zone drawing + control panel
- [x] Federation — 2+ simulated sites demoed

## Running the Full System

### Single-Command Launch (Recommended)
Start the entire system — unified FastAPI backend, static operations dashboard, and process supervisor — with a single cross-platform command:

```bash
python run.py
```
*(On Windows with venv: `venv\Scripts\python.exe run.py`)*

This will:
1. Start the unified server on `0.0.0.0:8000`.
2. Display your localhost URL (`http://127.0.0.1:8000`) and LAN IP URL (e.g. `http://192.168.1.x:8000`) for phone or tablet access.
3. Automatically open your default web browser to the operations dashboard as soon as `/health` responds `200 OK`.
4. Allow you to launch federated learning training rounds and edge detection pipelines directly from the **Control Panel** tab in the browser, without opening separate terminal windows.
5. Cleanly shut down all background child processes and video streams on `Ctrl+C`.

> **Manual / Advanced (Separate Processes):**
> If you prefer running the backend and dashboard in isolated processes:
> ```bash
> # Terminal 1 (Backend API)
> uvicorn cloud.backend.main:app --host 0.0.0.0 --port 8000
>
> # Terminal 2 (Dashboard Static Server)
> python -m http.server 8080 --directory dashboard
> ```

