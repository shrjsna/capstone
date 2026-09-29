"""
cloud/backend/stream_manager.py
================================
Background live-stream inference manager for the AEGIS Safety backend.

Architecture decision (see docs/decisions.md 2026-09-27):
    Uses MJPEG multipart/x-mixed-replace streaming where supported, with a
    polling /latest-frame fallback. The background thread runs cv2.VideoCapture
    on whichever source is given (webcam index, file path, or RTSP/HTTP URL),
    runs the YOLO model on each frame, draws annotations, and stores the latest
    JPEG-encoded frame in a thread-safe buffer. The FastAPI MJPEG endpoint reads
    from that buffer continuously.

Privacy: the stream manager NEVER persists raw frames to disk. Only annotated
JPEG bytes live in the in-memory ring buffer (single latest frame). Detection
events are forwarded to the same /events pipeline as the standalone infer.py
script, so they appear in the alert feed and trigger bandit decisions normally.

Reuse policy: DebounceTracker and build_event are imported directly from
edge/ppe_detection/infer.py — not reimplemented. Zone-check logic is imported
from edge/zone_intrusion/tracking/zone_check.py. No duplicate debounce logic.
"""

import sys
import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

import numpy as np

logger = logging.getLogger("stream_manager")

# ---------------------------------------------------------------------------
# Reuse existing edge module logic — not reimplemented
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from edge.ppe_detection.infer import (
    DebounceTracker,
    PPE_VIOLATION_CLASSES,
    build_event,
    post_event,
)

# ---------------------------------------------------------------------------
# Optional zone-check imports (only needed in zone_intrusion mode)
# ---------------------------------------------------------------------------
try:
    from edge.zone_intrusion.tracking.zone_check import (
        load_zone_config,
        check_box_in_zone,
    )
    from edge.zone_intrusion.tracking.debounce_tracker import (
        DebounceTracker as ZoneDebounceTracker,
    )
    _ZONE_SUPPORT = True
except ImportError:
    _ZONE_SUPPORT = False
    logger.warning("Zone intrusion modules not importable — zone_intrusion mode unavailable.")

# Lazy cv2 / ultralytics imports so tests can mock them without GPU
_cv2 = None
_YOLO = None


def _get_cv2():
    global _cv2
    if _cv2 is None:
        import cv2 as _cv2_real
        _cv2 = _cv2_real
    return _cv2


def _get_yolo():
    global _YOLO
    if _YOLO is None:
        from ultralytics import YOLO as _YOLO_real
        _YOLO = _YOLO_real
    return _YOLO


# ---------------------------------------------------------------------------
# StreamState — shared mutable state accessed by background thread + endpoints
# ---------------------------------------------------------------------------

class StreamState:
    """Thread-safe container for the single active stream's state."""

    def __init__(self):
        self._lock = threading.Lock()
        self.running: bool = False
        self.source: Optional[str] = None
        self.mode: str = "ppe"          # "ppe" | "zone_intrusion"
        self.zone_config_path: Optional[str] = None
        self.camera_id: str = "stream_cam"
        self.zone_id: str = "stream_zone"
        self.api_url: Optional[str] = None   # backend /events URL for self-posting
        self.error: Optional[str] = None     # last error message, cleared on new start
        # Latest annotated JPEG frame bytes — None until first frame ready
        self._latest_frame: Optional[bytes] = None
        self._frame_event = threading.Event()  # set when a new frame is available
        self._thread: Optional[threading.Thread] = None

    # ---- Frame access (thread-safe) ----------------------------------------

    def put_frame(self, jpeg_bytes: bytes) -> None:
        with self._lock:
            self._latest_frame = jpeg_bytes
        self._frame_event.set()

    def get_latest_frame(self) -> Optional[bytes]:
        with self._lock:
            return self._latest_frame

    def wait_for_frame(self, timeout: float = 2.0) -> Optional[bytes]:
        """Block until a new frame is available or timeout. Returns bytes or None."""
        self._frame_event.wait(timeout=timeout)
        self._frame_event.clear()
        return self.get_latest_frame()

    # ---- Control (thread-safe) ---------------------------------------------

    def set_running(self, val: bool) -> None:
        with self._lock:
            self.running = val

    def is_running(self) -> bool:
        with self._lock:
            return self.running

    def set_error(self, msg: Optional[str]) -> None:
        with self._lock:
            self.error = msg

    def get_error(self) -> Optional[str]:
        with self._lock:
            return self.error

    def clear(self) -> None:
        """Reset all state (called before starting a new stream)."""
        with self._lock:
            self.running = False
            self.source = None
            self.mode = "ppe"
            self.zone_config_path = None
            self.camera_id = "stream_cam"
            self.zone_id = "stream_zone"
            self.api_url = None
            self.error = None
            self._latest_frame = None
        self._frame_event.clear()


# Module-level singleton — one stream at a time
_stream_state = StreamState()


def get_stream_state() -> StreamState:
    return _stream_state


# ---------------------------------------------------------------------------
# Background worker thread
# ---------------------------------------------------------------------------

def _draw_ppe_annotations(frame, boxes, model_names: Dict[int, str]) -> List[Dict]:
    """Draw PPE violation boxes on frame, return list of detection dicts."""
    cv2 = _get_cv2()
    detections = []
    if boxes is None or boxes.id is None:
        return detections

    for box in boxes:
        track_id = int(box.id[0].item()) if box.id is not None else None
        if track_id is None:
            continue
        cls_id = int(box.cls[0].item())
        confidence = float(box.conf[0].item())
        class_name = model_names.get(cls_id, f"class_{cls_id}")

        if class_name not in PPE_VIOLATION_CLASSES:
            continue

        # Get bounding box
        x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]

        # Draw box (amber for PPE violations: BGR 0,191,251)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 191, 251), 2)
        label = f"{class_name} {confidence:.2f} id:{track_id}"
        cv2.putText(frame, label, (x1, max(y1 - 6, 14)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 191, 251), 1, cv2.LINE_AA)

        detections.append({
            "track_id": track_id,
            "class_name": class_name,
            "confidence": confidence,
        })

    return detections


def _draw_zone_annotations(frame, zone_config: Dict, boxes,
                            frame_counts: Dict) -> List[Dict]:
    """Draw zone polygon + tracked persons, return in-zone detection dicts."""
    cv2 = _get_cv2()
    detections = []

    # Draw zone polygon (cyan: BGR 251,191,36 → actually use cyan 255,230,0)
    polygon = zone_config.get("polygon", [])
    if polygon:
        pts = np.array(polygon, dtype=np.int32).reshape((-1, 1, 2))
        cv2.polylines(frame, [pts], isClosed=True, color=(0, 230, 255), thickness=2)
        # Semi-transparent fill
        overlay = frame.copy()
        cv2.fillPoly(overlay, [pts], color=(0, 230, 255))
        cv2.addWeighted(overlay, 0.08, frame, 0.92, 0, frame)
        # Label
        if polygon:
            lx, ly = polygon[0]
            cv2.putText(frame, zone_config.get("zone_id", "zone"),
                        (lx, max(ly - 6, 14)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 230, 255), 1, cv2.LINE_AA)

    if boxes is None or boxes.id is None:
        return detections

    track_ids = boxes.id.int().tolist()
    confidences = boxes.conf.tolist()
    xyxy_list = boxes.xyxy.tolist()

    for tid, conf, xyxy in zip(track_ids, confidences, xyxy_list):
        x1, y1, x2, y2 = [int(v) for v in xyxy]
        in_zone = check_box_in_zone(xyxy, zone_config) if _ZONE_SUPPORT else False

        key = (tid, "person")
        if in_zone:
            frame_counts[key] = frame_counts.get(key, 0) + 1
            color = (0, 50, 255)    # red when in zone (BGR)
        else:
            frame_counts[key] = 0
            color = (180, 180, 180)  # grey when outside

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        in_label = "IN-ZONE" if in_zone else "safe"
        cv2.putText(frame, f"id:{tid} {in_label}", (x1, max(y1 - 6, 14)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1, cv2.LINE_AA)

        if in_zone:
            detections.append({
                "track_id": tid,
                "confidence": conf,
                "in_zone": True,
            })

    return detections


def _stream_worker(state: StreamState, model_path: str, events_api_url: Optional[str],
                   debounce_frames: int, conf_threshold: float) -> None:
    """
    Background thread: open source, run inference loop, put JPEG frames into state.
    Exits when state.running becomes False or an unrecoverable error occurs.
    """
    cv2 = _get_cv2()
    YOLO = _get_yolo()

    source_raw = state.source
    # Convert "0" / "1" string integers to actual int for cv2
    source = int(source_raw) if (isinstance(source_raw, str) and source_raw.isdigit()) else source_raw

    logger.info("[stream] Opening source: %s", source)

    # --- Open capture ---
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        msg = f"Could not open source: {source_raw!r}. Check the URL/path/index."
        logger.error("[stream] %s", msg)
        state.set_error(msg)
        state.set_running(False)
        return

    logger.info("[stream] Source opened. Loading model: %s", model_path)

    # --- Load model ---
    try:
        model = YOLO(model_path)
    except Exception as exc:
        msg = f"Failed to load model from {model_path!r}: {exc}"
        logger.error("[stream] %s", msg)
        state.set_error(msg)
        state.set_running(False)
        cap.release()
        return

    # --- Zone config (if zone_intrusion mode) ---
    zone_config: Optional[Dict] = None
    zone_debouncer = None
    if state.mode == "zone_intrusion":
        if not _ZONE_SUPPORT:
            state.set_error("Zone intrusion modules not available on this installation.")
            state.set_running(False)
            cap.release()
            return
        if state.zone_config_path:
            try:
                zone_config = load_zone_config(state.zone_config_path)
                logger.info("[stream] Zone config loaded: %s", state.zone_config_path)
            except Exception as exc:
                msg = f"Failed to load zone config {state.zone_config_path!r}: {exc}"
                logger.error("[stream] %s", msg)
                state.set_error(msg)
                state.set_running(False)
                cap.release()
                return
        else:
            # Default zone config path
            default_zone = str(_REPO_ROOT / "edge" / "zone_intrusion" / "zones" / "camera_01_zones.json")
            try:
                zone_config = load_zone_config(default_zone)
            except Exception:
                zone_config = None

        zone_debouncer = ZoneDebounceTracker(required_frames=debounce_frames)

    # --- PPE debouncer ---
    ppe_debouncer = DebounceTracker(debounce_threshold=debounce_frames)
    frame_counts: Dict = {}  # for zone mode

    logger.info("[stream] Inference loop starting (mode=%s, debounce=%d)",
                state.mode, debounce_frames)

    webcam_fail_count = 0
    # --- Inference loop ---
    while state.is_running():
        ret, frame = cap.read()
        if not ret:
            if isinstance(source, int):
                webcam_fail_count += 1
                if webcam_fail_count < 15:
                    time.sleep(0.05)
                    continue
                logger.warning("[stream] Webcam disconnected or unavailable — stopping.")
                break
            # End of file — loop the video (useful for demo with a video file)
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = cap.read()
            if not ret:
                logger.warning("[stream] Source exhausted and cannot rewind — stopping.")
                break
        webcam_fail_count = 0

        h, w = frame.shape[:2]

        if state.mode == "ppe":
            # --- PPE detection mode ---
            try:
                results = model.track(
                    source=frame,
                    conf=conf_threshold,
                    tracker="bytetrack.yaml",
                    persist=True,
                    verbose=False,
                )
            except Exception as exc:
                logger.warning("[stream] Model track failed: %s", exc)
                results = []

            frame_detections = []
            for r in results:
                raw = _draw_ppe_annotations(frame, r.boxes, model.names)
                frame_detections.extend(raw)

            triggered = ppe_debouncer.update(frame_detections)
            for trig in triggered:
                ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                event = build_event(
                    camera_id=state.camera_id,
                    zone_id=state.zone_id,
                    event_type="ppe_violation",
                    class_name=trig["class_name"],
                    confidence=trig["confidence"],
                    tracked_id=f"person_{trig['track_id']}",
                    timestamp=ts,
                    frame_count_triggered=trig["frame_count"],
                    clip_captured=False,
                )
                logger.warning("[stream] PPE event: %s conf=%.2f", event["class"], event["confidence"])
                if events_api_url:
                    post_event(event, events_api_url)

        elif state.mode == "zone_intrusion" and _ZONE_SUPPORT:
            # --- Zone intrusion mode ---
            # Dynamically determine person class index from model
            person_cls_id = None
            if hasattr(model, "names") and isinstance(model.names, dict):
                for cid, cname in model.names.items():
                    if str(cname).lower() == "person":
                        person_cls_id = cid
                        break
            classes_to_track = [person_cls_id] if person_cls_id is not None else [0]

            try:
                results = model.track(
                    source=frame,
                    conf=conf_threshold,
                    tracker="bytetrack.yaml",
                    persist=True,
                    classes=classes_to_track,
                    verbose=False,
                )
            except Exception as exc:
                logger.warning("[stream] Model track failed: %s", exc)
                results = []

            for r in results:
                if zone_config:
                    zone_dets = _draw_zone_annotations(
                        frame, zone_config, r.boxes, frame_counts
                    )
                else:
                    zone_dets = []

                for det in zone_dets:
                    tid = det["track_id"]
                    conf = det["confidence"]
                    if zone_debouncer:
                        fired = zone_debouncer.update(
                            track_id=tid, cls="person", is_in_zone=True
                        )
                        if fired:
                            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                            zid = zone_config["zone_id"] if zone_config else state.zone_id
                            cam = zone_config.get("camera_id", state.camera_id) if zone_config else state.camera_id
                            event = {
                                "camera_id": cam,
                                "zone_id": zid,
                                "event_type": "zone_intrusion",
                                "class": "person_in_zone",
                                "confidence": round(conf, 4),
                                "tracked_id": f"person_{tid}",
                                "timestamp": ts,
                                "frame_count_triggered": frame_counts.get((tid, "person"), debounce_frames),
                                "clip_captured": False,
                            }
                            logger.warning("[stream] Zone intrusion event: person_%s", tid)
                            if events_api_url:
                                post_event(event, events_api_url)

                # Reset zone debouncer for persons NOT in zone this frame
                if r.boxes is not None and r.boxes.id is not None and zone_debouncer:
                    in_zone_ids = {det["track_id"] for det in zone_dets}
                    for tid_all in r.boxes.id.int().tolist():
                        if tid_all not in in_zone_ids:
                            zone_debouncer.update(
                                track_id=tid_all, cls="person", is_in_zone=False
                            )

        # --- Add stream overlay (mode label + source) ---
        mode_label = "PPE DETECTION" if state.mode == "ppe" else "ZONE INTRUSION"
        cv2.putText(frame, f"AEGIS LIVE — {mode_label}", (8, 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (56, 189, 248), 1, cv2.LINE_AA)
        cv2.putText(frame, f"src: {str(source_raw)[:40]}", (8, h - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (100, 100, 100), 1, cv2.LINE_AA)

        # --- Encode to JPEG and store ---
        ok, jpeg_buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if ok:
            state.put_frame(jpeg_buf.tobytes())

    # --- Cleanup ---
    cap.release()
    state.set_running(False)
    logger.info("[stream] Worker thread exited cleanly.")


# Concurrency & Client Management Locks
_stream_control_lock = threading.Lock()
_client_count_lock = threading.Lock()
_active_mjpeg_clients = 0
MAX_MJPEG_CLIENTS = 10
_capture_lock = threading.Lock()


def get_capture_lock() -> threading.Lock:
    return _capture_lock


def start_stream(
    source: str,
    mode: str = "ppe",
    model_path: Optional[str] = None,
    zone_config_path: Optional[str] = None,
    camera_id: str = "stream_cam",
    zone_id: str = "stream_zone",
    events_api_url: Optional[str] = None,
    debounce_frames: int = 3,
    conf_threshold: float = 0.25,
) -> Dict[str, Any]:
    """
    Start a background inference stream safely with re-entrancy protection.
    If a stream is already running, it is cleanly stopped and joined first.
    """
    with _stream_control_lock:
        state = _stream_state

        # Stop and join any running worker thread
        if state.is_running():
            stop_stream()
            if state._thread and state._thread.is_alive():
                state._thread.join(timeout=2.0)

        if mode not in ("ppe", "zone_intrusion"):
            return {
                "started": False,
                "error": f"Unknown mode '{mode}'. Use 'ppe' or 'zone_intrusion'.",
                "source": source,
            }

        # Default model path
        if model_path is None:
            model_path = str(_REPO_ROOT / "edge" / "ppe_detection" / "models" / "ppe_final_v4.pt")

        state.clear()
        state.source = source
        state.mode = mode
        state.zone_config_path = zone_config_path
        state.camera_id = camera_id
        state.zone_id = zone_id
        state.api_url = events_api_url
        state.set_running(True)

        thread = threading.Thread(
            target=_stream_worker,
            args=(state, model_path, events_api_url, debounce_frames, conf_threshold),
            daemon=True,
            name="aegis-stream-worker",
        )
        thread.start()
        state._thread = thread

        logger.info("[stream] Started: source=%s mode=%s", source, mode)
        return {"started": True, "error": None, "source": source, "mode": mode}


def stop_stream() -> Dict[str, Any]:
    """Signal the background stream worker to stop and wait briefly for release."""
    state = _stream_state
    if not state.is_running():
        return {"stopped": True, "was_running": False}
    state.set_running(False)
    logger.info("[stream] Stop requested.")
    return {"stopped": True, "was_running": True}


def stream_status() -> Dict[str, Any]:
    """Return current stream state for the /stream/status endpoint."""
    state = _stream_state
    with _client_count_lock:
        client_count = _active_mjpeg_clients
    return {
        "running": state.is_running(),
        "source": state.source,
        "mode": state.mode,
        "camera_id": state.camera_id,
        "zone_id": state.zone_id,
        "error": state.get_error(),
        "has_frame": state.get_latest_frame() is not None,
        "active_viewers": client_count,
    }


def generate_mjpeg_frames() -> Generator[bytes, None, None]:
    """
    Yield MJPEG boundary-encoded frame chunks for multipart/x-mixed-replace.
    Protects server against client explosion by enforcing a MAX_MJPEG_CLIENTS limit.
    """
    global _active_mjpeg_clients
    with _client_count_lock:
        if _active_mjpeg_clients >= MAX_MJPEG_CLIENTS:
            err_frame = _make_placeholder_frame(f"Max viewers ({MAX_MJPEG_CLIENTS}) reached")
            yield b"--aegisframe\r\nContent-Type: image/jpeg\r\n\r\n" + err_frame + b"\r\n"
            return
        _active_mjpeg_clients += 1

    state = _stream_state
    boundary = b"--aegisframe\r\n"
    content_type = b"Content-Type: image/jpeg\r\n\r\n"
    tail = b"\r\n"

    placeholder = _make_placeholder_frame("No active stream")

    try:
        while True:
            if state.is_running():
                frame_bytes = state.wait_for_frame(timeout=2.0)
            else:
                frame_bytes = None
                time.sleep(0.4)  # Conservative polling when inactive

            if frame_bytes is None:
                frame_bytes = placeholder

            yield boundary + content_type + frame_bytes + tail
    finally:
        with _client_count_lock:
            _active_mjpeg_clients = max(0, _active_mjpeg_clients - 1)



def get_latest_frame_jpeg() -> Optional[bytes]:
    """Return the single latest JPEG frame (for polling fallback endpoint)."""
    frame = _stream_state.get_latest_frame()
    if frame is None:
        return _make_placeholder_frame("No active stream")
    return frame


def _make_placeholder_frame(message: str = "No stream") -> bytes:
    """Return a small grey JPEG with a text message — used when no stream is running."""
    try:
        cv2 = _get_cv2()
        import numpy as np
        img = np.zeros((240, 426, 3), dtype=np.uint8)
        img[:] = (24, 32, 48)  # dark navy matching AEGIS palette
        cv2.putText(img, "AEGIS LIVE STREAM", (50, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (56, 189, 248), 2, cv2.LINE_AA)
        cv2.putText(img, message, (50, 140),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 116, 139), 1, cv2.LINE_AA)
        _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 60])
        return buf.tobytes()
    except Exception:
        # Absolute fallback: minimal valid 1x1 grey JPEG
        return (
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c"
            b"\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c"
            b"\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\x1edL\tE\x11\x00\x01\x01"
            b"\x00\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f"
            b"\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00"
            b"\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01"
            b"\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11"
            b"\x05\x12!1A\x06\x13Qa\x07\"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1"
            b"\xf0$3br\x82\t\n\x16\x17\x18\x19\x1a%&'()*456789:CDEFGHIJSTUVWXYZ"
            b"cdefghijstuvwxyz\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97"
            b"\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7"
            b"\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7"
            b"\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4\xf5"
            b"\xf6\xf7\xf8\xf9\xfa\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xfb\xff\xd9"
        )
