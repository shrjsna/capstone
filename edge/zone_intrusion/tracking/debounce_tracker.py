"""
Module B - Piece 4: Debounce tracker.

Prevents false alarms from single-frame flicker (e.g. a person's foot-point
briefly wobbling across the zone boundary due to detection jitter). Requires
a configurable number of CONSECUTIVE frames of intrusion before actually
firing an event.

Keyed on (track_id, class) so multiple people/classes are tracked independently.

Usage (standalone test):
    python debounce_tracker.py
"""


class DebounceTracker:
    def __init__(self, required_frames=4):
        """
        required_frames: how many consecutive True updates are needed before
        firing. CONTRIBUTING/plan says 3-5, defaulting to 4 (middle of range).
        """
        self.required_frames = required_frames
        # key: (track_id, class) -> current consecutive-True streak count
        self._streaks = {}
        # key: (track_id, class) -> whether we've already fired for this
        # ongoing intrusion (so we don't re-fire every frame once triggered)
        self._fired = {}

    def update(self, track_id, cls, is_in_zone):
        """
        Call this once per frame per tracked person.

        Returns True exactly on the frame the debounce condition is first
        met (i.e. "fire an event now"). Returns False on every other frame,
        including frames where the person is still in the zone but we
        already fired, and frames where they're not in the zone at all.
        """
        key = (track_id, cls)

        if is_in_zone:
            self._streaks[key] = self._streaks.get(key, 0) + 1

            already_fired = self._fired.get(key, False)
            streak_met = self._streaks[key] >= self.required_frames

            if streak_met and not already_fired:
                self._fired[key] = True
                return True
            return False
        else:
            # Person left the zone (or was never in it this frame) - reset
            # everything for this key so a future entry starts fresh.
            self._streaks.pop(key, None)
            self._fired.pop(key, None)
            return False

    def remove_track(self, track_id, cls):
        """
        Call this when a track disappears entirely (person leaves frame),
        so old state doesn't linger forever for IDs that no longer exist.
        """
        key = (track_id, cls)
        self._streaks.pop(key, None)
        self._fired.pop(key, None)


if __name__ == "__main__":
    # Standalone test - fake sequence of True/False intrusion flags, no
    # camera/model/zone-check needed at all.

    print("Test 1: person enters zone and stays (should fire once, on frame 5)")
    tracker = DebounceTracker(required_frames=4)
    sequence = [False, False, True, True, True, True, True, True]
    fired_frames = []
    for i, in_zone in enumerate(sequence):
        fired = tracker.update(track_id=1, cls="person", is_in_zone=in_zone)
        if fired:
            fired_frames.append(i)
    expected = [3]  # 0-indexed: frames 2,3,4,5 are the 4 consecutive Trues -> fires on frame 5? let's check
    print(f"  fired on frames: {fired_frames}")
    print(f"  {'PASS' if fired_frames == [5] else 'CHECK'} (expected to fire once, on frame 5, "
          f"since frames 2-5 are the 4th consecutive True)\n")

    print("Test 2: boundary flicker, never sustains 4 in a row (should never fire)")
    tracker = DebounceTracker(required_frames=4)
    sequence = [True, True, False, True, True, True, False, True, True]
    fired_frames = []
    for i, in_zone in enumerate(sequence):
        fired = tracker.update(track_id=2, cls="person", is_in_zone=in_zone)
        if fired:
            fired_frames.append(i)
    print(f"  fired on frames: {fired_frames}")
    print(f"  {'PASS' if fired_frames == [] else 'FAIL'} (expected: never fires)\n")

    print("Test 3: fires once, then does NOT re-fire every subsequent frame while still inside")
    tracker = DebounceTracker(required_frames=3)
    sequence = [True, True, True, True, True, True]
    fired_frames = []
    for i, in_zone in enumerate(sequence):
        fired = tracker.update(track_id=3, cls="person", is_in_zone=in_zone)
        if fired:
            fired_frames.append(i)
    print(f"  fired on frames: {fired_frames}")
    print(f"  {'PASS' if fired_frames == [2] else 'FAIL'} (expected: fires exactly once, on frame 2)\n")

    print("Test 4: person leaves and re-enters - should fire again on the second entry")
    tracker = DebounceTracker(required_frames=3)
    sequence = [True, True, True, False, False, True, True, True]
    fired_frames = []
    for i, in_zone in enumerate(sequence):
        fired = tracker.update(track_id=4, cls="person", is_in_zone=in_zone)
        if fired:
            fired_frames.append(i)
    print(f"  fired on frames: {fired_frames}")
    print(f"  {'PASS' if fired_frames == [2, 7] else 'FAIL'} (expected: fires on frame 2 AND frame 7)\n")

    print("Test 5: two different people tracked independently, no cross-contamination")
    tracker = DebounceTracker(required_frames=3)
    # person 1 (track_id=5) stays in zone the whole time
    # person 2 (track_id=6) never enters
    fired = {5: [], 6: []}
    for i in range(5):
        f5 = tracker.update(track_id=5, cls="person", is_in_zone=True)
        f6 = tracker.update(track_id=6, cls="person", is_in_zone=False)
        if f5:
            fired[5].append(i)
        if f6:
            fired[6].append(i)
    print(f"  track 5 fired on: {fired[5]}, track 6 fired on: {fired[6]}")
    print(f"  {'PASS' if fired[5] == [2] and fired[6] == [] else 'FAIL'} "
          f"(expected: track 5 fires once on frame 2, track 6 never fires)")
