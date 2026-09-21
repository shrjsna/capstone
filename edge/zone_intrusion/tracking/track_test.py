"""
Module B - Piece 1: Detection + Tracking test script.

Goal: confirm we can detect people in a video/webcam feed and that each
person keeps a STABLE track_id across frames (that's what ByteTrack gives us,
and everything downstream - zone-check, debounce - depends on it working).

Usage:
    python track_test.py --source 0                # webcam
    python track_test.py --source path/to/video.mp4 # video file

Press 'q' in the video window to quit.
"""

import argparse
import cv2
from ultralytics import YOLO


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=str,
        default="0",
        help="Video source: '0' for webcam, or a path to a video file",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="yolo11n.pt",
        help="Model weights to use. Start with yolo11n.pt (auto-downloads). "
             "Switch to an RT-DETR weight file later if Jetson Nano compute allows.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # '0' as a string means webcam; ultralytics wants an int for that case
    source = 0 if args.source == "0" else args.source

    model = YOLO(args.model)

    print(f"Loading model: {args.model}")
    print(f"Source: {'webcam' if source == 0 else source}")
    print("Press 'q' in the video window to quit.\n")

    # classes=[0] restricts detection to the 'person' class only (COCO class 0)
    # - we don't care about any other object class for this module.
    results = model.track(
        source=source,
        tracker="bytetrack.yaml",
        persist=True,   # keep track IDs consistent across frames
        stream=True,    # process frame-by-frame instead of loading it all into memory
        classes=[0],
        verbose=False,
    )

    for frame_result in results:
        frame = frame_result.plot()  # draws boxes + track IDs on the frame for us

        boxes = frame_result.boxes
        if boxes is not None and boxes.id is not None:
            track_ids = boxes.id.int().tolist()
            confidences = boxes.conf.tolist()
            for tid, conf in zip(track_ids, confidences):
                print(f"  track_id={tid}  confidence={conf:.2f}")

        cv2.imshow("Module B - Tracking Test", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
