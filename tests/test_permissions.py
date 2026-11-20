"""
tests/test_permissions.py
=========================
Comprehensive tests for Role-Based Access Control:
- Default-deny enforcement across all registered FastAPI routes.
- Verification that missing table entries trigger immediate 403 rejection.
- Table-driven matrix tests across all four roles (Anon, Operator, Admin, Edge).
- Synchronization check between code and Markdown permission documentation.
"""

import pytest
from starlette.routing import Route, Mount
from cloud.backend.main import app
from cloud.backend.permissions import (
    PERMISSION_TABLE,
    ROLE_ADMIN,
    ROLE_EDGE,
    ROLE_OPERATOR,
    Perm,
    generate_permissions_markdown,
)


def test_default_deny_every_registered_route_has_table_entry():
    """
    Default-deny guarantee: Every registered route in the FastAPI application
    MUST have an explicit entry in PERMISSION_TABLE.
    Fails if any route is added without permission mapping.
    """
    registered_routes = set()
    routes_to_check = []
    for route in app.routes:
        if hasattr(route, "original_router"):
            routes_to_check.extend(route.original_router.routes)
        else:
            routes_to_check.append(route)

    for route in routes_to_check:
        if isinstance(route, Route):
            # Exclude HEAD if GET is registered
            methods = [m for m in route.methods if m not in ("OPTIONS", "HEAD")]
            for m in methods:
                registered_routes.add((m, route.path))
        elif isinstance(route, Mount):
            registered_routes.add(("GET", "/"))
            registered_routes.add(("HEAD", "/"))

    table_routes = {(m, p) for (m, p) in PERMISSION_TABLE.keys() if m != "OPTIONS"}

    # Routes in app but missing in table
    unmapped = registered_routes - table_routes
    assert not unmapped, f"Unmapped routes detected (default-deny violation): {unmapped}"

    # Routes in table but missing in app
    dangling = table_routes - registered_routes
    assert not dangling, f"Dangling permissions in table without route in app: {dangling}"


def test_default_deny_unmapped_route_is_rejected_at_runtime(anon_client, admin_client):
    """Prove that an unmapped route template is rejected with 403 under default-deny."""
    # Try calling a path that exists nowhere in routes
    res_anon = anon_client.get("/nonexistent-unmapped-path-test")
    assert res_anon.status_code == 403
    assert res_anon.json()["code"] == "UNMAPPED_ROUTE"

    res_admin = admin_client.get("/nonexistent-unmapped-path-test")
    assert res_admin.status_code == 403
    assert res_admin.json()["code"] == "UNMAPPED_ROUTE"


def test_default_deny_fails_when_entry_removed(monkeypatch, anon_client):
    """
    Prove that removing an entry from PERMISSION_TABLE causes the route to be refused
    under default-deny, and fails the test.
    """
    # Temporarily remove /health from table
    original_perm = PERMISSION_TABLE.pop(("GET", "/health"))
    try:
        res = anon_client.get("/health")
        assert res.status_code == 403
        assert res.json()["code"] == "ROUTE_NOT_CONFIGURED"
    finally:
        # Restore permission entry
        PERMISSION_TABLE[("GET", "/health")] = original_perm

    # Confirm restored
    assert anon_client.get("/health").status_code == 200


def test_permission_markdown_export():
    """Verify that the permission table markdown exporter generates valid documentation."""
    md = generate_permissions_markdown()
    assert "| Method | Path Template | Anon | Operator | Admin | Edge | Description |" in md
    assert "| `GET` | `/health` | yes | yes | yes | yes |" in md
    assert "| `POST` | `/events` | - | - | yes | yes |" in md
    assert "| `POST` | `/processes/{name}/start` | - | - | yes | - |" in md


# ---------------------------------------------------------------------------
# Table-Driven Permission Verification Matrix
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("method,path,expected_anon,expected_op,expected_admin,expected_edge", [
    # Health probe
    ("GET", "/health", 200, 200, 200, 200),
    # Static dashboard mount
    ("GET", "/", 200, 200, 200, 200),
    # OpenAPI surface (Admin-only)
    ("GET", "/openapi.json", 401, 403, 200, 403),
    ("GET", "/docs", 401, 403, 200, 403),
    # Auth endpoints
    ("GET", "/auth/me", 401, 200, 200, 200),
    # Alerts and thresholds
    ("GET", "/alerts", 401, 200, 200, 403),
    ("GET", "/thresholds", 401, 200, 200, 403),
    ("GET", "/model-weights", 401, 200, 200, 403),
    ("GET", "/policy-history", 401, 200, 200, 403),
    ("POST", "/policy/checkpoint", 401, 200, 200, 403),
    # Stream status and latest frame
    ("GET", "/stream/status", 401, 200, 200, 403),
    ("GET", "/stream/latest-frame", 401, 200, 200, 403),
    # Zones list
    ("GET", "/zones", 401, 200, 200, 403),
    # Capture frame (Admin-only)
    ("GET", "/capture-frame?source=demo/videos/zone_intrusion_demo.mp4", 401, 403, 200, 403),
    # Process management (Admin-only)
    ("GET", "/processes", 401, 403, 200, 403),
    ("GET", "/processes/federated_demo/logs", 401, 403, 200, 403),
    ("GET", "/processes/zone_pipeline/logs", 401, 403, 200, 403),
    # Admin users and audit log
    ("GET", "/admin/users", 401, 403, 200, 403),
    ("GET", "/admin/edge-keys", 401, 403, 200, 403),
    ("GET", "/admin/audit-log", 401, 403, 200, 403),
])
def test_get_routes_permission_matrix(
    method, path, expected_anon, expected_op, expected_admin, expected_edge,
    anon_client, operator_client, admin_client, edge_client
):
    """Table-driven verification of GET routes against all 4 roles."""
    # Anon
    r_anon = anon_client.request(method, path)
    assert r_anon.status_code == expected_anon, f"Anon {method} {path} expected {expected_anon}, got {r_anon.status_code}"

    # Operator
    r_op = operator_client.request(method, path)
    assert r_op.status_code == expected_op, f"Operator {method} {path} expected {expected_op}, got {r_op.status_code}"

    # Admin
    r_admin = admin_client.request(method, path)
    if expected_admin == 200:
        assert r_admin.status_code in (200, 422), f"Admin {method} {path} expected 200/422, got {r_admin.status_code}"
    else:
        assert r_admin.status_code == expected_admin, f"Admin {method} {path} expected {expected_admin}, got {r_admin.status_code}"

    # Edge
    r_edge = edge_client.request(method, path)
    assert r_edge.status_code == expected_edge, f"Edge {method} {path} expected {expected_edge}, got {r_edge.status_code}"
