"""
tests/test_dashboard.py
Smoke test verifying dashboard HTML, CSS, and JS file existence and essential DOM structures.
"""

import os


def test_dashboard_files_exist():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dashboard_dir = os.path.join(base_dir, "dashboard")

    html_path = os.path.join(dashboard_dir, "index.html")
    css_path = os.path.join(dashboard_dir, "styles.css")
    js_path = os.path.join(dashboard_dir, "app.js")

    assert os.path.isfile(html_path), "index.html must exist"
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
