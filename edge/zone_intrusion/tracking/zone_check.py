"""
Module B - Piece 3: Zone-check logic.

Loads a zone config (polygon) and tells you whether a given point is inside it.
This file can be tested completely standalone - no camera, no model, no video
needed - just fake coordinates.

Usage (standalone test):
    python zone_check.py
"""

import json


def load_zone_config(path):
    """Load a zone config JSON file. Returns the parsed dict."""
    with open(path, "r") as f:
        return json.load(f)


def get_foot_point(box):
    """
    Given a bounding box (x1, y1, x2, y2), return the foot-point:
    bottom-center of the box. This is more accurate than the box's centroid
    for deciding whether someone is "standing" inside a zone, since a
    person's feet - not their torso/head - determine their actual floor
    position.
    """
    x1, y1, x2, y2 = box
    foot_x = (x1 + x2) / 2
    foot_y = y2
    return (foot_x, foot_y)


def point_in_polygon(point, polygon):
    """
    Ray-casting algorithm: returns True if `point` (x, y) is inside `polygon`
    (a list of [x, y] vertex pairs), False otherwise.

    This works by drawing an imaginary horizontal ray from the point out to
    infinity (to the right) and counting how many polygon edges it crosses.
    Odd number of crossings = inside, even = outside.
    """
    x, y = point
    n = len(polygon)
    inside = False

    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]

        # Does the edge (xi,yi)-(xj,yj) straddle the horizontal line at y?
        intersects = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / (yj - yi) + xi
        )
        if intersects:
            inside = not inside
        j = i

    return inside


def check_box_in_zone(box, zone_config):
    """
    Convenience wrapper: given a bounding box and a loaded zone config,
    returns True if that box's foot-point is inside the zone's polygon.
    """
    foot_point = get_foot_point(box)
    return point_in_polygon(foot_point, zone_config["polygon"])


if __name__ == "__main__":
    # Standalone test - no camera/model needed, just fake data.
    zone = load_zone_config("../zones/camera_01_zones.json")
    print(f"Loaded zone: {zone['zone_id']} on {zone['camera_id']}")
    print(f"Polygon: {zone['polygon']}\n")

    # A handful of test cases: (description, fake bounding box, expected result)
    test_cases = [
        ("Person standing well inside the zone",      (800, 300, 900, 500), True),
        ("Person standing well outside the zone",     (100, 300, 200, 500), False),
        ("Person just inside the left edge",          (760, 300, 800, 500), True),
        ("Person just outside the left edge",         (600, 300, 740, 500), False),
        ("Person near the bottom of the zone",        (800, 800, 900, 990), True),
    ]

    print("Running test cases:\n")
    all_passed = True
    for description, box, expected in test_cases:
        result = check_box_in_zone(box, zone)
        status = "PASS" if result == expected else "FAIL"
        if result != expected:
            all_passed = False
        foot = get_foot_point(box)
        print(f"[{status}] {description}")
        print(f"       box={box}  foot_point={foot}  "
              f"got={result}  expected={expected}\n")

    print("ALL TESTS PASSED" if all_passed else "SOME TESTS FAILED - check above")
