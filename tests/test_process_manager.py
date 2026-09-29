"""
tests/test_process_manager.py
=============================
Tests for process manager module, API endpoints, source validation,
crash detection state transitions, and static dashboard file serving.
All subprocesses are mocked to ensure deterministic, hardware-free execution in CI.
"""

import collections
import subprocess
import time
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from cloud.backend.main import app
from cloud.backend.process_manager import (
    ProcessManager,
    ManagedProcessState,
    get_process_manager,
    validate_source,
)


@pytest.fixture(autouse=True)
def reset_process_manager():
    """Ensure process manager state is clean before and after each test."""
    pm = get_process_manager()
    pm.stop_all()
    # Reset states
    for state in pm.processes.values():
        with state.lock:
            state.status = "stopped"
            state.pids.clear()
            state.logs.clear()
            state.subprocesses.clear()
            state.threads.clear()
            state.was_stopped_by_user = False
            state.started_at = None
    yield pm
    pm.stop_all()


client = TestClient(app)


# =========================================================================
# 1. Source Validation Security Tests
# =========================================================================

def test_validate_source_integer():
    assert validate_source("0") == "0"
    assert validate_source("1") == "1"


def test_validate_source_valid_urls():
    assert validate_source("rtsp://192.168.1.100:554/live") == "rtsp://192.168.1.100:554/live"
    assert validate_source("http://192.168.1.100:8080/stream") == "http://192.168.1.100:8080/stream"
    assert validate_source("https://example.com/video.mp4") == "https://example.com/video.mp4"


def test_validate_source_demo_video():
    valid_path = "demo/videos/zone_intrusion_demo.mp4"
    result = validate_source(valid_path)
    assert "zone_intrusion_demo.mp4" in result


def test_validate_source_reject_empty():
    with pytest.raises(ValueError, match="Source cannot be empty"):
        validate_source("")


def test_validate_source_reject_traversal():
    with pytest.raises(ValueError, match="traversal or shell characters not allowed"):
        validate_source("demo/videos/../../windows/system32/cmd.exe")


def test_validate_source_reject_metacharacters():
    with pytest.raises(ValueError, match="traversal or shell characters not allowed"):
        validate_source("demo/videos/test.mp4; rm -rf /")
    with pytest.raises(ValueError, match="traversal or shell characters not allowed"):
        validate_source("demo/videos/test.mp4 | cat")
    with pytest.raises(ValueError, match="traversal or shell characters not allowed"):
        validate_source("$(whoami)")


def test_validate_source_reject_url_with_metacharacters():
    with pytest.raises(ValueError, match="URL contains invalid or unsafe characters"):
        validate_source("rtsp://example.com/stream; rm -rf")


def test_validate_source_reject_outside_directory():
    with pytest.raises(ValueError, match="must reside under demo/videos/"):
        validate_source("cloud/backend/main.py")


def test_validate_source_reject_nonexistent_file():
    with pytest.raises(ValueError, match="does not exist"):
        validate_source("demo/videos/non_existent_file_xyz123.mp4")


# =========================================================================
# 2. Process Manager API Endpoints Tests
# =========================================================================

def test_get_processes_list():
    resp = client.get("/processes")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    names = [p["name"] for p in data]
    assert "federated_demo" in names
    assert "zone_pipeline" in names


def test_get_processes_unknown_name_returns_404():
    resp = client.post("/processes/non_existent/start")
    assert resp.status_code == 404
    resp = client.post("/processes/non_existent/stop")
    assert resp.status_code == 404
    resp = client.get("/processes/non_existent/logs")
    assert resp.status_code == 404


def test_start_zone_pipeline_endpoint():
    with patch("cloud.backend.process_manager.ProcessManager._run_zone_pipeline"):
        resp = client.post(
            "/processes/zone_pipeline/start",
            json={"source": "demo/videos/zone_intrusion_demo.mp4"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "zone_pipeline"
        assert data["status"] == "running"

        # Verify duplicate start returns current status without second spawn
        resp_dup = client.post(
            "/processes/zone_pipeline/start",
            json={"source": "demo/videos/zone_intrusion_demo.mp4"},
        )
        assert resp_dup.status_code == 200
        assert resp_dup.json()["status"] == "running"


def test_start_federated_demo_endpoint():
    with patch("cloud.backend.process_manager.ProcessManager._run_federated_demo"):
        resp = client.post("/processes/federated_demo/start")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "federated_demo"
        assert data["status"] == "running"

        # Duplicate start
        resp_dup = client.post("/processes/federated_demo/start")
        assert resp_dup.status_code == 200
        assert resp_dup.json()["status"] == "running"


def test_start_zone_pipeline_invalid_source_returns_400():
    resp = client.post(
        "/processes/zone_pipeline/start",
        json={"source": "invalid;metachar"},
    )
    assert resp.status_code == 400


def test_stop_unstarted_process_returns_stopped():
    resp = client.post("/processes/zone_pipeline/stop")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "zone_pipeline"
    assert data["status"] == "stopped"


def test_stop_running_process():
    pm = get_process_manager()
    proc = pm.get_process_state("zone_pipeline")

    mock_proc = MagicMock()
    mock_proc.pid = 99992
    mock_proc.poll.return_value = None
    mock_proc.wait.return_value = 0

    with proc.lock:
        proc.status = "running"
        proc.subprocesses = [mock_proc]

    resp = client.post("/processes/zone_pipeline/stop")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "stopped"
    assert mock_proc.terminate.called



def test_get_process_logs():
    pm = get_process_manager()
    proc = pm.get_process_state("federated_demo")
    proc.append_log("Log line 1")
    proc.append_log("Log line 2")

    resp = client.get("/processes/federated_demo/logs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "federated_demo"
    assert "Log line 1" in data["logs"]
    assert "Log line 2" in data["logs"]


# =========================================================================
# 3. Crash-Detection State Transition Test
# =========================================================================

def test_crash_detection_state_transition():
    pm = get_process_manager()
    proc = pm.get_process_state("zone_pipeline")

    mock_proc = MagicMock()
    mock_proc.pid = 88881
    mock_proc.returncode = 1
    mock_proc.stdout = MagicMock()
    mock_proc.stdout.readline.side_effect = [
        "Starting zone pipeline\n",
        "Error: Video stream corrupted\n",
        "",
    ]
    mock_proc.wait.return_value = 1

    with proc.lock:
        proc.was_stopped_by_user = False
        proc.status = "running"
        proc.subprocesses = [mock_proc]

    # Directly run worker logic (simulating unexpected exit)
    with patch.object(pm, "_spawn_subprocess", return_value=mock_proc):
        pm._run_zone_pipeline(proc, "demo/videos/zone_intrusion_demo.mp4")

    # Verify status changed to crashed, not stopped
    assert proc.status == "crashed"
    assert any("Error: Video stream corrupted" in line for line in proc.logs)
    assert any("crashed" in line or "exited" in line for line in proc.logs)


# =========================================================================
# 4. Single-Process Dashboard Static Serving Tests
# =========================================================================

def test_static_dashboard_html_served_on_root():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "AEGIS" in resp.text
    assert "Control Panel" in resp.text


def test_static_styles_css_served():
    resp = client.get("/styles.css")
    assert resp.status_code == 200
    assert "control-layout" in resp.text


def test_static_app_js_served():
    resp = client.get("/app.js")
    assert resp.status_code == 200
    assert "buildDefaultApiUrl" in resp.text
    assert "loadProcessStatus" in resp.text


def test_api_routes_not_shadowed_by_static_mount():
    # Confirm health check and existing endpoints still return JSON
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}

    resp = client.get("/alerts")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

    resp = client.get("/thresholds")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)
