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

### 1. Configuration & Environment Tunables
Configuration is loaded from environment variables or a local `.env` file (copied from `.env.example`):

```bash
cp .env.example .env
```

Key environment tunables:
| Variable | Default | Purpose |
|---|---|---|
| `AEGIS_HOST` | `0.0.0.0` | Bind address (`127.0.0.1` for local-only, `0.0.0.0` for LAN access) |
| `AEGIS_PORT` | `8000` | Port for unified backend API and operations dashboard |
| `AEGIS_AUTH_ENABLED` | `true` | Enforces central default-deny RBAC on every route |
| `AEGIS_COOKIE_SECURE` | `false` | Set `true` in production when fronted by a TLS reverse proxy |
| `AEGIS_SESSION_IDLE_MINUTES` | `30` | Inactivity window before session expiration |
| `AEGIS_SESSION_ABSOLUTE_HOURS`| `12` | Hard maximum session duration |
| `AEGIS_LOGIN_MAX_FAILURES` | `5` | Failed login limit triggering 15-minute account throttle |
| `AEGIS_LOGIN_LOCKOUT_MINUTES`| `15` | Duration of login attempt lockout window |
| `AEGIS_MIN_PASSWORD_LENGTH` | `12` | Minimum character length for human passwords |
| `AEGIS_TRUSTED_PROXIES` | `127.0.0.1,::1` | Proxies permitted to populate `X-Forwarded-For` client IP |
| `AEGIS_CORS_ORIGINS` | `http://localhost:8000,...` | Allowed CORS origins (strict matching, no wildcards with credentials) |
| `AEGIS_RETENTION_DAYS` | `7` | Maximum age (days) for local incident clips before auto-pruning |
| `AEGIS_RETENTION_MAX_EVENTS` | `5000` | SQLite event limit before FIFO truncation |

### 2. Roles and Access Control (RBAC)

AEGIS enforces strict server-side Role-Based Access Control backed by a unified default-deny permission table:

#### Role Matrix
| Role | Identity Type | Purpose & Scope |
|---|---|---|
| `admin` | Human (User account) | Full access. User management, edge key issuance/revocation, process supervisor (federated demo, zone pipeline), zone configuration, retention cleanup, live stream controls (all sources), and audit trail review. |
| `operator` | Human (User account) | Daily safety operations. View alerts and alert details, submit feedback (confirms/false alarms), review thresholds and policy progression, view live stream (built-in webcam / demo video only), and read-only zone inspection. Control panel, process launches, zone editing, and simulations are restricted. |
| `edge` | Service Credential (API Key) | Edge producers (Jetson Nano nodes, standalone `infer.py`, `zone_intrusion_pipeline.py`, backend stream worker). Granted access strictly to `POST /events` to ingest detection events. Cannot read alerts, stream, or configure system. |

#### Authoritative Permission Matrix
| Method | Path Template | Anon | Operator | Admin | Edge | Notes |
|---|---|---|---|---|---|---|
| `GET` | `/health` | yes | yes | yes | yes | System liveness probe |
| `GET` | `/` | yes | yes | yes | yes | Static dashboard interface |
| `GET` | `/docs`, `/redoc`, `/openapi.json` | - | - | yes | - | API documentation restricted to Admin |
| `POST` | `/auth/login`, `/auth/logout` | yes | yes | yes | yes | Session initiation and termination |
| `GET` | `/auth/me` | - | yes | yes | yes | Active session / identity query |
| `POST` | `/auth/change-password` | - | yes | yes | yes | Forced on initial login or admin reset |
| `POST` | `/events` | - | - | yes | yes | Detection ingestion by edge producers |
| `POST` | `/feedback` | - | yes | yes | - | Operator human-in-the-loop decisions |
| `GET` | `/alerts`, `/alerts/{event_id}` | - | yes | yes | - | Read-only safety incident queries |
| `GET` | `/policy-history`, `/thresholds`| - | yes | yes | - | Read-only bandit policy queries |
| `POST` | `/stream/start` | - | built-in | yes | - | Operator: built-in only; Admin: custom RTSP/URLs |
| `POST` | `/stream/stop` | - | yes | yes | - | Stop running live stream worker |
| `GET` | `/stream/status`, `/mjpeg`, `/latest-frame` | - | yes | yes | - | Video stream monitoring |
| `GET` | `/zones` | - | yes | yes | - | Read-only zone polygon listing |
| `POST` | `/zones`, `DELETE /zones/{cam}/{zone}` | - | - | yes | - | Zone polygon configuration |
| `GET` | `/capture-frame` | - | - | yes | - | Reference frame calibration |
| `GET` | `/processes`, `/processes/{name}/logs` | - | - | yes | - | Background subprocess inspection |
| `POST` | `/processes/{name}/start`, `/stop` | - | - | yes | - | Federated demo and zone pipeline supervisor |
| `POST` | `/retention/cleanup` | - | - | yes | - | GDPR / storage bounded cleanup |
| `GET`, `POST` | `/admin/users*` | - | - | yes | - | User CRUD (atomic last-admin protection) |
| `GET`, `POST` | `/admin/edge-keys*` | - | - | yes | - | Edge device API key management |
| `GET` | `/admin/audit-log` | - | - | yes | - | Append-only security audit log |

### 2.1 CLI Account & Key Bootstrap (`cloud/backend/manage.py`)

Manage users and edge credentials directly from the command line:

```bash
# 1. Create Initial Administrator
python -m cloud.backend.manage create-admin --username admin --password "StrongAdminPass123!"

# 2. Create Safety Operator Account (Forces password change on first web login)
python -m cloud.backend.manage create-user --username operator_jane --role operator --temp-password "InitialTempPass123!"

# 3. List Registered Accounts
python -m cloud.backend.manage list-users

# 4. Issue Edge Device API Key (Secret shown once in terminal)
python -m cloud.backend.manage create-edge-key --label "jetson-nano-south-01"

# 5. List Edge Keys (Never displays raw secrets)
python -m cloud.backend.manage list-edge-keys

# 6. Revoke Edge Key
python -m cloud.backend.manage revoke-edge-key --prefix <key_prefix>

# 7. Reset User Password
python -m cloud.backend.manage reset-password --username operator_jane --temp-password "NewTempPass123!"
```

### 2.2 Security Architecture Details
- **Password Hashing:** Passwords are never stored in plaintext; hashed with Argon2id (`argon2-cffi`). Timing-attack mitigation employs pre-computed dummy verification.
- **Session Tokens:** 256-bit entropy (`secrets.token_urlsafe(32)`), stored as SHA-256 digests in SQLite. Delivered via `HttpOnly`, `SameSite=Strict` cookies.
- **CSRF Defense:** State-changing browser operations validate double-submit tokens (`X-CSRF-Token`).
- **Append-Only Audit Trail:** SQLite database triggers (`audit_log_no_update`, `audit_log_no_delete`) enforce append-only immutability at the engine level.
- **Internal Worker Credential:** Stream worker uses an ephemeral in-memory secret (`INTERNAL_STREAM_KEY`) generated once per backend lifespan and injected into child processes via environment variables (`AEGIS_EDGE_API_KEY`). No hardcoded keys exist in source code.

### 3. Data Retention & Incident Cleanup
- **Automated Startup Pruning:** The backend executes retention enforcement on server lifespan startup.
- **Manual Trigger:** Operators can trigger pruning on-demand from the **Control Panel** tab or via `POST /retention/cleanup`.
- **Privacy & Storage Bounds:** Incident video clips older than `AEGIS_RETENTION_DAYS` and database records exceeding retention windows are pruned, adhering to the best-effort storage commitments in `docs/decisions.md`.

### 4. Network Exposure & Hardening Recommendation
By default, `run.py` binds to `0.0.0.0:8000` to allow operators on factory-floor tablets or phones to view streams and acknowledge alerts. For deployment outside an air-gapped or trusted VLAN:
1. **Reverse Proxy (Nginx / Caddy):** Terminate TLS (HTTPS/WSS) in front of AEGIS.
2. **Firewall Rules:** Restrict port 8000 access to designated camera IP ranges and operator subnets.
3. **Bind to Localhost:** If using a reverse proxy on the same host, set `AEGIS_HOST=127.0.0.1`.

### 5. Honest Statement of Security Model & Residual Boundaries
- **Mandatory Reverse Proxy for TLS:** AEGIS does not implement native TLS termination. For production deployment, a reverse proxy (e.g., Nginx, Caddy, Cloudflare) must terminate HTTPS, and `AEGIS_COOKIE_SECURE` should be set to `true`.
- **Database at Rest:** SQLite databases (`aegis.db`) and recorded incident clips reside on the local filesystem with OS-level permissions. Systems requiring defense against physical disk seizure should employ OS-level full disk encryption (BitLocker, LUKS).
- **Scope Delimitations:** AEGIS implements RBAC with local password and session management. Enterprise single sign-on (SSO), SAML/OIDC federation, and hardware multi-factor authentication (WebAuthn/FIDO2) are beyond current scope.
- **Subprocess Isolation:** Background tasks run under the same OS service account as the backend process. Deployments on multi-tenant servers should run AEGIS within isolated containers or unprivileged systemd service units.


