"""
infer.py

Runs the trained PPE detection model on a video source or camera feed with
ByteTrack multi-object tracking, applies a consecutive-frame debounce filter,
and emits Detection Events adhering strictly to the INTERFACES.md schema.

Events are appended to a local JSONL log and optionally forwarded to the
cloud/backend decision layer via HTTP POST.

Usage:
    # Run on default webcam:
    python infer.py --model models/ppe_final_v4.pt --source 0

    # Run on a video file with custom debounce and API forwarding:
    python infer.py --model models/ppe_final_v4.pt --source sample.mp4 \
        --camera-id cam_01 --zone-id zone_A --debounce 3 \
        --output-log events_log.jsonl --api-url http://localhost:8000/events
"""

import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ppe_infer")

# 16 Unified classes
UNIFIED_CLASSES = [
    "helmet",        # 0
    "no_helmet",     # 1
    "vest",          # 2
    "no_vest",       # 3
    "gloves",        # 4
    "no_gloves",     # 5
    "boots",         # 6
    "no_boots",      # 7
    "goggles",       # 8
    "no_goggles",    # 9
    "mask",          # 10
    "no_mask",       # 11
    "person",        # 12
    "safety_cone",   # 13
    "machinery",     # 14
    "vehicle",       # 15
]

# PPE violation classes that warrant safety alerts
PPE_VIOLATION_CLASSES: Set[str] = {
    "no_helmet",
    "no_vest",
    "no_gloves",
    "no_boots",
    "no_goggles",
    "no_mask",
}


def build_event(
    camera_id: str,
    zone_id: str,
    event_type: str,
    class_name: str,
    confidence: float,
    tracked_id: str,
    timestamp: str,
    frame_count_triggered: int,
    clip_captured: bool = False,
) -> Dict[str, Any]:
    """Build a Detection Event dictionary strictly adhering to INTERFACES.md.

    Schema:
        camera_id: str
        zone_id: str
        event_type: str ("ppe_violation" or "zone_intrusion")
        class: str ("no_helmet", "no_vest", etc.)
        confidence: float (JSON-serializable numeric)
        tracked_id: str (e.g. "person_142")
        timestamp: str (ISO8601 UTC string, e.g. "2026-09-05T14:32:10Z")
        frame_count_triggered: int (>= 3)
        clip_captured: bool
    """
    return {
        "camera_id": str(camera_id),
        "zone_id": str(zone_id),
        "event_type": str(event_type),
        "class": str(class_name),
        "confidence": round(float(confidence), 4),
        "tracked_id": str(tracked_id),
        "timestamp": str(timestamp),
        "frame_count_triggered": int(frame_count_triggered),
        "clip_captured": bool(clip_captured),
    }


class DebounceTracker:
    """Tracks consecutive detection counts per (track_id, violation_class) pair.

    Ensures alerts only trigger after a configured number of consecutive frames,
    suppresses repeated alerts while the violation persists, and safely resets
    state when a violation or track disappears so that ID reuses or reappearing
    violations start with clean counts.
    """

    def __init__(self, debounce_threshold: int = 3):
        if debounce_threshold < 1:
            raise ValueError("debounce_threshold must be >= 1")
        self.debounce_threshold = debounce_threshold
        # Structure: self.track_states[track_id][class_name] = {"count": int, "fired": bool, "confidence": float}
        self.track_states: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def reset(self) -> None:
        """Clear all tracking state."""
        self.track_states.clear()

    def update(self, detections: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Update tracker with detections from the current frame.

        Args:
            detections: List of dicts, each with keys:
                - "track_id": Any (int/str, will be stringified)
                - "class_name": str
                - "confidence": float

        Returns:
            List of triggered violation event descriptors:
                [{"track_id": str, "class_name": str, "confidence": float, "frame_count": int}]
        """
        detections = detections or []
        events_to_emit: List[Dict[str, Any]] = []

        # Deduplicate/aggregate detections per (track_id, class_name) in current frame
        current_frame_map: Dict[str, Dict[str, float]] = {}
        for det in detections:
            track_id = det.get("track_id")
            if track_id is None:
                continue
            t_key = str(track_id)
            c_name = str(det.get("class_name", ""))
            conf = float(det.get("confidence", 0.0))

            if t_key not in current_frame_map:
                current_frame_map[t_key] = {}
            if c_name not in current_frame_map[t_key] or conf > current_frame_map[t_key][c_name]:
                current_frame_map[t_key][c_name] = conf

        current_active_tracks = set(current_frame_map.keys())

        # 1. Age out / clean up tracks that disappeared from the frame
        for old_track_id in list(self.track_states.keys()):
            if old_track_id not in current_active_tracks:
                # Track completely left frame -> delete state to prevent ID-reuse leakage
                del self.track_states[old_track_id]
            else:
                # Track is present, but clean up violation classes that disappeared
                active_classes_for_track = current_frame_map[old_track_id]
                for old_cls in list(self.track_states[old_track_id].keys()):
                    if old_cls not in active_classes_for_track:
                        del self.track_states[old_track_id][old_cls]

        # 2. Update counts and evaluate trigger condition for current frame detections
        for t_key, classes_dict in current_frame_map.items():
            if t_key not in self.track_states:
                self.track_states[t_key] = {}

            for c_name, conf in classes_dict.items():
                if c_name not in self.track_states[t_key]:
                    self.track_states[t_key][c_name] = {
                        "count": 1,
                        "fired": False,
                        "confidence": conf,
                    }
                else:
                    state = self.track_states[t_key][c_name]
                    state["count"] += 1
                    state["confidence"] = conf

                state = self.track_states[t_key][c_name]
                if state["count"] >= self.debounce_threshold and not state["fired"]:
                    state["fired"] = True
                    events_to_emit.append({
                        "track_id": t_key,
                        "class_name": c_name,
                        "confidence": state["confidence"],
                        "frame_count": state["count"],
                    })

        return events_to_emit


def log_event(event: Dict[str, Any], output_path: Path) -> None:
    """Append event JSON line to local log file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def post_event(event: Dict[str, Any], api_url: str) -> bool:
    """Send event JSON payload to backend endpoint via HTTP POST."""
    try:
        import requests
        resp = requests.post(api_url, json=event, timeout=5)
        resp.raise_for_status()
        return True
    except Exception as exc:
        logger.warning("Failed to POST event to %s: %s", api_url, exc)
        return False


def run_inference(
    model_path: str,
    source: str,
    camera_id: str = "cam_01",
    zone_id: str = "zone_A",
    conf: float = 0.25,
    debounce_frames: int = 3,
    api_url: Optional[str] = None,
    output_log: str = "events_log.jsonl",
    show: bool = False,
    save_video: Optional[str] = None,
) -> None:
    """Run YOLOv11 + ByteTrack inference pipeline on video/stream."""
    try:
        from ultralytics import YOLO
    except ImportError:
        raise RuntimeError("ultralytics is required for run_inference. Install via 'pip install ultralytics'.")

    model_file = Path(model_path)
    if not model_file.exists():
        raise FileNotFoundError(f"Model file not found at {model_file}")

    logger.info("Loading model from %s...", model_file)
    model = YOLO(str(model_file))

    # Parse camera source (int for webcam, str for path)
    src: Any = int(source) if source.isdigit() else source
    log_path = Path(output_log)
    tracker = DebounceTracker(debounce_threshold=debounce_frames)

    logger.info("Starting inference on source: %s (conf=%.2f, debounce=%d)", src, conf, debounce_frames)

    # Run stream with ByteTrack
    results = model.track(
        source=src,
        conf=conf,
        tracker="bytetrack.yaml",
        stream=True,
        show=show,
        save=bool(save_video),
    )

    for frame_idx, r in enumerate(results):
        frame_detections: List[Dict[str, Any]] = []

        if r.boxes is not None and r.boxes.id is not None:
            boxes = r.boxes
            for box in boxes:
                track_id = int(box.id[0].item()) if box.id is not None else None
                if track_id is None:
                    continue
                cls_id = int(box.cls[0].item())
                confidence = float(box.conf[0].item())
                class_name = model.names.get(cls_id, f"class_{cls_id}")

                # Only evaluate PPE violation classes
                if class_name in PPE_VIOLATION_CLASSES:
                    frame_detections.append({
                        "track_id": track_id,
                        "class_name": class_name,
                        "confidence": confidence,
                    })
        else:
            # If tracker loses all tracks or no boxes present, update with empty list
            frame_detections = []

        triggered_events = tracker.update(frame_detections)
        for trig in triggered_events:
            tid = trig["track_id"]
            tracked_id_str = f"person_{tid}" if not str(tid).startswith("person_") else str(tid)
            timestamp_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            event = build_event(
                camera_id=camera_id,
                zone_id=zone_id,
                event_type="ppe_violation",
                class_name=trig["class_name"],
                confidence=trig["confidence"],
                tracked_id=tracked_id_str,
                timestamp=timestamp_str,
                frame_count_triggered=trig["frame_count"],
                clip_captured=False,
            )

            logger.warning(
                "PPE Violation Detected: %s on %s (conf: %.2f, frame_count: %d)",
                event["class"], event["tracked_id"], event["confidence"], event["frame_count_triggered"]
            )
            log_event(event, log_path)

            if api_url:
                post_event(event, api_url)

    logger.info("Inference completed. Events written to %s", log_path)


def main():
    parser = argparse.ArgumentParser(description="PPE Detection Inference with ByteTrack and Debounce Filtering")
    parser.add_argument("--model", default="edge/ppe_detection/models/ppe_final_v4.pt", help="Path to model weights")
    parser.add_argument("--source", default="0", help="Video source (camera index e.g. 0, or file path)")
    parser.add_argument("--camera-id", default="cam_01", help="Camera ID (e.g. cam_01)")
    parser.add_argument("--zone-id", default="zone_A", help="Zone ID (e.g. zone_A)")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold")
    parser.add_argument("--debounce", type=int, default=3, help="Consecutive frames debounce count")
    parser.add_argument("--api-url", default=None, help="Backend URL to POST events to")
    parser.add_argument("--output-log", default="events_log.jsonl", help="Path to output JSONL log file")
    parser.add_argument("--show", action="store_true", help="Display annotated live video window")
    parser.add_argument("--save-video", default=None, help="Path or flag to save output video")
    args = parser.parse_args()

    run_inference(
        model_path=args.model,
        source=args.source,
        camera_id=args.camera_id,
        zone_id=args.zone_id,
        conf=args.conf,
        debounce_frames=args.debounce,
        api_url=args.api_url,
        output_log=args.output_log,
        show=args.show,
        save_video=args.save_video,
    )


if __name__ == "__main__":
    main()
