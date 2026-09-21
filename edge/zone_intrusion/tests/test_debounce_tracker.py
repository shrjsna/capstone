"""
Tests for debounce_tracker.py - fires only after N consecutive in-zone
frames, resets on absence, handles multiple tracks independently.
No camera/model/GPU needed - pure logic tests with fake True/False sequences.

Run with: pytest test_debounce_tracker.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tracking"))

from debounce_tracker import DebounceTracker


def run_sequence(tracker, track_id, cls, sequence):
    """Feed a sequence of True/False flags, return list of frame indices
    where the tracker fired."""
    fired = []
    for i, flag in enumerate(sequence):
        if tracker.update(track_id=track_id, cls=cls, is_in_zone=flag):
            fired.append(i)
    return fired


def test_fires_after_required_consecutive_frames():
    tracker = DebounceTracker(required_frames=4)
    sequence = [False, False, True, True, True, True, True, True]
    fired = run_sequence(tracker, 1, "person", sequence)
    assert fired == [5]  # 4th consecutive True lands on index 5


def test_never_fires_on_boundary_flicker():
    tracker = DebounceTracker(required_frames=4)
    sequence = [True, True, False, True, True, True, False, True, True]
    fired = run_sequence(tracker, 2, "person", sequence)
    assert fired == []


def test_fires_only_once_while_sustained():
    tracker = DebounceTracker(required_frames=3)
    sequence = [True, True, True, True, True, True]
    fired = run_sequence(tracker, 3, "person", sequence)
    assert fired == [2]


def test_refires_on_reentry():
    tracker = DebounceTracker(required_frames=3)
    sequence = [True, True, True, False, False, True, True, True]
    fired = run_sequence(tracker, 4, "person", sequence)
    assert fired == [2, 7]


def test_tracks_are_independent():
    tracker = DebounceTracker(required_frames=3)
    fired_5, fired_6 = [], []
    for i in range(5):
        if tracker.update(track_id=5, cls="person", is_in_zone=True):
            fired_5.append(i)
        if tracker.update(track_id=6, cls="person", is_in_zone=False):
            fired_6.append(i)
    assert fired_5 == [2]
    assert fired_6 == []


def test_empty_sequence_never_fires():
    tracker = DebounceTracker(required_frames=3)
    fired = run_sequence(tracker, 7, "person", [])
    assert fired == []


def test_remove_track_clears_state():
    tracker = DebounceTracker(required_frames=3)
    tracker.update(track_id=8, cls="person", is_in_zone=True)
    tracker.update(track_id=8, cls="person", is_in_zone=True)
    tracker.remove_track(8, "person")
    # After removal, streak should restart from 0, so it takes another
    # full `required_frames` to fire again.
    sequence = [True, True, True]
    fired = run_sequence(tracker, 8, "person", sequence)
    assert fired == [2]
