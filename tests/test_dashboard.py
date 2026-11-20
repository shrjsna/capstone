"""
tests/test_dashboard.py
Smoke test verifying dashboard HTML, CSS, and JS file existence and essential DOM structures.
"""

import os
from starlette.testclient import TestClient
from cloud.backend.main import app


def test_dashboard_files_exist():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dashboard_dir = os.path.join(base_dir, "dashboard")

    html_path = os.path.join(dashboard_dir, "index.html")
    login_path = os.path.join(dashboard_dir, "login.html")
    css_path = os.path.join(dashboard_dir, "styles.css")
    js_path = os.path.join(dashboard_dir, "app.js")

    assert os.path.isfile(html_path), "index.html must exist"
    assert os.path.isfile(login_path), "login.html must exist"
    assert os.path.isfile(css_path), "styles.css must exist"
    assert os.path.isfile(js_path), "app.js must exist"


def test_dashboard_html_contains_core_elements():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html_path = os.path.join(base_dir, "dashboard", "index.html")

    with open(html_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Verify essential containers and script bindings exist
    assert 'id="alert-feed-container"' in content
    assert 'id="thresholds-container"' in content
    assert 'id="api-url-input"' in content
    assert 'src="app.js"' in content
    assert 'href="styles.css"' in content


def test_login_page_renders_and_is_accessible():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    login_path = os.path.join(base_dir, "dashboard", "login.html")

    with open(login_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert 'id="form-login-page"' in content
    assert 'id="login-username"' in content
    assert 'id="login-password"' in content
    assert 'id="form-change-pwd-page"' in content

    # Verify public static serving
    client = TestClient(app)
    r_html = client.get("/login.html")
    assert r_html.status_code == 200
    assert "AEGIS SAFETY" in r_html.text

    r_clean = client.get("/login", follow_redirects=True)
    assert r_clean.status_code == 200
    assert "AEGIS SAFETY" in r_clean.text
