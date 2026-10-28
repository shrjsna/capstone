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

---

## Deploying for Real Use

While AEGIS was initially prototyped for single-machine demonstration, this production-readiness pass hardens the server for unattended, 24/7 network operation on an industrial LAN.

### 1. Configuration & Security Credentials
Configuration is loaded from environment variables or a local `.env` file (copied from `.env.example`):

```bash
cp .env.example .env
```

Key environment variables:
| Variable | Default | Purpose |
|---|---|---|
| `AEGIS_HOST` | `0.0.0.0` | Bind address (`127.0.0.1` for local-only, `0.0.0.0` for LAN access) |
| `AEGIS_PORT` | `8000` | Port for unified backend API and dashboard |
| `AEGIS_API_KEY` | `aegis-secret-key-2026` | **Mandatory shared secret** required on all state-mutating endpoints |
| `AEGIS_AUTH_REQUIRED` | `true` | When `true`, enforces API key checks on mutating routes |
| `AEGIS_CORS_ORIGINS` | `http://localhost:8000,...` | Comma-delimited list of permitted CORS origins (no wildcards by default) |
| `AEGIS_RETENTION_DAYS` | `7` | Maximum age (days) for local `.mp4`/`.avi` incident clips before auto-pruning |
| `AEGIS_RETENTION_MAX_EVENTS` | `5000` | SQLite event limit before FIFO truncation |
| `AEGIS_MAX_MJPEG_CLIENTS` | `10` | Concurrency ceiling for simultaneous live stream viewers |

### 2. Authentication & Provenance Model
- **Protected Endpoints:** All state-changing routes (`POST /events`, `POST /feedback`, `POST /zones`, `DELETE /zones/{cam}/{zone}`, `POST /stream/start`, `POST /stream/stop`, `POST /processes/{name}/start`, `POST /processes/{name}/stop`, `POST /retention/cleanup`) require the API key.
- **Header Delivery:** Send `X-API-Key: <your-key>` (or `Authorization: Bearer <your-key>`).
- **Dashboard Integration:** Click the operator badge (`👤 op_admin 🔒`) in the top-right header to configure your operator call-sign and API key. Stored locally in browser `localStorage`.
- **Operator Provenance:** Human feedback (`POST /feedback`) records both the verified session key and the operator identifier (`X-Operator-ID` or payload `operator_id`) to maintain an accountable audit trail.

### 3. Data Retention & Incident Cleanup
- **Automated Startup Pruning:** The backend executes retention enforcement on server lifespan startup.
- **Manual Trigger:** Operators can trigger pruning on-demand from the **Control Panel** tab or via `POST /retention/cleanup`.
- **Privacy & Storage Bounds:** Incident video clips older than `AEGIS_RETENTION_DAYS` and database records exceeding retention windows are pruned, adhering to the best-effort storage commitments in `docs/decisions.md`.

### 4. Network Exposure & Hardening Recommendation
By default, `run.py` binds to `0.0.0.0:8000` to allow operators on factory-floor tablets or phones to view streams and acknowledge alerts. For deployment outside an air-gapped or trusted VLAN:
1. **Reverse Proxy (Nginx / Caddy):** Terminate TLS (HTTPS/WSS) in front of AEGIS.
2. **Firewall Rules:** Restrict port 8000 access to designated camera IP ranges and operator subnets.
3. **Bind to Localhost:** If using a reverse proxy on the same host, set `AEGIS_HOST=127.0.0.1`.

### 5. Honest Statement of Residual Security Gaps
To prevent false assumptions regarding production security, note the following architectural boundaries:
- **No TLS / HTTPS Out of the Box:** AEGIS runs plain HTTP. Any traffic over untrusted networks can be intercepted unless fronted by a TLS reverse proxy.
- **Shared Secret vs. Individual Accounts:** Authentication uses a single shared secret key (`AEGIS_API_KEY`) and self-asserted operator call-signs, not individual user accounts, OAuth2/OIDC, or salted per-user password hashes.
- **No Role-Based Access Control (RBAC):** Any holder of the valid API key has full permissions (can acknowledge alerts, start/stop processes, delete zones, and trigger retention cleanups).
- **Local File Storage:** SQLite databases and video clips are stored with standard filesystem permissions without at-rest encryption. Ensure proper OS-level filesystem ACLs on the host machine.


