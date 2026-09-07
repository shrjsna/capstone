"""
test_ppe_detection.py

Unit and regression test suite for Module A (PPE Detection).
Exercises prepare_dataset.py's label remapping, infer.py's event construction,
and DebounceTracker's multi-frame state machine in isolation.

These tests run in CI on CPU-only runners in < 2 seconds, with zero GPU,
video stream, or model weights dependencies.
"""

from datetime import datetime
import json
from pathlib import Path
import re
import tempfile
import pytest

from edge.ppe_detection.data.prepare_dataset import (
    CLASS_TO_ID,
    DATASET1_MAP,
    DATASET2_MAP,
    DATASET3_MAP,
    DATASET4_MAP,
    UNIFIED_CLASSES,
    remap_label_file,
    remap_label_line,
)
from edge.ppe_detection.infer import (
    DebounceTracker,
    PPE_VIOLATION_CLASSES,
    build_event,
    log_event,
)

INTERFACES_EVENT_SCHEMA_KEYS = {
    "camera_id",
    "zone_id",
    "event_type",
    "class",
    "confidence",
    "tracked_id",
    "timestamp",
    "frame_count_triggered",
    "clip_captured",
}


# ==============================================================================
# 1. Label Remapping Tests (prepare_dataset.py)
# ==============================================================================


def test_unified_class_definitions():
    """Verify the 16 unified classes and bijective ID mappings."""
    assert len(UNIFIED_CLASSES) == 16
    assert len(CLASS_TO_ID) == 16
    for idx, name in enumerate(UNIFIED_CLASSES):
        assert CLASS_TO_ID[name] == idx


def test_dataset1_roboflow_remapping():
    """Verify Dataset 1 mapping (e.g. NO-Hardhat -> no_helmet, etc.)."""
    # old 2 is NO-Hardhat -> no_helmet (unified class id 1)
    line = "2 0.5 0.5 0.2 0.2"
    remapped = remap_label_line(line, DATASET1_MAP)
    assert remapped == "1 0.5 0.5 0.2 0.2"

    # old 0 is Hardhat -> helmet (unified class id 0)
    line_helmet = "0 0.1 0.2 0.3 0.4"
    assert remap_label_line(line_helmet, DATASET1_MAP) == "0 0.1 0.2 0.3 0.4"


def test_dataset2_ultralytics_remapping_and_dropped_class():
    """Verify Dataset 2 mapping, specifically that old_id 5 ('none') is dropped."""
    # old 7 is no_helmet -> unified id 1
    assert remap_label_line("7 0.4 0.4 0.1 0.1", DATASET2_MAP) == "1 0.4 0.4 0.1 0.1"
    # old 10 is no_boots -> unified id 7
    assert remap_label_line("10 0.3 0.3 0.1 0.1", DATASET2_MAP) == "7 0.3 0.3 0.1 0.1"
    # old 5 is 'none' catch-all -> dropped (returns None)
    assert remap_label_line("5 0.2 0.2 0.1 0.1", DATASET2_MAP) is None


def test_dataset3_pk_remapping_case_variants():
    """Verify Dataset 3 maps case-variant dupes to identical unified classes."""
    # old 0 is 'Hardhat', old 11 is lowercase 'hardhat' -> both map to helmet (id 0)
    assert remap_label_line("0 0.1 0.1 0.1 0.1", DATASET3_MAP) == "0 0.1 0.1 0.1 0.1"
    assert remap_label_line("11 0.1 0.1 0.1 0.1", DATASET3_MAP) == "0 0.1 0.1 0.1 0.1"
    # old 19 is 'shoes' -> boots (unified id 6)
    assert remap_label_line("19 0.5 0.5 0.1 0.1", DATASET3_MAP) == "6 0.5 0.5 0.1 0.1"


def test_dataset4_keremberke_hf_remapping():
    """Verify Dataset 4 maps keremberke HF classes correctly."""
    # old 5 is no_goggles -> unified id 9
    assert remap_label_line("5 0.5 0.5 0.2 0.2", DATASET4_MAP) == "9 0.5 0.5 0.2 0.2"
    # old 8 is no_shoes -> no_boots (unified id 7)
    assert remap_label_line("8 0.5 0.5 0.2 0.2", DATASET4_MAP) == "7 0.5 0.5 0.2 0.2"


def test_remap_label_file_integration(tmp_path: Path):
    """Test full file remapping with multiple lines and dropped classes."""
    src = tmp_path / "sample_src.txt"
    dst = tmp_path / "sample_dst.txt"
    src.write_text("7 0.1 0.1 0.2 0.2\n5 0.9 0.9 0.1 0.1\n0 0.3 0.3 0.1 0.1\n")

    remap_label_file(src, dst, DATASET2_MAP)
    assert dst.exists()
    out_lines = dst.read_text().strip().splitlines()
    assert len(out_lines) == 2  # class 5 was dropped
    assert out_lines[0] == "1 0.1 0.1 0.2 0.2"  # old 7 -> no_helmet (1)
    assert out_lines[1] == "0 0.3 0.3 0.1 0.1"  # old 0 -> helmet (0)


# ==============================================================================
# 2. Schema Compliance Tests (build_event)
# ==============================================================================


def test_build_event_schema_and_serialization():
    """Verify build_event produces exact INTERFACES.md schema with serializable types."""
    event = build_event(
        camera_id="cam_01",
        zone_id="zone_A",
        event_type="ppe_violation",
        class_name="no_helmet",
        confidence=0.87321,
        tracked_id="person_142",
        timestamp="2026-09-05T14:32:10Z",
        frame_count_triggered=4,
        clip_captured=True,
    )

    # 1. Exact key match (no extra, no missing)
    assert set(event.keys()) == INTERFACES_EVENT_SCHEMA_KEYS
    assert len(event) == len(INTERFACES_EVENT_SCHEMA_KEYS)

    # 2. Exact types
    assert isinstance(event["camera_id"], str)
    assert isinstance(event["zone_id"], str)
    assert isinstance(event["event_type"], str)
    assert isinstance(event["class"], str)
    assert isinstance(event["confidence"], float)
    assert isinstance(event["tracked_id"], str)
    assert isinstance(event["timestamp"], str)
    assert isinstance(event["frame_count_triggered"], int)
    assert isinstance(event["clip_captured"], bool)

    # 3. Values and precision
    assert event["event_type"] == "ppe_violation"
    assert event["class"] == "no_helmet"
    assert event["confidence"] == 0.8732
    assert event["frame_count_triggered"] == 4
    assert event["clip_captured"] is True

    # 4. Valid ISO8601 UTC timestamp format
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", event["timestamp"])

    # 5. JSON serialization round-trip
    dumped = json.dumps(event)
    reloaded = json.loads(dumped)
    assert reloaded == event


def test_build_event_handles_numeric_types():
    """Verify build_event safely handles non-standard numerics (e.g. float/int conversion)."""
    event = build_event(
        camera_id=1,  # passed as int
        zone_id="zone_B",
        event_type="ppe_violation",
        class_name="no_vest",
        confidence="0.95",  # passed as str
        tracked_id=42,  # passed as int
        timestamp="2026-09-05T15:00:00Z",
        frame_count_triggered="3",  # passed as str
        clip_captured=0,  # passed as int
    )
    assert event["camera_id"] == "1"
    assert event["tracked_id"] == "42"
    assert isinstance(event["confidence"], float)
    assert event["confidence"] == 0.95
    assert isinstance(event["frame_count_triggered"], int)
    assert event["frame_count_triggered"] == 3
    assert isinstance(event["clip_captured"], bool)
    assert event["clip_captured"] is False

    # Check json.dumps succeeds
    assert json.dumps(event)


def test_log_event_file_output(tmp_path: Path):
    """Test log_event appends valid JSON lines to disk."""
    log_file = tmp_path / "test_events.jsonl"
    event = build_event("cam_01", "zone_A", "ppe_violation", "no_mask", 0.91, "person_10", "2026-09-05T12:00:00Z", 3)
    log_event(event, log_file)
    log_event(event, log_file)

    lines = log_file.read_text().strip().splitlines()
    assert len(lines) == 2
    for line in lines:
        parsed = json.loads(line)
        assert parsed["class"] == "no_mask"


# ==============================================================================
# 3. DebounceTracker State Machine & Edge Cases
# ==============================================================================


def test_debounce_threshold_gating_and_no_refire():
    """Event fires only at threshold frames, and suppresses subsequent continuous frames."""
    tracker = DebounceTracker(debounce_threshold=3)

    det = [{"track_id": "person_1", "class_name": "no_helmet", "confidence": 0.85}]

    # Frame 1: count = 1 -> No event
    events = tracker.update(det)
    assert len(events) == 0

    # Frame 2: count = 2 -> No event
    events = tracker.update(det)
    assert len(events) == 0

    # Frame 3: count = 3 -> Event fires!
    events = tracker.update(det)
    assert len(events) == 1
    assert events[0]["track_id"] == "person_1"
    assert events[0]["class_name"] == "no_helmet"
    assert events[0]["frame_count"] == 3
    assert events[0]["confidence"] == 0.85

    # Frames 4 & 5: count increases, but violation is already fired -> No re-fire
    assert len(tracker.update(det)) == 0
    assert len(tracker.update(det)) == 0


def test_debounce_reset_when_class_disappears():
    """When a violation class disappears for a frame, count resets and can fire again."""
    tracker = DebounceTracker(debounce_threshold=3)
    det_violation = [{"track_id": "person_1", "class_name": "no_helmet", "confidence": 0.9}]

    # Frames 1-3: reach threshold and fire
    tracker.update(det_violation)
    tracker.update(det_violation)
    fired = tracker.update(det_violation)
    assert len(fired) == 1

    # Frame 4: Person puts on helmet -> no violation detected this frame
    tracker.update([])

    # Frame 5: Person takes off helmet again -> count should start at 1, NOT 4!
    events = tracker.update(det_violation)
    assert len(events) == 0

    # Frame 6: count = 2 -> No event
    assert len(tracker.update(det_violation)) == 0

    # Frame 7: count = 3 -> Re-fires properly!
    re_fired = tracker.update(det_violation)
    assert len(re_fired) == 1
    assert re_fired[0]["frame_count"] == 3


def test_debounce_id_reuse_leak_prevention():
    """ByteTrack reuses track_id after previous object leaves frame.

    Ensures no stale count or 'already fired' state leaks to the new object.
    """
    tracker = DebounceTracker(debounce_threshold=3)

    # Person A has track_id 10 and triggers violation
    det_a = [{"track_id": 10, "class_name": "no_vest", "confidence": 0.88}]
    tracker.update(det_a)
    tracker.update(det_a)
    fired_a = tracker.update(det_a)
    assert len(fired_a) == 1

    # Person A leaves the frame (track 10 absent for 2 frames)
    tracker.update([])
    tracker.update([])

    # A new Person B enters and ByteTrack assigns reused track_id 10.
    # Person B must NOT be blocked by Person A's fired state, and must NOT inherit count.
    det_b = [{"track_id": 10, "class_name": "no_vest", "confidence": 0.92}]
    # Frame 1 for Person B
    assert len(tracker.update(det_b)) == 0
    # Frame 2 for Person B
    assert len(tracker.update(det_b)) == 0
    # Frame 3 for Person B -> Fires fresh event!
    fired_b = tracker.update(det_b)
    assert len(fired_b) == 1
    assert fired_b[0]["track_id"] == "10"
    assert fired_b[0]["frame_count"] == 3


def test_debounce_multiple_violations_on_same_track():
    """A person missing BOTH helmet and vest at once has both tracked independently."""
    tracker = DebounceTracker(debounce_threshold=3)

    det_both = [
        {"track_id": "worker_1", "class_name": "no_helmet", "confidence": 0.89},
        {"track_id": "worker_1", "class_name": "no_vest", "confidence": 0.94},
    ]

    # Frames 1 and 2
    assert len(tracker.update(det_both)) == 0
    assert len(tracker.update(det_both)) == 0

    # Frame 3: Both reach threshold simultaneously -> BOTH fire!
    events = tracker.update(det_both)
    assert len(events) == 2
    classes_fired = {e["class_name"] for e in events}
    assert classes_fired == {"no_helmet", "no_vest"}

    # Frame 4: Both still present -> neither re-fires
    assert len(tracker.update(det_both)) == 0

    # Frame 5: Worker puts on vest, helmet still missing
    det_helmet_only = [{"track_id": "worker_1", "class_name": "no_helmet", "confidence": 0.89}]
    assert len(tracker.update(det_helmet_only)) == 0

    # Frame 6: Worker takes off vest again -> no_vest count is 1
    assert len(tracker.update(det_both)) == 0
    # Frame 7: no_vest count is 2
    assert len(tracker.update(det_both)) == 0
    # Frame 8: no_vest count is 3 -> no_vest fires again, no_helmet does not!
    events_frame8 = tracker.update(det_both)
    assert len(events_frame8) == 1
    assert events_frame8[0]["class_name"] == "no_vest"


def test_debounce_first_frame_and_none_detections():
    """First frame and empty/None detections (tracker lost) must not throw or false-fire."""
    tracker = DebounceTracker(debounce_threshold=3)

    # Frame 0: None or empty detections
    assert tracker.update(None) == []
    assert tracker.update([]) == []

    # Frame with missing track_id in detection dict
    invalid_det = [{"class_name": "no_helmet", "confidence": 0.8}]
    assert tracker.update(invalid_det) == []


def test_debounce_reset_method():
    """Verify reset() completely purges tracking state."""
    tracker = DebounceTracker(debounce_threshold=2)
    tracker.update([{"track_id": "1", "class_name": "no_helmet", "confidence": 0.8}])
    assert len(tracker.track_states) > 0

    tracker.reset()
    assert len(tracker.track_states) == 0
