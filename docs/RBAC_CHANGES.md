# AEGIS RBAC & High-Contrast Visual Theme — Change Log

## Overview
This document records all modifications performed during the implementation of Role-Based Access Control (RBAC), cookie session authentication, tamper-resistant audit logging, and the Black, White, and Orange UI theme.

---

## 1. Summary of Changes by Component

### 1.1 Backend Core & Security Modules
- `cloud/backend/config.py`:
  - Retired default shared secret `"aegis-secret-key-2026"`.
  - Added security tunables: `AEGIS_COOKIE_SECURE`, `AEGIS_SESSION_IDLE_MINUTES` (30), `AEGIS_SESSION_ABSOLUTE_HOURS` (12), `AEGIS_LOGIN_MAX_FAILURES` (5), `AEGIS_LOGIN_LOCKOUT_MINUTES` (15), `AEGIS_MIN_PASSWORD_LENGTH` (12), `AEGIS_TRUSTED_PROXIES`, `AEGIS_CORS_ORIGINS`.
  - Added strict CORS validation rejecting wildcard `*` with credentials.
- `cloud/backend/models.py`:
  - Added `UserModel`: id, username (unique, case-insensitive), password_hash (Argon2id), role (`admin` | `operator`), active, must_change_password, created_at, created_by, last_login_at.
  - Added `SessionModel`: id, token_hash (SHA-256), user_id, csrf_token, created_at, last_seen_at, expires_at, revoked, client_addr, user_agent.
  - Added `LoginAttemptModel`: id, username, client_addr, attempted_at, success.
  - Added `EdgeKeyModel`: id, key_prefix (unique), key_hash (SHA-256), label, created_at, last_used_at, active, revoked_at.
  - Added `AuditLogModel`: id, ts, actor, role, action, target, outcome, client_addr, detail.
- `cloud/backend/database.py`:
  - Enforced SQLite WAL mode (`PRAGMA journal_mode=WAL`) and foreign keys (`PRAGMA foreign_keys=ON`).
  - Implemented SQLite triggers `audit_log_no_update` and `audit_log_no_delete` ensuring append-only tamper resistance.
- `cloud/backend/audit.py` (New):
  - Created append-only audit logger function `record_audit(...)`.
  - Registered `audit_router` providing `GET /admin/audit-log` with pagination and action filtering.
- `cloud/backend/auth.py` (New):
  - Password hashing and verification using Argon2id (`argon2-cffi`).
  - Complexity validation (min 12 chars, upper, lower, number, symbol, no username match).
  - Timing attack mitigation via constant-time dummy verification.
  - Rate limiting / account throttling (5 failures within 15 minutes triggers HTTP 429).
  - Session cookie issuance (`HttpOnly`, `SameSite=Strict`, idle/absolute timeouts).
  - Double-submit CSRF token validation (`X-CSRF-Token`) on mutating browser requests.
  - Ephemeral in-memory process credential (`INTERNAL_STREAM_KEY`).
  - Auth routes: `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `POST /auth/change-password`.
- `cloud/backend/permissions.py` (New):
  - Defined role constants: `ROLE_ADMIN`, `ROLE_OPERATOR`, `ROLE_EDGE`.
  - Defined authoritative `PERMISSION_TABLE` mapping `(Method, Path Template)` to permitted roles and custom policy checkers.
  - Built `RBACMiddleware` enforcing strict DEFAULT DENY across all application endpoints.
  - Starlette route unwrapper supporting nested FastAPI `_IncludedRouter` route trees and exact static mount matching.
  - Markdown exporter `generate_permissions_markdown()` for documentation synchronization.
- `cloud/backend/users_admin.py` (New):
  - User administration endpoints: `GET /admin/users`, `POST /admin/users`, `PATCH /admin/users/{id}`, `POST /admin/users/{id}/reset-password`.
  - Atomic last-admin protection: database query counts active administrators before permitting role change or deactivation.
  - Edge key administration endpoints: `GET /admin/edge-keys`, `POST /admin/edge-keys`, `POST /admin/edge-keys/{prefix}/revoke`.
- `cloud/backend/manage.py` (New):
  - CLI management tool for offline bootstrap: `create-admin`, `create-user`, `list-users`, `disable-user`, `reset-password`, `create-edge-key`, `list-edge-keys`, `revoke-edge-key`.
- `cloud/backend/main.py`:
  - Connected `RBACMiddleware`, registered `auth_router`, `admin_users_router`, `audit_router`.
  - Replaced legacy per-route `verify_api_key` with central RBAC.
  - Injected `INTERNAL_STREAM_KEY` into stream worker.
  - Added automated security audit logging for stream starts/stops, zone modifications, process lifecycle events, and data pruning.
  - Made frame capture safe against OpenCV headless empty frame returns.
- `cloud/backend/stream_manager.py`:
  - Updated `start_stream` and `_stream_worker` to accept `api_key` argument and authenticate calls to `POST /events`.
- `cloud/backend/process_manager.py`:
  - Injected `INTERNAL_STREAM_KEY` into child process environment (`AEGIS_EDGE_API_KEY`) when launching zone pipeline.
- `run.py`:
  - Removed hardcoded key substring from startup console banner.
  - Added database check printing notice if no administrator account exists.

### 1.2 Edge Modules & Standalone Producers
- `edge/ppe_detection/infer.py`:
  - Retired default `"aegis-secret-key-2026"`.
  - Added `--api-key` CLI argument and `AEGIS_EDGE_API_KEY` environment variable fallback.
  - Standalone mode: when run without an API key, logs detections locally without raising HTTP exceptions or crashing.
- `edge/zone_intrusion/tracking/zone_intrusion_pipeline.py`:
  - Retired default `"aegis-secret-key-2026"`.
  - Added `--api-key` CLI argument and `AEGIS_EDGE_API_KEY` environment variable fallback.
  - Standalone mode: logs events locally and saves clips without crashing when key is absent.

### 1.3 Operations Dashboard (Frontend)
- `dashboard/index.html`:
  - Header: added user profile display (`#header-username`, `#header-role-badge`) and sign-out button (`#btn-header-logout`).
  - Retiring legacy API key input and settings modal.
  - Tab navigation: added "Users & Keys" (`#tab-btn-users`) and "Audit Log" (`#tab-btn-audit`) tabs (Admin only).
  - Role visibility: wrapped Simulate Edge Detection in `#panel-simulate-alerts` (Operator hidden).
  - Zone drawing: updated zone category pills to Black/White/Orange palette tokens.
  - Added view contents: `#tab-users` (User CRUD table & Edge Key management) and `#tab-audit` (Audit Log table with pagination).
  - Added modals: `#login-modal` (Authentication overlay), `#change-pwd-modal` (Mandatory password update), `#fed-confirm-modal` (Federated learning launch confirmation).
- `dashboard/app.js`:
  - Retired `apiKey`, `aegis-secret-key-2026`, and `localStorage` credential storage.
  - Built central `authFetch` with `credentials: 'same-origin'`, automatic CSRF header injection (`X-CSRF-Token`), 401 login modal triggers, and 403 password update enforcement.
  - Added `initAuth()` check querying `/auth/me` at startup.
  - Implemented `applyRoleVisibility(role)` toggling Control Panel, User management, Audit trail, custom RTSP inputs, and simulation buttons.
  - Added full interactive handlers for User CRUD, Password Resets, Edge Key issuance/revocation, and Audit Trail pagination.
  - Restyled zone canvas rendering: orange fill (`rgba(255, 106, 0, 0.25)`), orange boundary (`#FF6A00`), and white vertex handles (`#FFFFFF`).
- `dashboard/styles.css`:
  - Defined `:root` CSS variables for the authoritative palette: `--bg: #0A0A0A`, `--surface: #141414`, `--surface-2: #1E1E1E`, `--border: #2E2E2E`, `--text: #FFFFFF`, `--text-muted: #A3A3A3`, `--accent: #FF6A00`, `--accent-hover: #FF8533`, `--accent-press: #E65F00`, `--on-accent: #0A0A0A`.
  - Replaced 139 legacy color literals (cyan, amber, red, green, blue) with palette tokens.
  - Added table, badge, modal, and banner styling adhering to high-contrast guidelines.

### 1.4 Verification Tools & Test Suite
- `tools/check_theme.py` (New):
  - Automated linting utility scanning `dashboard/*.css`, `*.html`, `*.js` for unauthorized color literals.
- `tests/conftest.py`:
  - Added `AuthenticatedTestClient` supporting session cookie injection, CSRF header propagation, and Edge API keys.
  - Added fixtures: `admin_client`, `operator_client`, `edge_client`, `anon_client`, `admin_user`, `operator_user`.
  - Configured append-only triggers on in-memory SQLite test database.
- `tests/test_permissions.py` (New):
  - 22 tests verifying default-deny across every application route, runtime unmapped route rejection, Markdown table export, and table-driven GET route matrix.
- `tests/test_auth.py` (New):
  - 7 tests covering password complexity validation, Argon2id verification, account lockout throttling, session lifecycle, CSRF defense, and `must_change_password` mandatory enforcement.
- `tests/test_users_admin.py` (New):
  - 4 tests covering user listing RBAC, user account creation, atomic last-admin protection, and admin password resets.
- `tests/test_edge_keys.py` (New):
  - Edge key lifecycle test: issuing, listing without secrets, ingestion on `POST /events`, least-privilege rejection on operator/admin routes, and immediate revocation invalidation.
- `tests/test_audit_log.py` (New):
  - 2 tests verifying SQLite trigger abort on `UPDATE`/`DELETE` and `GET /admin/audit-log` access control.
- `tests/test_federated_access.py` (New):
  - Verified federated demo routes (`/processes/federated_demo/*`) are Admin-only (Operator 403, Anon 401).
- `tests/test_detection_pipeline_auth.py` (New):
  - 3 tests covering detection event ingestion authentication, stream worker internal key propagation, and operator feedback RBAC.
- `tests/test_theme.py` (New):
  - Automated test executing `check_theme.py` verifying 0 color violations.

