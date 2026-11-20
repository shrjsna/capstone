"""
cloud/backend/permissions.py
============================
Centralized Role-Based Access Control (RBAC) permission registry and enforcement engine.

Defines the single authoritative permission table mapping (method, path_template)
to required roles (admin, operator, edge, or open).
Enforces default-deny: any route without an explicit table entry is refused for all callers.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from fastapi import HTTPException, Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Match, Mount, Route

from cloud.backend.audit import record_audit
from cloud.backend.auth import (
    AuthenticatedIdentity,
    get_client_ip,
    get_current_identity,
)
from cloud.backend.config import get_settings
from cloud.backend.database import SessionLocal, get_db

def get_session_for_request(app) -> SessionLocal:
    """Retrieve database session, honoring dependency overrides in testing."""
    if hasattr(app, "dependency_overrides") and get_db in app.dependency_overrides:
        override = app.dependency_overrides[get_db]
        res = override()
        if hasattr(res, "__next__"):
            return next(res)
        return res
    return SessionLocal()


logger = logging.getLogger("aegis.permissions")

# Roles definition
ROLE_ADMIN = "admin"
ROLE_OPERATOR = "operator"
ROLE_EDGE = "edge"

ALL_ROLES = {ROLE_ADMIN, ROLE_OPERATOR, ROLE_EDGE}
HUMAN_ROLES = {ROLE_ADMIN, ROLE_OPERATOR}


@dataclass
class Perm:
    """Permission entry for a registered route."""
    allowed_roles: Set[str]  # Empty set indicates public/unauthenticated access
    description: str
    custom_checker: Optional[Callable[[Request, Optional[AuthenticatedIdentity], Dict[str, Any]], None]] = None

    @property
    def is_open(self) -> bool:
        return len(self.allowed_roles) == 0


# ---------------------------------------------------------------------------
# Custom Body / Parameter Dependent Checkers
# ---------------------------------------------------------------------------

def is_builtin_media_source(source: Any) -> bool:
    """
    Check if a stream source qualifies as a built-in source (webcam index or demo video).
    Custom RTSP/HTTP URLs require Administrator privileges.
    """
    s = str(source).strip()
    if s.isdigit():
        return True
    # Strip leading slashes/dots and check demo/videos prefix
    clean = s.replace("\\", "/").lstrip("./")
    if clean.startswith("demo/videos/"):
        return True
    return False


async def check_stream_start(request: Request, identity: Optional[AuthenticatedIdentity], path_params: Dict[str, Any]) -> None:
    """
    Rule for POST /stream/start:
    - Admin: allowed for all valid sources (built-in and custom network URLs).
    - Operator: allowed ONLY for built-in sources (webcam index, demo video).
    - Edge / Anon: rejected.
    """
    if not identity or identity.role not in (ROLE_ADMIN, ROLE_OPERATOR):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Stream control requires Operator or Admin role."},
        )

    if identity.role == ROLE_ADMIN:
        return

    # Operator validation: must inspect request body for source type
    try:
        body_bytes = await request.body()
        if body_bytes:
            body = json.loads(body_bytes.decode("utf-8"))
            source = body.get("source", "")
            if not is_builtin_media_source(source):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "code": "FORBIDDEN",
                        "message": "Operators are permitted to stream built-in sources only. "
                                   "Streaming custom network URLs requires Administrator privileges."
                    },
                )
    except json.JSONDecodeError:
        pass  # Malformed JSON will be handled by FastAPI's validation layer


ALLOWED_PROCESS_NAMES = {"federated_demo", "zone_pipeline"}


def check_process_route(request: Request, identity: Optional[AuthenticatedIdentity], path_params: Dict[str, Any]) -> None:
    """
    Verify process name is in the fixed whitelist before dispatching.
    Admin-only.
    """
    proc_name = path_params.get("name")
    if proc_name and proc_name not in ALLOWED_PROCESS_NAMES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown process '{proc_name}'. Permitted processes: {sorted(list(ALLOWED_PROCESS_NAMES))}",
        )


# ---------------------------------------------------------------------------
# Authoritative Permission Table
# ---------------------------------------------------------------------------

PERMISSION_TABLE: Dict[Tuple[str, str], Perm] = {
    # System liveness probe
    ("GET", "/health"): Perm(
        allowed_roles=set(),
        description="Public health check / liveness probe.",
    ),

    # Live model weights
    ("GET", "/model-weights"): Perm(
        allowed_roles={ROLE_ADMIN, ROLE_OPERATOR},
        description="Retrieve live Contextual Bandit decision weights and mathematical norms.",
    ),

    # Login redirect
    ("GET", "/login"): Perm(
        allowed_roles=set(),
        description="Redirect to dashboard login page.",
    ),

    # Static UI mount (GET / HEAD)
    ("GET", "/"): Perm(
        allowed_roles=set(),
        description="Dashboard static assets and login screen.",
    ),
    ("HEAD", "/"): Perm(
        allowed_roles=set(),
        description="Static asset header check.",
    ),

    # OpenAPI / Swagger Documentation (Admin-only to prevent reconnaissance)
    ("GET", "/openapi.json"): Perm(
        allowed_roles={ROLE_ADMIN},
        description="OpenAPI 3.0 specification.",
    ),
    ("GET", "/docs"): Perm(
        allowed_roles={ROLE_ADMIN},
        description="Swagger UI API documentation.",
    ),
    ("GET", "/docs/oauth2-redirect"): Perm(
        allowed_roles={ROLE_ADMIN},
        description="Swagger OAuth2 redirect helper.",
    ),
    ("GET", "/redoc"): Perm(
        allowed_roles={ROLE_ADMIN},
        description="ReDoc API documentation.",
    ),

    # Authentication Routes
    ("POST", "/auth/login"): Perm(
        allowed_roles=set(),
        description="User authentication and session cookie issuance.",
    ),
    ("POST", "/auth/logout"): Perm(
        allowed_roles={ROLE_ADMIN, ROLE_OPERATOR},
        description="User session revocation and cookie clearing.",
    ),
    ("GET", "/auth/me"): Perm(
        allowed_roles={ROLE_ADMIN, ROLE_OPERATOR, ROLE_EDGE},
        description="Current authenticated identity and active CSRF token.",
    ),
    ("POST", "/auth/change-password"): Perm(
        allowed_roles={ROLE_ADMIN, ROLE_OPERATOR},
        description="User password update.",
    ),

    # Detection Event Ingestion
    ("POST", "/events"): Perm(
        allowed_roles={ROLE_ADMIN, ROLE_EDGE},
        description="Event submission (Edge producers and Admin simulations). Operator refused.",
    ),

    # Operator Feedback
    ("POST", "/feedback"): Perm(
        allowed_roles={ROLE_ADMIN, ROLE_OPERATOR},
        description="Human feedback for bandit decision updates.",
    ),

    # Safety Alerts
    ("GET", "/alerts"): Perm(
        allowed_roles={ROLE_ADMIN, ROLE_OPERATOR},
        description="Paginated alert feed query.",
    ),
    ("GET", "/alerts/{event_id}"): Perm(
        allowed_roles={ROLE_ADMIN, ROLE_OPERATOR},
        description="Single alert detail view.",
    ),

    # Policy and Threshold Queries
    ("GET", "/policy-history"): Perm(
        allowed_roles={ROLE_ADMIN, ROLE_OPERATOR},
        description="Historical policy progression records.",
    ),
    ("POST", "/policy/checkpoint"): Perm(
        allowed_roles={ROLE_ADMIN, ROLE_OPERATOR},
        description="Checkpoint current learned weights into a formal versioned policy release.",
    ),
    ("GET", "/thresholds"): Perm(
        allowed_roles={ROLE_ADMIN, ROLE_OPERATOR},
        description="Current per-zone sensitivity thresholds.",
    ),

    # Live Stream Controls
    ("POST", "/stream/start"): Perm(
        allowed_roles={ROLE_ADMIN, ROLE_OPERATOR},
        description="Start live stream worker. Built-in sources for Operator; custom URLs for Admin.",
        custom_checker=check_stream_start,
    ),
    ("POST", "/stream/stop"): Perm(
        allowed_roles={ROLE_ADMIN, ROLE_OPERATOR},
        description="Stop live stream worker.",
    ),
    ("GET", "/stream/status"): Perm(
        allowed_roles={ROLE_ADMIN, ROLE_OPERATOR},
        description="Current stream liveness state.",
    ),
    ("GET", "/stream/mjpeg"): Perm(
        allowed_roles={ROLE_ADMIN, ROLE_OPERATOR},
        description="Multipart MJPEG video stream.",
    ),
    ("GET", "/stream/latest-frame"): Perm(
        allowed_roles={ROLE_ADMIN, ROLE_OPERATOR},
        description="Single JPEG frame buffer snapshot.",
    ),

    # Zone Capture and Configuration
    ("GET", "/capture-frame"): Perm(
        allowed_roles={ROLE_ADMIN},
        description="Server-side frame capture for zone drawing. Admin-only.",
    ),
    ("GET", "/zones"): Perm(
        allowed_roles={ROLE_ADMIN, ROLE_OPERATOR},
        description="Read-only query of configured safety zones.",
    ),
    ("POST", "/zones"): Perm(
        allowed_roles={ROLE_ADMIN},
        description="Save/update safety zone polygon. Admin-only.",
    ),
    ("DELETE", "/zones/{camera_id}/{zone_id}"): Perm(
        allowed_roles={ROLE_ADMIN},
        description="Delete safety zone polygon. Admin-only.",
    ),

    # Background Process Management (Federated Learning & Zone Pipeline)
    ("GET", "/processes"): Perm(
        allowed_roles={ROLE_ADMIN},
        description="Query managed background processes. Admin-only.",
    ),
    ("POST", "/processes/{name}/start"): Perm(
        allowed_roles={ROLE_ADMIN},
        description="Launch managed process (federated_demo or zone_pipeline). Admin-only.",
        custom_checker=check_process_route,
    ),
    ("POST", "/processes/{name}/stop"): Perm(
        allowed_roles={ROLE_ADMIN},
        description="Terminate managed process. Admin-only.",
        custom_checker=check_process_route,
    ),
    ("GET", "/processes/{name}/logs"): Perm(
        allowed_roles={ROLE_ADMIN},
        description="Retrieve subprocess ring-buffer logs. Admin-only.",
        custom_checker=check_process_route,
    ),

    # Data Retention & GDPR Incident Cleanup
    ("POST", "/retention/cleanup"): Perm(
        allowed_roles={ROLE_ADMIN},
        description="Purge aged incident clips and historical records. Admin-only.",
    ),

    # User Administration (Admin-only)
    ("GET", "/admin/users"): Perm(
        allowed_roles={ROLE_ADMIN},
        description="List registered user accounts.",
    ),
    ("POST", "/admin/users"): Perm(
        allowed_roles={ROLE_ADMIN},
        description="Create operator or administrator account.",
    ),
    ("PATCH", "/admin/users/{id}"): Perm(
        allowed_roles={ROLE_ADMIN},
        description="Update user account role or active state.",
    ),
    ("POST", "/admin/users/{id}/reset-password"): Perm(
        allowed_roles={ROLE_ADMIN},
        description="Reset user password and require change on next login.",
    ),

    # Edge Key Administration (Admin-only)
    ("GET", "/admin/edge-keys"): Perm(
        allowed_roles={ROLE_ADMIN},
        description="List registered edge keys (never reveals secrets).",
    ),
    ("POST", "/admin/edge-keys"): Perm(
        allowed_roles={ROLE_ADMIN},
        description="Issue new edge API key.",
    ),
    ("POST", "/admin/edge-keys/{prefix}/revoke"): Perm(
        allowed_roles={ROLE_ADMIN},
        description="Revoke an edge API key immediately.",
    ),

    # Audit Trail (Admin-only)
    ("GET", "/admin/audit-log"): Perm(
        allowed_roles={ROLE_ADMIN},
        description="Query append-only audit trail.",
    ),
}


# ---------------------------------------------------------------------------
# Route Matching and RBAC Enforcement
# ---------------------------------------------------------------------------

def match_route_template(app, method: str, path: str) -> Tuple[Optional[str], Dict[str, Any], bool]:
    """
    Match incoming HTTP request against registered Starlette routes.
    Returns (path_template, path_params, is_static_mount).
    """
    scope = {"type": "http", "method": method, "path": path}
    mount_route = None

    for route in app.routes:
        if hasattr(route, "original_router"):
            for sub_route in route.original_router.routes:
                match, child_scope = sub_route.matches(scope)
                if match == Match.FULL:
                    path_params = child_scope.get("path_params", {})
                    return getattr(sub_route, "path", None), path_params, False
        elif isinstance(route, Route):
            match, child_scope = route.matches(scope)
            if match == Match.FULL:
                path_params = child_scope.get("path_params", {})
                return getattr(route, "path", None), path_params, False
        elif isinstance(route, Mount):
            mount_route = route

    # Verify static file mount only matches actual existing files or root index.html
    if mount_route and method in ("GET", "HEAD"):
        static_dir = getattr(mount_route.app, "directory", None)
        if static_dir:
            from pathlib import Path
            clean_path = path.lstrip("/")
            if not clean_path or clean_path == "index.html":
                return "/", {}, True
            try:
                static_root = Path(static_dir).resolve()
                target_file = (static_root / clean_path).resolve()
                html_file = (static_root / f"{clean_path}.html").resolve()
                if (target_file.is_file() and target_file.is_relative_to(static_root)) or \
                   (html_file.is_file() and html_file.is_relative_to(static_root)):
                    return "/", {}, True
            except Exception:
                pass

    return None, {}, False


class RBACMiddleware(BaseHTTPMiddleware):
    """
    Global RBAC enforcement middleware:
    - Resolves credential (cookie or X-API-Key).
    - Checks route against PERMISSION_TABLE with DEFAULT DENY.
    - Enforces must_change_password restriction.
    - Audits all refusals (401 and 403).
    """

    async def dispatch(self, request: Request, call_next):
        method = request.method
        path = request.url.path

        # Allow CORS preflight requests
        if method == "OPTIONS":
            return await call_next(request)

        # 1. Match route template
        template, path_params, is_mount = match_route_template(request.app, method, path)

        if not template:
            # Unmatched / unmapped route: default deny
            db = get_session_for_request(request.app)
            try:
                client_ip = get_client_ip(request)
                record_audit(
                    db=db,
                    action="access.denied.403",
                    outcome="denied",
                    actor="unknown",
                    target=f"{method} {path}",
                    client_addr=client_ip,
                    detail=f"Unmapped route '{path}' refused under default-deny policy.",
                )
            finally:
                db.close()

            return Response(
                content=json.dumps({"code": "UNMAPPED_ROUTE", "message": "Access denied by default."}),
                status_code=status.HTTP_403_FORBIDDEN,
                media_type="application/json",
            )

        # 2. Look up permission rule
        perm = PERMISSION_TABLE.get((method, template))
        if not perm:
            # Route exists in app but missing from permission table: default deny!
            db = get_session_for_request(request.app)
            try:
                client_ip = get_client_ip(request)
                record_audit(
                    db=db,
                    action="access.denied.403",
                    outcome="denied",
                    actor="unknown",
                    target=f"{method} {template}",
                    client_addr=client_ip,
                    detail=f"Route '{method} {template}' lacks PERMISSION_TABLE entry.",
                )
            finally:
                db.close()

            logger.error("[rbac] Default-deny triggered for unconfigured route: %s %s", method, template)
            return Response(
                content=json.dumps({"code": "ROUTE_NOT_CONFIGURED", "message": "Route has no configured permission."}),
                status_code=status.HTTP_403_FORBIDDEN,
                media_type="application/json",
            )

        # 3. Open / Public route check
        if perm.is_open:
            response = await call_next(request)
            if is_mount:
                response.headers["Cache-Control"] = "no-cache, must-revalidate"
            return response

        # 4. Resolve caller identity
        db = get_session_for_request(request.app)
        identity: Optional[AuthenticatedIdentity] = None
        client_ip = get_client_ip(request)

        try:
            cookie_val = request.cookies.get("aegis_session")
            header_val = request.headers.get("X-API-Key")

            # Check ambiguous credentials
            if cookie_val and header_val:
                record_audit(
                    db=db,
                    action="access.denied.403",
                    outcome="denied",
                    actor="unknown",
                    target=f"{method} {template}",
                    client_addr=client_ip,
                    detail="Ambiguous request presenting both session cookie and X-API-Key.",
                )
                return Response(
                    content=json.dumps({"code": "AMBIGUOUS_CREDENTIALS", "message": "Cannot present both session cookie and API key."}),
                    status_code=status.HTTP_403_FORBIDDEN,
                    media_type="application/json",
                )

            if header_val:
                from cloud.backend.auth import resolve_edge_key
                identity = resolve_edge_key(db, header_val.strip())
                if not identity:
                    record_audit(
                        db=db,
                        action="access.denied.401",
                        outcome="denied",
                        actor="unknown_edge",
                        target=f"{method} {template}",
                        client_addr=client_ip,
                        detail="Invalid or revoked edge key.",
                    )
                    return Response(
                        content=json.dumps({"code": "AUTH_REQUIRED", "message": "Invalid or revoked edge key."}),
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        media_type="application/json",
                    )
            elif cookie_val:
                from cloud.backend.auth import resolve_session_cookie
                user_agent = request.headers.get("User-Agent")
                identity = resolve_session_cookie(db, cookie_val, client_ip, user_agent)
                if not identity:
                    return Response(
                        content=json.dumps({"code": "SESSION_EXPIRED", "message": "Session expired or invalid. Please sign in again."}),
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        media_type="application/json",
                    )

                # Anti-CSRF check for mutating methods using cookie auth
                if method in ("POST", "PUT", "PATCH", "DELETE"):
                    csrf_header = request.headers.get("X-CSRF-Token")
                    if not csrf_header or not identity.session or csrf_header != identity.session.csrf_token:
                        record_audit(
                            db=db,
                            action="access.denied.403",
                            outcome="denied",
                            actor=identity.actor,
                            role=identity.role,
                            target=f"{method} {template}",
                            client_addr=client_ip,
                            detail=f"CSRF token validation failed on {method} {template}.",
                        )
                        return Response(
                            content=json.dumps({"code": "CSRF_FAILED", "message": "Invalid or missing CSRF token."}),
                            status_code=status.HTTP_403_FORBIDDEN,
                            media_type="application/json",
                        )

            # Not authenticated
            if not identity:
                record_audit(
                    db=db,
                    action="access.denied.401",
                    outcome="denied",
                    actor="anonymous",
                    target=f"{method} {template}",
                    client_addr=client_ip,
                    detail=f"Authentication required for {method} {template}.",
                )
                return Response(
                    content=json.dumps({"code": "AUTH_REQUIRED", "message": "Authentication required."}),
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    media_type="application/json",
                )

            # 5. Check must_change_password restriction
            if identity.must_change_password:
                allowed_while_must_change = {
                    ("GET", "/auth/me"),
                    ("POST", "/auth/logout"),
                    ("POST", "/auth/change-password"),
                }
                if (method, template) not in allowed_while_must_change:
                    record_audit(
                        db=db,
                        action="access.denied.403",
                        outcome="denied",
                        actor=identity.actor,
                        role=identity.role,
                        target=f"{method} {template}",
                        client_addr=client_ip,
                        detail="Access refused: user must change password.",
                    )
                    return Response(
                        content=json.dumps({
                            "code": "PASSWORD_CHANGE_REQUIRED",
                            "message": "Password change required before accessing this resource."
                        }),
                        status_code=status.HTTP_403_FORBIDDEN,
                        media_type="application/json",
                    )

            # 6. Check Role Authorization
            if identity.role not in perm.allowed_roles:
                record_audit(
                    db=db,
                    action="access.denied.403",
                    outcome="denied",
                    actor=identity.actor,
                    role=identity.role,
                    target=f"{method} {template}",
                    client_addr=client_ip,
                    detail=f"Role '{identity.role}' forbidden from accessing {method} {template}.",
                )
                return Response(
                    content=json.dumps({
                        "code": "FORBIDDEN",
                        "message": f"Account role '{identity.role}' does not have permission to access this resource."
                    }),
                    status_code=status.HTTP_403_FORBIDDEN,
                    media_type="application/json",
                )

            # 7. Execute custom checkers (e.g. stream_start source checks)
            if perm.custom_checker:
                try:
                    res = perm.custom_checker(request, identity, path_params)
                    if hasattr(res, "__await__"):
                        await res
                except HTTPException as http_exc:
                    record_audit(
                        db=db,
                        action="access.denied.403",
                        outcome="denied",
                        actor=identity.actor,
                        role=identity.role,
                        target=f"{method} {template}",
                        client_addr=client_ip,
                        detail=str(http_exc.detail),
                    )
                    return Response(
                        content=json.dumps(http_exc.detail if isinstance(http_exc.detail, dict) else {"message": str(http_exc.detail)}),
                        status_code=http_exc.status_code,
                        media_type="application/json",
                    )

        finally:
            db.close()

        # Attach identity to request state for downstream handler consumption
        request.state.identity = identity
        return await call_next(request)


# ---------------------------------------------------------------------------
# Documentation & Verification Helper
# ---------------------------------------------------------------------------

def generate_permissions_markdown() -> str:
    """Generate Markdown representation of the live permission table."""
    lines = [
        "| Method | Path Template | Anon | Operator | Admin | Edge | Description |",
        "|---|---|:---:|:---:|:---:|:---:|---|",
    ]
    for (m, path), p in sorted(PERMISSION_TABLE.items()):
        anon_mark = "yes" if p.is_open else "-"
        op_mark = "yes" if (p.is_open or ROLE_OPERATOR in p.allowed_roles) else "-"
        admin_mark = "yes" if (p.is_open or ROLE_ADMIN in p.allowed_roles) else "-"
        edge_mark = "yes" if (p.is_open or ROLE_EDGE in p.allowed_roles) else "-"
        lines.append(f"| `{m}` | `{path}` | {anon_mark} | {op_mark} | {admin_mark} | {edge_mark} | {p.description} |")
    return "\n".join(lines)
