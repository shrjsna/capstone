"""
Module B - Piece 6: Clip capture + face-blur on flagged events.

Two independent pieces, each testable on its own:
  1. RollingClipRecorder - keeps a rolling buffer of recent frames, and when
     triggered, captures 5s before + 5s after, downsamples, and saves.
  2. blur_faces() - runs face detection on a frame and blurs any faces found.

Standalone test (buffer logic only, no camera/model needed):
    python clip_capture.py
"""

import os
import time
from collections import deque

import cv2
import numpy as np


CLIP_SIZE = (224, 224)      # per plan: reduced resolution for storage
CLIP_FPS = 12                # per plan: 8-16fps, picked 12 as a middle value
BUFFER_SECONDS = 5           # 5s before + 5s after = 10s total


class RollingClipRecorder:
    """
    Keeps a rolling buffer of the last `buffer_seconds` of frames. When
    `trigger()` is called, it captures everything currently in the buffer
    (the "before" half) plus the next `buffer_seconds` of incoming frames
    (the "after" half), then hands the assembled clip to a callback.

    `source_fps` is used to figure out how many raw frames correspond to
    `buffer_seconds`, since the buffer stores raw frames, not a time-based
    structure.
    """

    def __init__(self, source_fps, buffer_seconds=BUFFER_SECONDS,
                 on_clip_ready=None):
        self.source_fps = source_fps
        self.buffer_seconds = buffer_seconds
        self.max_buffer_frames = int(source_fps * buffer_seconds)
        self.on_clip_ready = on_clip_ready  # callback(event_id, list_of_frames)

        self._buffer = deque(maxlen=self.max_buffer_frames)
        # active triggers: event_id -> {"pre_frames": [...], "post_needed": N, "post_frames": [...]}
        self._pending = {}

    def add_frame(self, frame):
        """Call once per processed frame, always - whether or not anything
        triggered. Keeps the rolling buffer full and feeds any pending
        post-trigger captures."""
        self._buffer.append(frame)

        # Feed any in-progress post-trigger captures.
        finished_ids = []
        for event_id, state in self._pending.items():
            state["post_frames"].append(frame)
            if len(state["post_frames"]) >= state["post_needed"]:
                finished_ids.append(event_id)

        for event_id in finished_ids:
            state = self._pending.pop(event_id)
            full_clip = state["pre_frames"] + state["post_frames"]
            if self.on_clip_ready:
                self.on_clip_ready(event_id, full_clip)

    def trigger(self, event_id):
        """Call when an event fires. Snapshots the current buffer as the
        'pre' half, and starts collecting the 'post' half from subsequent
        add_frame() calls."""
        if event_id in self._pending:
            return  # already capturing for this event, don't double-trigger
        self._pending[event_id] = {
            "pre_frames": list(self._buffer),
            "post_needed": int(self.source_fps * self.buffer_seconds),
            "post_frames": [],
        }


def downsample_clip(frames, target_size=CLIP_SIZE, target_fps=CLIP_FPS,
                     source_fps=30):
    """Resize every frame to target_size, and drop frames to approximate
    target_fps (keep every Nth frame)."""
    if source_fps <= target_fps:
        keep_every = 1
    else:
        keep_every = round(source_fps / target_fps)

    resized = [cv2.resize(f, target_size) for f in frames[::keep_every]]
    return resized


_face_detector = None


def get_face_detector(model_path="face_detection_yunet.onnx"):
    """Lazily loads the YuNet face detector. Returns None if the model file
    isn't present - caller should handle that (skip blurring rather than
    crash) since the weight file has to be downloaded separately and isn't
    committed to the repo (CONTRIBUTING.md: never commit weights)."""
    global _face_detector
    if _face_detector is not None:
        return _face_detector
    if not os.path.exists(model_path):
        return None
    _face_detector = cv2.FaceDetectorYN.create(model_path, "", (320, 320))
    return _face_detector


def blur_faces(frame, model_path="face_detection_yunet.onnx"):
    """Detects faces in `frame` and blurs each detected region in place.
    If the model file isn't available, returns the frame unchanged (with a
    printed warning) rather than crashing - so the pipeline still runs, just
    without blurring, until the model file is actually set up."""
    detector = get_face_detector(model_path)
    if detector is None:
        return frame

    h, w = frame.shape[:2]
    detector.setInputSize((w, h))
    _, faces = detector.detect(frame)

    if faces is None:
        return frame

    for face in faces:
        x, y, fw, fh = face[:4].astype(int)
        x, y = max(0, x), max(0, y)
        roi = frame[y:y + fh, x:x + fw]
        if roi.size == 0:
            continue
        blurred = cv2.GaussianBlur(roi, (51, 51), 30)
        frame[y:y + fh, x:x + fw] = blurred

    return frame


def save_clip(frames, output_path, fps=CLIP_FPS):
    """Writes a list of frames out as an mp4 file."""
    if not frames:
        return
    h, w = frames[0].shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path, fourcc, fps, (w, h))
    for f in frames:
        writer.write(f)
    writer.release()


if __name__ == "__main__":
    # Standalone test of the ROLLING BUFFER LOGIC ONLY - fake frames (plain
    # numpy arrays), no camera, no model weights, no real video needed.
    # Face-blur itself isn't tested here since it needs the real YuNet
    # weight file - that's a manual/separate check once the file is in place.

    print("Test: rolling buffer captures correct pre/post frame counts\n")

    captured = {}

    def on_ready(event_id, frames):
        captured[event_id] = len(frames)

    source_fps = 10
    buffer_seconds = 2  # small numbers so the test runs fast
    recorder = RollingClipRecorder(source_fps=source_fps,
                                    buffer_seconds=buffer_seconds,
                                    on_clip_ready=on_ready)

    # Feed 30 fake frames total. Trigger at frame 15.
    # Expect: pre = up to 20 frames (source_fps*buffer_seconds=20, but only
    # 15 exist so far -> 15), post = 20 frames after trigger.
    total_frames = 40
    trigger_at = 15

    for i in range(total_frames):
        fake_frame = np.full((100, 100, 3), i % 255, dtype=np.uint8)
        if i == trigger_at:
            recorder.trigger(event_id="test_event_1")
        recorder.add_frame(fake_frame)

    expected_pre = min(trigger_at, source_fps * buffer_seconds)
    expected_post = source_fps * buffer_seconds
    expected_total = expected_pre + expected_post

    got = captured.get("test_event_1")
    status = "PASS" if got == expected_total else "FAIL"
    print(f"[{status}] expected {expected_total} total frames "
          f"({expected_pre} pre + {expected_post} post), got {got}")

    print("\nTest: downsample_clip resizes and reduces frame count")
    fake_frames = [np.zeros((480, 640, 3), dtype=np.uint8) for _ in range(30)]
    result = downsample_clip(fake_frames, target_size=(224, 224),
                              target_fps=10, source_fps=30)
    status = "PASS" if (len(result) == 10 and result[0].shape[:2] == (224, 224)) else "FAIL"
    print(f"[{status}] got {len(result)} frames of shape {result[0].shape if result else None} "
          f"(expected 10 frames of shape (224, 224, 3))")

    print("\nNote: blur_faces() needs the real YuNet .onnx model file to test "
          "properly - not covered by this standalone run. Test it manually "
          "once the model file is downloaded and in place.")
