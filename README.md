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
- [ ] `INTERFACES.md` locked and agreed
- [ ] PPE detection — baseline trained
- [ ] Zone intrusion — detection + tracking working
- [ ] Bandit — offline-trained baseline policy
- [ ] Backend — event ingestion + feedback endpoint live
- [ ] Dashboard — alert feed + feedback buttons
- [ ] Federation — 2+ simulated sites demoed
