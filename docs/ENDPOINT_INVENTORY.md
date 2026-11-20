# AEGIS API Route & Detection Producer Inventory

Authoritative inventory verified against FastAPI application inspection (`app.routes`) and codebase audit.

## 1. Route Inventory

| Method | Path Template | Handler (File:Function) | Request Fields / Body | Existing Protection | Primary Caller | Proposed Role | Notes / Rationale |
|---|---|---|---|---|---|---|---|
| `GET` | `/health` | `cloud/backend/main.py:health_check` | None | None | Browser / Poller / `run.py` | Anon, Operator, Admin, Edge | System liveness probe; open to all. |
| `POST` | `/events` | `cloud/backend/main.py:receive_detection_event` | `camera_id`, `zone_id`, `event_type`, `class_name`, `confidence`, `tracked_id`, `timestamp`, `frame_count_triggered`, `clip_captured` | `verify_api_key` | Edge producers (`infer.py`, zone pipeline, internal stream worker) & Admin simulate buttons | Edge, Admin | Operator refused. Producers send detection events; Admins may simulate events for bandit training. |
| `POST` | `/feedback` | `cloud/backend/main.py:submit_operator_feedback` | `event_id`, `feedback` (`confirmed`/`false_alarm`), `operator_id` (retired from payload; derived from session) | `verify_api_key` | Dashboard (Operator & Admin) | Operator, Admin | Identity taken from session user to maintain human provenance. |
| `GET` | `/alerts` | `cloud/backend/main.py:get_alerts` | Query: `limit`, `event_type`, `camera_id` | None | Dashboard feed | Operator, Admin | Reading alert lists for safety monitoring. |
| `GET` | `/alerts/{event_id}` | `cloud/backend/main.py:get_alert_detail` | Path: `event_id` | None | Dashboard alert modal | Operator, Admin | Alert detail view. |
| `GET` | `/policy-history` | `cloud/backend/main.py:get_policy_history` | None | None | Dashboard | Operator, Admin | Read-only policy version progression history. |
| `GET` | `/thresholds` | `cloud/backend/main.py:get_current_thresholds` | None | None | Dashboard | Operator, Admin | Read-only zone sensitivity thresholds. |
| `POST` | `/stream/start` | `cloud/backend/main.py:stream_start` | `source`, `mode`, `model_path`, `zone_config_path`, `camera_id`, `zone_id`, `debounce_frames`, `conf_threshold` | `verify_api_key` | Dashboard live stream tab | Operator (built-in sources only), Admin (all including custom URLs) | Custom URL forces server connection; restricted to Admin. Built-in webcams/demo videos allowed for Operator. |
| `POST` | `/stream/stop` | `cloud/backend/main.py:stream_stop` | None | `verify_api_key` | Dashboard live stream tab | Operator, Admin | Stop active live stream. |
| `GET` | `/stream/status` | `cloud/backend/main.py:stream_status_endpoint` | None | None | Dashboard live stream tab | Operator, Admin | Stream status query. |
| `GET` | `/stream/mjpeg` | `cloud/backend/main.py:stream_mjpeg` | None | None | Dashboard `<img>` element | Operator, Admin | MJPEG streaming video; cookie session authenticated. |
| `GET` | `/stream/latest-frame` | `cloud/backend/main.py:stream_latest_frame` | None | None | Dashboard fallback / preview | Operator, Admin | Single annotated JPEG frame. |
| `GET` | `/capture-frame` | `cloud/backend/main.py:capture_frame` | Query: `source` (camera index, path, or RTSP URL) | None | Dashboard Draw Zone tab | Admin | Opens server-side media capture for zone drawing. Admin-only. |
| `GET` | `/zones` | `cloud/backend/main.py:list_zones` | None | None | Dashboard live stream & Draw Zone tabs | Operator, Admin | Read-only list of configured detection polygons. |
| `POST` | `/zones` | `cloud/backend/main.py:save_zone` | `camera_id`, `zone_id`, `polygon`, `zone_type` | `verify_api_key` | Dashboard Draw Zone tab | Admin | Zone creation defines intrusion geometry; Admin-only. |
| `DELETE` | `/zones/{camera_id}/{zone_id}` | `cloud/backend/main.py:delete_zone` | Path: `camera_id`, `zone_id` | `verify_api_key` | Dashboard Draw Zone tab | Admin | Zone deletion defines intrusion geometry; Admin-only. |
| `GET` | `/processes` | `cloud/backend/main.py:list_managed_processes` | None | None | Dashboard Control Panel tab | Admin | Lists subprocess states; Admin-only. |
| `POST` | `/processes/{name}/start` | `cloud/backend/main.py:start_managed_process` | Path: `name` (`federated_demo`, `zone_pipeline`); Body: `source` (optional for zone_pipeline) | `verify_api_key` | Dashboard Control Panel tab | Admin | Launches background jobs. Admin-only. |
| `POST` | `/processes/{name}/stop` | `cloud/backend/main.py:stop_managed_process` | Path: `name` (`federated_demo`, `zone_pipeline`) | `verify_api_key` | Dashboard Control Panel tab | Admin | Terminates background jobs. Admin-only. |
| `GET` | `/processes/{name}/logs` | `cloud/backend/main.py:get_managed_process_logs` | Path: `name` | None | Dashboard Control Panel tab | Admin | Subprocess ring buffer logs; can reveal internal paths. Admin-only. |
| `POST` | `/retention/cleanup` | `cloud/backend/main.py:trigger_retention_cleanup` | None | `verify_api_key` | Dashboard Control Panel tab | Admin | Permanent deletion of historical data/clips; Admin-only. |
| `GET` / `HEAD` | `/` and static mount | `cloud/backend/main.py:app.mount` | None | None | Web browser | Anon, Operator, Admin, Edge | Serves static assets (`index.html`, `app.js`, `styles.css`); unauthenticated for login screen. |
| `GET` / `HEAD` | `/openapi.json`, `/docs`, `/redoc` | FastAPI built-ins | None | None | API consumers / Swagger | Admin | Exposes complete internal API surface; Admin-only. |
| `POST` | `/auth/login` | `cloud/backend/auth.py:login` (new) | `username`, `password` | Throttling | Web browser / clients | Anon, Operator, Admin | Issues session cookie. |
| `POST` | `/auth/logout` | `cloud/backend/auth.py:logout` (new) | None | Session cookie + CSRF | Web browser | Operator, Admin | Revokes server session & clears cookie. |
| `GET` | `/auth/me` | `cloud/backend/auth.py:me` (new) | None | Session cookie | Web browser | Operator, Admin | Returns current user identity, role, and CSRF token. |
| `POST` | `/auth/change-password` | `cloud/backend/auth.py:change_password` (new) | `old_password`, `new_password` | Session cookie + CSRF | Web browser | Operator, Admin | Self password update; clears `must_change_password`. |
| `GET` | `/admin/users` | `cloud/backend/users_admin.py:list_users` (new) | None | Session cookie | Dashboard Users page | Admin | Lists user accounts (never returns hashes). |
| `POST` | `/admin/users` | `cloud/backend/users_admin.py:create_user` (new) | `username`, `role`, `temp_password` | Session cookie + CSRF | Dashboard Users page | Admin | Creates operator/admin account. |
| `PATCH` | `/admin/users/{id}` | `cloud/backend/users_admin.py:update_user` (new) | `role`, `active` | Session cookie + CSRF | Dashboard Users page | Admin | Account modifications with last-admin protection. |
| `POST` | `/admin/users/{id}/reset-password` | `cloud/backend/users_admin.py:reset_password` (new) | `temp_password` | Session cookie + CSRF | Dashboard Users page | Admin | Sets `must_change_password=1` and revokes sessions. |
| `GET` | `/admin/audit-log` | `cloud/backend/audit.py:get_audit_log` (new) | Query: `from`, `to`, `actor`, `action`, `outcome`, `limit`, `offset` | Session cookie | Dashboard Audit page | Admin | Paginated append-only audit trail. |

### Photo/Video Detection Route Audit
A project-wide code search confirmed:
- No `/detect`, `/detect-video`, `/detect-photo`, or `/detect-image` endpoint exists anywhere in the codebase.
- Ingestion occurs solely via `POST /events` using the contract defined in `INTERFACES.md`.

---

## 2. Detection Producers Survey

| Producer | Execution Context | How Started | How Events Are Emitted | Destination URL | Authentication Post-RBAC |
|---|---|---|---|---|---|
| **1. Live Stream Worker** | Backend process; background thread (`_stream_worker` in `stream_manager.py`) | Via `POST /stream/start` | Uses `requests.post()` | `http://127.0.0.1:{PORT}/events` | In-memory internal edge service credential (`internal-stream`), generated at startup and rotated on each restart. Valid only for `POST /events`. |
| **2. `infer.py`** | Standalone Python process | Executed directly from terminal or edge device: `python edge/ppe_detection/infer.py` | Uses `requests.post()` in `post_event()` | Configurable via `--api-url` (e.g. `http://127.0.0.1:8000/events`) | `--api-key` CLI parameter or `AEGIS_EDGE_API_KEY` environment variable. If omitted, operates in standalone mode: runs inference and logs locally without sending HTTP events. |
| **3. Zone Intrusion Pipeline** | Subprocess managed by `process_manager.py` or standalone script | Via `POST /processes/zone_pipeline/start` or standalone `python edge/zone_intrusion/tracking/zone_intrusion_pipeline.py` | Uses `requests.post()` in `post_event()` | Configurable via `--api-url` | When spawned by `process_manager.py`, passes edge key via process environment (`AEGIS_EDGE_API_KEY`), never on command line. When standalone, accepts `--api-key` or `AEGIS_EDGE_API_KEY`. Standalone works without key (logs locally). |
| **4. Dashboard Simulate Buttons** | Browser client (`dashboard/app.js`) | User clicks "+ PPE Violation" or "+ Zone Intrusion" in Alert Feed sidebar | `fetch('/events', { method: 'POST', ... })` | Same-origin `/events` | Authenticated via browser session cookie (Admin-only). Operator sessions are rejected with 403. |
| **5. `federated_demo`** | 3 Subprocesses (`flower_server`, `site_1` client, `site_2` client) spawned by `process_manager.py` | Via `POST /processes/federated_demo/start` | gRPC on `127.0.0.1:8089` (Flower FedAvg) | Port 8089 (gRPC) | No REST endpoints are called. No API keys are passed to federated subprocesses. |

---

## 3. Streaming and Capture Route Specifications

1. `POST /stream/start`:
   - Uses `StreamStartRequest` model: `source` can be a webcam index (`"0"`, `"1"`), a demo video path (`"demo/videos/..."`), or an RTSP/HTTP URL.
   - Built-in sources (integers and verified `demo/videos/` files) are permitted for Operators and Admins.
   - Custom network URLs (e.g. `rtsp://`, `http://`, `https://`) are strictly Admin-only.
2. `GET /capture-frame`:
   - Used by Draw Zone tab to capture a single still image from a source to mark zone polygons.
   - Takes `source` query parameter. Calls `validate_media_source(source)` and captures frame.
   - Admin-only because it causes the server to connect to arbitrary media sources.
3. `GET /stream/latest-frame`:
   - Used as polling fallback for browsers that cannot render MJPEG streams.
   - Returns latest frame buffer from running stream. Permitted for Operator and Admin.

