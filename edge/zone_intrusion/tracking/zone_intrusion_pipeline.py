"""
Module B - Piece 5 (partial): wire detect+track + zone-check + debounce
together into one live pipeline. When debounce fires, prints an event dict
matching the INTERFACES.md schema shape (clip_captured hardcoded False for
now - that's piece 6, not built yet).

Usage:
    python zone_intrusion_pipeline.py --source "http://192.168.1.5:8080/video"
Press 'q' in the video window to quit.
"""

import argparse
import json
import os
from datetime import datetime, timezone

import cv2
from ultralytics import YOLO

try:
    from .zone_check import load_zone_config, check_box_in_zone
    from .debounce_tracker import DebounceTracker
    from .clip_capture import RollingClipRecorder, downsample_clip, blur_faces, save_clip, CLIP_FPS
except (ImportError, ValueError):
    from zone_check import load_zone_config, check_box_in_zone
    from debounce_tracker import DebounceTracker
    from clip_capture import RollingClipRecorder, downsample_clip, blur_faces, save_clip, CLIP_FPS


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=str, required=True)
    parser.add_argument("--model", type=str, default="yolo11n.pt")
    parser.add_argument("--zone_config", type=str,
                         default="../zones/camera_01_zones.json")
    parser.add_argument("--debounce_frames", type=int, default=4)
    parser.add_argument("--events_log", type=str, default="../events.jsonl",
                         help="Path to append each fired event as a JSON line")
    parser.add_argument("--clips_dir", type=str, default="../clips",
                         help="Folder to save captured clips into")
    parser.add_argument("--source_fps", type=float, default=15.0,
                         help="Approximate fps of the incoming stream, used to size the rolling buffer")
    return parser.parse_args()


def log_event(event, log_path):
    """Append one event as a single JSON line to the log file (JSONL format:
    one JSON object per line, so the file can be read/parsed line-by-line
    without loading everything into memory - standard for event logs)."""
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    with open(log_path, "a") as f:
        f.write(json.dumps(event) + "\n")


def build_event(camera_id, zone_id, track_id, confidence, frame_count_triggered):
    return {
        "camera_id": camera_id,
        "zone_id": zone_id,
        "event_type": "zone_intrusion",
        "class": "person_in_zone",
        "confidence": round(confidence, 2),
        "tracked_id": f"person_{track_id}",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "frame_count_triggered": frame_count_triggered,
        "clip_captured": True,
    }


def main():
    args = parse_args()
    source = 0 if args.source == "0" else args.source

    zone = load_zone_config(args.zone_config)
    debouncer = DebounceTracker(required_frames=args.debounce_frames)
    model = YOLO(args.model)

    os.makedirs(args.clips_dir, exist_ok=True)

    def on_clip_ready(event_id, frames):
        print(f"Clip ready for {event_id}: {len(frames)} raw frames. "
              f"Blurring faces and saving...")
        blurred = [blur_faces(f.copy()) for f in frames]
        downsampled = downsample_clip(blurred, source_fps=args.source_fps)
        out_path = os.path.join(args.clips_dir, f"{event_id}.mp4")
        save_clip(downsampled, out_path, fps=CLIP_FPS)
        print(f"Saved clip: {out_path} ({len(downsampled)} frames)\n")

    recorder = RollingClipRecorder(source_fps=args.source_fps,
                                    on_clip_ready=on_clip_ready)

    print(f"Zone loaded: {zone['zone_id']} on {zone['camera_id']}")
    print(f"Debounce: {args.debounce_frames} consecutive frames required")
    print("Press 'q' in the video window to quit.\n")

    # Draw the zone polygon on every frame so you can SEE it overlaid on the
    # live feed, not just trust the coordinates blindly.
    polygon_pts = zone["polygon"]

    results = model.track(
        source=source,
        tracker="bytetrack.yaml",
        persist=True,
        stream=True,
        classes=[0],  # person only
        verbose=False,
    )

    # Track each person's current consecutive-in-zone frame count, purely
    # for populating frame_count_triggered in the event.
    frame_counts = {}

    for frame_result in results:
        frame = frame_result.plot()
        recorder.add_frame(frame.copy())

        # Draw the zone polygon in red so it's visible on screen.
        import numpy as np
        pts = np.array(polygon_pts, dtype=np.int32).reshape((-1, 1, 2))
        cv2.polylines(frame, [pts], isClosed=True, color=(0, 0, 255), thickness=2)

        boxes = frame_result.boxes
        if boxes is not None and boxes.id is not None:
            track_ids = boxes.id.int().tolist()
            confidences = boxes.conf.tolist()
            xyxy = boxes.xyxy.tolist()

            for tid, conf, box in zip(track_ids, confidences, xyxy):
                in_zone = check_box_in_zone(box, zone)

                key = (tid, "person")
                if in_zone:
                    frame_counts[key] = frame_counts.get(key, 0) + 1
                else:
                    frame_counts[key] = 0

                fired = debouncer.update(track_id=tid, cls="person", is_in_zone=in_zone)

                if fired:
                    event = build_event(
                        camera_id=zone["camera_id"],
                        zone_id=zone["zone_id"],
                        track_id=tid,
                        confidence=conf,
                        frame_count_triggered=frame_counts[key],
                    )
                    print("EVENT FIRED:")
                    print(json.dumps(event, indent=2))
                    print()
                    log_event(event, args.events_log)

                    event_id = f"{event['tracked_id']}_{event['timestamp'].replace(':', '-')}"
                    recorder.trigger(event_id)

        cv2.imshow("Module B - Zone Intrusion Pipeline", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
