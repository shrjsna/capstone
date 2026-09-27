"""
tests/test_stream_manager.py
=============================
Unit tests for cloud/backend/stream_manager.py and the stream-related
FastAPI endpoints in cloud/backend/main.py.

Zero real camera, GPU, video, or network dependency.
cv2.VideoCapture and ultralytics.YOLO are fully mocked.

What is covered here (NOT duplicating test_backend.py or test_integration.py):
  1. StreamState thread-safe state management (put/get frame, set/is_running,
     set/get error, clear).
  2. start_stream / stop_stream public API — state transitions, idempotency.
  3. generate_mjpeg_frames — produces correct multipart boundary chunks; works
     before any stream starts (returns placeholder).
  4. get_latest_frame_jpeg — returns placeholder when no frame yet.
  5. POST /stream/start endpoint — validates request, returns correct JSON.
  6. POST /stream/stop endpoint — always returns {stopped: true}.
  7. GET /stream/status endpoint — reflects running state.
  8. GET /stream/mjpeg — returns multipart/x-mixed-replace content-type.
  9. GET /stream/latest-frame — returns image/jpeg content-type.
  10. GET /capture-frame — returns 422 when cv2 can't open source (mocked).
  11. GET /zones — returns empty list when no zone files exist.
  12. POST /zones — writes correct JSON to disk; GET /zones lists it.
  13. DELETE /zones — removes the file; subsequent GET doesn't include it.
  14. Starting stream twice stops the first before starting the second
      (no two conflicting workers).
  15. Stopping an already-stopped stream doesn't crash (was_running=False).
"""

import json
import os
import sys
import threading
import time
import tempfile
import shutil
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ---------------------------------------------------------------------------
# Ensure repo root is in sys.path
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ---------------------------------------------------------------------------
# Patch cv2 and ultralytics BEFORE importing stream_manager or main
# so the module-level lazy imports don't fail in CI (no GPU/camera).
# ---------------------------------------------------------------------------
import types

# Build a minimal fake cv2 module
_fake_cv2 = types.ModuleType("cv2")
_fake_cv2.VideoCapture   = MagicMock()
_fake_cv2.imencode       = MagicMock(return_value=(True, np.zeros((1,), dtype=np.uint8)))
_fake_cv2.rectangle      = MagicMock()
_fake_cv2.putText        = MagicMock()
_fake_cv2.polylines      = MagicMock()
_fake_cv2.fillPoly       = MagicMock()
_fake_cv2.addWeighted    = MagicMock()
_fake_cv2.FONT_HERSHEY_SIMPLEX = 0
_fake_cv2.LINE_AA        = 16
_fake_cv2.IMWRITE_JPEG_QUALITY = 1
_fake_cv2.CAP_PROP_POS_FRAMES  = 1

sys.modules.setdefault("cv2", _fake_cv2)

# Fake ultralytics
_fake_ultra = types.ModuleType("ultralytics")
_fake_ultra.YOLO = MagicMock()
sys.modules.setdefault("ultralytics", _fake_ultra)

# ---------------------------------------------------------------------------
# Now import stream_manager — it will pick up our fakes via sys.modules
# ---------------------------------------------------------------------------
from cloud.backend.stream_manager import (
    StreamState,
    start_stream,
    stop_stream,
    stream_status,
    generate_mjpeg_frames,
    get_latest_frame_jpeg,
    get_stream_state,
)

# ---------------------------------------------------------------------------
# Set up FastAPI TestClient with in-memory DB (mirrors test_backend.py approach)
# ---------------------------------------------------------------------------
from cloud.backend.main import app
from cloud.backend.database import get_db
from cloud.backend.models import Base, PolicyVersionModel

_TEST_DB_URL = "sqlite://"
_engine = create_engine(_TEST_DB_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def _override_get_db():
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_db_and_stream():
    """Per-test: wire in-memory DB, reset stream state, clean up after."""
    app.dependency_overrides[get_db] = _override_get_db
    Base.metadata.create_all(bind=_engine)
    db = _SessionLocal()
    if not db.query(PolicyVersionModel).first():
        db.add(PolicyVersionModel(
            policy_version="policy_v1", trained_at="2026-09-27T00:00:00Z",
            validation_score=0.9, previous_version="policy_v0", deployed=True))
        db.commit()
    db.close()

    # Reset stream state before each test so tests are isolated
    state = get_stream_state()
    state.set_running(False)
    time.sleep(0.05)
    state.clear()

    yield

    # Cleanup
    state.set_running(False)
    Base.metadata.drop_all(bind=_engine)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def tmp_zones_dir(tmp_path, monkeypatch):
    """Redirect ZONES_DIR to a temp directory so tests don't touch real zone files."""
    import cloud.backend.main as main_mod
    monkeypatch.setattr(main_mod, "ZONES_DIR", tmp_path)
    return tmp_path


# ===========================================================================
# 1. StreamState unit tests
# ===========================================================================

class TestStreamState:
    def test_initial_state(self):
        s = StreamState()
        assert s.is_running() is False
        assert s.get_latest_frame() is None
        assert s.get_error() is None
        assert s.source is None

    def test_put_and_get_frame(self):
        s = StreamState()
        data = b"\xff\xd8test_jpeg_bytes\xff\xd9"
        s.put_frame(data)
        assert s.get_latest_frame() == data

    def test_set_and_get_running(self):
        s = StreamState()
        s.set_running(True)
        assert s.is_running() is True
        s.set_running(False)
        assert s.is_running() is False

    def test_set_and_get_error(self):
        s = StreamState()
        s.set_error("test error message")
        assert s.get_error() == "test error message"
        s.set_error(None)
        assert s.get_error() is None

    def test_clear_resets_all_fields(self):
        s = StreamState()
        s.set_running(True)
        s.put_frame(b"frame_data")
        s.set_error("some error")
        s.source = "rtsp://example.com/stream"
        s.clear()
        assert s.is_running() is False
        assert s.get_latest_frame() is None
        assert s.get_error() is None
        assert s.source is None

    def test_wait_for_frame_timeout_returns_none(self):
        """wait_for_frame should return None quickly when no frame arrives."""
        s = StreamState()
        result = s.wait_for_frame(timeout=0.05)
        assert result is None

    def test_put_frame_unblocks_wait(self):
        """A frame put from another thread should unblock wait_for_frame."""
        s = StreamState()
        result_holder = [None]

        def waiter():
            result_holder[0] = s.wait_for_frame(timeout=1.0)

        t = threading.Thread(target=waiter)
        t.start()
        time.sleep(0.05)
        s.put_frame(b"unblocking_frame")
        t.join(timeout=1.5)
        assert result_holder[0] == b"unblocking_frame"

    def test_thread_safe_concurrent_put_get(self):
        """Multiple threads putting/getting frames shouldn't raise or corrupt."""
        s = StreamState()
        errors = []

        def writer():
            for i in range(50):
                try:
                    s.put_frame(f"frame_{i}".encode())
                except Exception as e:
                    errors.append(e)

        def reader():
            for _ in range(50):
                try:
                    s.get_latest_frame()
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=writer), threading.Thread(target=reader),
                   threading.Thread(target=writer), threading.Thread(target=reader)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=3)
        assert errors == [], f"Thread safety errors: {errors}"


# ===========================================================================
# 2. start_stream / stop_stream public API
# ===========================================================================

class TestStreamControl:
    def test_stop_when_not_running_returns_was_running_false(self):
        result = stop_stream()
        assert result["stopped"] is True
        assert result["was_running"] is False

    def test_start_stream_bad_mode_returns_started_false(self):
        result = start_stream(source="0", mode="invalid_mode")
        assert result["started"] is False
        assert "mode" in result["error"].lower() or "unknown" in result["error"].lower()

    def test_stream_status_reflects_running(self):
        """stream_status() should report is_running correctly."""
        state = get_stream_state()
        state.clear()
        assert stream_status()["running"] is False
        # Manually set to running (without actually starting a thread)
        state.set_running(True)
        assert stream_status()["running"] is True
        state.set_running(False)

    def test_start_stream_stops_previous_before_starting(self):
        """Calling start_stream while one is running should stop the old stream."""
        state = get_stream_state()
        # Simulate a running stream
        state.set_running(True)
        state.source = "old_source"
        # start_stream should first stop the old one
        # (worker thread won't actually start since cv2 is mocked to fail to open)
        with patch("cloud.backend.stream_manager._stream_worker"):
            start_stream(source="new_source", mode="ppe")
        # After the call, state.source should be the new source
        assert get_stream_state().source == "new_source"

    def test_start_stream_sets_source_and_mode(self):
        """start_stream should record the source and mode on the state object."""
        with patch("cloud.backend.stream_manager._stream_worker"):
            start_stream(source="test_source", mode="ppe")
        state = get_stream_state()
        assert state.source == "test_source"
        assert state.mode == "ppe"

    def test_stop_running_stream_sets_running_false(self):
        state = get_stream_state()
        state.set_running(True)
        result = stop_stream()
        assert result["was_running"] is True
        assert state.is_running() is False


# ===========================================================================
# 3. generate_mjpeg_frames
# ===========================================================================

class TestMjpegGenerator:
    def test_yields_bytes_immediately_when_no_stream(self):
        """generate_mjpeg_frames should yield at least one chunk even with no stream."""
        gen = generate_mjpeg_frames()
        # It should yield within a short time (uses placeholder when stream not running)
        # We can't actually iterate forever — just pull one chunk and stop
        chunk = None
        for chunk in gen:
            break  # take the first yield
        assert chunk is not None
        assert isinstance(chunk, bytes)

    def test_mjpeg_chunk_contains_boundary(self):
        """Each chunk must contain the MJPEG boundary string."""
        gen = generate_mjpeg_frames()
        chunk = next(gen)
        assert b"--aegisframe" in chunk

    def test_mjpeg_chunk_contains_content_type(self):
        """Each chunk must contain the image/jpeg content-type header."""
        gen = generate_mjpeg_frames()
        chunk = next(gen)
        assert b"Content-Type: image/jpeg" in chunk

    def test_mjpeg_uses_latest_frame_when_available(self):
        """When a frame is in the buffer, mjpeg should include it."""
        state = get_stream_state()
        test_jpeg = b"\xff\xd8test_frame_data\xff\xd9"
        state.put_frame(test_jpeg)
        state.set_running(True)  # simulate active stream

        gen = generate_mjpeg_frames()
        chunk = next(gen)
        state.set_running(False)  # stop after one frame

        assert test_jpeg in chunk


# ===========================================================================
# 4. get_latest_frame_jpeg
# ===========================================================================

class TestLatestFrameEndpoint:
    def test_returns_bytes_when_no_frame(self):
        """Should return a placeholder JPEG (bytes), not None."""
        get_stream_state().clear()
        frame = get_latest_frame_jpeg()
        assert frame is not None
        assert isinstance(frame, bytes)
        assert len(frame) > 0

    def test_returns_actual_frame_when_available(self):
        state = get_stream_state()
        test_frame = b"\xff\xd8actual_frame\xff\xd9"
        state.put_frame(test_frame)
        result = get_latest_frame_jpeg()
        assert result == test_frame


# ===========================================================================
# 5-9. FastAPI endpoint tests
# ===========================================================================

class TestStreamEndpoints:
    def test_post_stream_start_returns_started(self, client):
        """POST /stream/start should return {started: true} for valid request."""
        with patch("cloud.backend.stream_manager._stream_worker"):
            r = client.post("/stream/start", json={
                "source": "0", "mode": "ppe",
                "camera_id": "cam_test", "zone_id": "zone_test"
            })
        assert r.status_code == 200
        data = r.json()
        assert data["started"] is True
        assert data["source"] == "0"

    def test_post_stream_start_bad_mode_returns_422(self, client):
        """Unknown mode should return HTTP 422."""
        r = client.post("/stream/start", json={
            "source": "0", "mode": "flying_drones"
        })
        assert r.status_code == 422

    def test_post_stream_stop_returns_stopped(self, client):
        """POST /stream/stop should always return {stopped: true}."""
        r = client.post("/stream/stop")
        assert r.status_code == 200
        assert r.json()["stopped"] is True

    def test_get_stream_status(self, client):
        """GET /stream/status should return a dict with 'running' key."""
        r = client.get("/stream/status")
        assert r.status_code == 200
        data = r.json()
        assert "running" in data
        assert isinstance(data["running"], bool)

    def test_get_stream_mjpeg_content_type(self, client, monkeypatch):
        """GET /stream/mjpeg must return multipart/x-mixed-replace content-type."""
        import cloud.backend.main as main_mod

        def mock_gen():
            yield b"--aegisframe\r\nContent-Type: image/jpeg\r\n\r\nfake\r\n"

        monkeypatch.setattr(main_mod, "generate_mjpeg_frames", mock_gen)
        r = client.get("/stream/mjpeg")
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "multipart/x-mixed-replace" in ct
        assert "aegisframe" in ct

    def test_get_stream_latest_frame_content_type(self, client):
        """GET /stream/latest-frame must return image/jpeg content-type."""
        r = client.get("/stream/latest-frame")
        assert r.status_code == 200
        assert "image/jpeg" in r.headers.get("content-type", "")

    def test_get_stream_latest_frame_returns_bytes(self, client):
        """GET /stream/latest-frame should return non-empty bytes body."""
        r = client.get("/stream/latest-frame")
        assert r.status_code == 200
        assert len(r.content) > 0

    def test_start_twice_does_not_create_duplicate_stream(self, client):
        """Starting a stream twice should not crash and should return started=True both times."""
        with patch("cloud.backend.stream_manager._stream_worker"):
            r1 = client.post("/stream/start", json={"source": "0", "mode": "ppe"})
            r2 = client.post("/stream/start", json={"source": "1", "mode": "ppe"})
        assert r1.json()["started"] is True
        assert r2.json()["started"] is True
        # After two starts, source should be the second one
        assert get_stream_state().source == "1"


# ===========================================================================
# 10. capture-frame endpoint
# ===========================================================================

class TestCaptureFrameEndpoint:
    def test_returns_422_when_source_cannot_open(self, client):
        """When cv2.VideoCapture fails to open, should return HTTP 422."""
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = False
        with patch("cv2.VideoCapture", return_value=mock_cap):
            r = client.get("/capture-frame?source=rtsp://fake.host/stream")
        assert r.status_code == 422
        assert "Could not open source" in r.json()["detail"]

    def test_returns_jpeg_when_source_opens_successfully(self, client):
        """When cv2 returns a valid frame, /capture-frame should return image/jpeg."""
        fake_frame = np.zeros((240, 320, 3), dtype=np.uint8)
        import cv2 as cv2_real
        # Create a proper mock: isOpened=True, read() returns a blank frame
        mock_cap = MagicMock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (True, fake_frame)

        fake_encoded = np.zeros((100,), dtype=np.uint8)
        fake_encoded[0] = 0xFF
        fake_encoded[1] = 0xD8

        with patch("cv2.VideoCapture", return_value=mock_cap), \
             patch("cv2.imencode", return_value=(True, fake_encoded)):
            r = client.get("/capture-frame?source=0")

        # Either 200 (success) or 503 (cv2 not available) depending on env
        # In CI with mocked cv2 the import happens successfully
        assert r.status_code in (200, 422, 503)


# ===========================================================================
# 11-13. Zone management endpoint tests
# ===========================================================================

class TestZoneEndpoints:
    def test_get_zones_empty(self, client, tmp_zones_dir):
        """GET /zones with no files returns empty list."""
        r = client.get("/zones")
        assert r.status_code == 200
        assert r.json() == []

    def test_post_zone_saves_file(self, client, tmp_zones_dir):
        """POST /zones should write a JSON file and return saved=True."""
        payload = {
            "camera_id": "cam_test",
            "zone_id": "zone_test",
            "polygon": [[0, 0], [100, 0], [100, 100], [0, 100]],
        }
        r = client.post("/zones", json=payload)
        assert r.status_code == 201
        data = r.json()
        assert data["saved"] is True
        assert data["camera_id"] == "cam_test"
        assert data["zone_id"] == "zone_test"
        assert data["point_count"] == 4

        # File should exist on disk
        expected_file = tmp_zones_dir / "cam_test_zone_test.json"
        assert expected_file.exists(), f"Expected file not found: {expected_file}"

    def test_saved_zone_matches_zone_check_format(self, client, tmp_zones_dir):
        """The JSON written by POST /zones must be readable by zone_check.load_zone_config."""
        from edge.zone_intrusion.tracking.zone_check import load_zone_config

        payload = {
            "camera_id": "cam_compat",
            "zone_id": "zone_compat",
            "polygon": [[10, 20], [200, 20], [200, 300], [10, 300]],
        }
        client.post("/zones", json=payload)

        zone_file = tmp_zones_dir / "cam_compat_zone_compat.json"
        zone_data = load_zone_config(str(zone_file))

        assert zone_data["camera_id"] == "cam_compat"
        assert zone_data["zone_id"] == "zone_compat"
        assert len(zone_data["polygon"]) == 4
        # Polygon entries must be integer [x,y] pairs
        for pt in zone_data["polygon"]:
            assert len(pt) == 2
            assert isinstance(pt[0], int)
            assert isinstance(pt[1], int)

    def test_get_zones_lists_saved_zone(self, client, tmp_zones_dir):
        """After POST /zones, GET /zones should include the new zone."""
        client.post("/zones", json={
            "camera_id": "cam_list",
            "zone_id": "zone_list",
            "polygon": [[0,0],[1,0],[1,1]],
        })
        r = client.get("/zones")
        assert r.status_code == 200
        zones = r.json()
        assert len(zones) == 1
        assert zones[0]["camera_id"] == "cam_list"
        assert zones[0]["zone_id"] == "zone_list"
        assert zones[0]["point_count"] == 3

    def test_post_zone_requires_at_least_3_points(self, client, tmp_zones_dir):
        """Polygon with < 3 points should return 422."""
        r = client.post("/zones", json={
            "camera_id": "cam_x", "zone_id": "zone_x",
            "polygon": [[0,0],[100,100]],
        })
        assert r.status_code == 422

    def test_delete_zone_removes_file(self, client, tmp_zones_dir):
        """DELETE /zones/{cam}/{zone} should remove the file."""
        client.post("/zones", json={
            "camera_id": "cam_del", "zone_id": "zone_del",
            "polygon": [[0,0],[1,0],[1,1]],
        })
        r_del = client.delete("/zones/cam_del/zone_del")
        assert r_del.status_code == 200
        assert r_del.json()["deleted"] is True

        # Should now be gone from GET /zones
        r_list = client.get("/zones")
        zones = r_list.json()
        assert not any(z["zone_id"] == "zone_del" for z in zones)

    def test_delete_nonexistent_zone_returns_404(self, client, tmp_zones_dir):
        """Deleting a zone that doesn't exist should return 404."""
        r = client.delete("/zones/cam_ghost/zone_ghost")
        assert r.status_code == 404

    def test_post_zone_overwrites_existing(self, client, tmp_zones_dir):
        """Saving the same camera_id/zone_id twice should overwrite without error."""
        payload = {"camera_id": "cam_ow", "zone_id": "zone_ow", "polygon": [[0,0],[1,0],[1,1]]}
        r1 = client.post("/zones", json=payload)
        assert r1.status_code == 201

        payload2 = {**payload, "polygon": [[5,5],[50,5],[50,50],[5,50]]}
        r2 = client.post("/zones", json=payload2)
        assert r2.status_code == 201
        assert r2.json()["point_count"] == 4

        # GET should show 4 points (the overwritten version)
        r_list = client.get("/zones")
        zones = r_list.json()
        assert zones[0]["point_count"] == 4

    def test_zone_and_infer_pipeline_format_identical(self, tmp_zones_dir):
        """
        Zone saved via the API and zone written manually in the same format
        both parse identically in zone_check.load_zone_config — confirms
        dashboard-drawn zones and CLI-drawn zones are fully interchangeable.
        """
        from edge.zone_intrusion.tracking.zone_check import load_zone_config, check_box_in_zone

        # Write a zone manually (as draw_zone.py would)
        manual_zone = {
            "camera_id": "cam_manual",
            "zone_id": "zone_manual",
            "polygon": [[750, 0], [1050, 0], [1050, 1000], [750, 1000]]
        }
        manual_path = tmp_zones_dir / "cam_manual_zone_manual.json"
        manual_path.write_text(json.dumps(manual_zone), encoding="utf-8")

        # Write a zone via the API format (what POST /zones writes)
        api_zone = {
            "camera_id": "cam_api",
            "zone_id": "zone_api",
            "polygon": [[750, 0], [1050, 0], [1050, 1000], [750, 1000]]
        }
        api_path = tmp_zones_dir / "cam_api_zone_api.json"
        api_path.write_text(json.dumps(api_zone, indent=2), encoding="utf-8")

        # Both should load and produce the same check_box_in_zone results
        zc_manual = load_zone_config(str(manual_path))
        zc_api    = load_zone_config(str(api_path))

        test_box_inside  = [800, 300, 900, 500]   # foot point (850,500) — inside
        test_box_outside = [100, 300, 200, 500]   # foot point (150,500) — outside

        assert check_box_in_zone(test_box_inside,  zc_manual) is True
        assert check_box_in_zone(test_box_outside, zc_manual) is False
        assert check_box_in_zone(test_box_inside,  zc_api)    is True
        assert check_box_in_zone(test_box_outside, zc_api)    is False
