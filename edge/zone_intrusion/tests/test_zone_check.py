"""
Tests for zone_check.py - point-in-polygon zone detection.
No camera, model, or GPU needed - pure logic tests with fake coordinates.

Run with: pytest test_zone_check.py -v
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tracking"))

from zone_check import point_in_polygon, get_foot_point, check_box_in_zone


SAMPLE_ZONE = {
    "camera_id": "cam_01",
    "zone_id": "zone_red_1",
    "polygon": [[750, 0], [1050, 0], [1050, 1000], [750, 1000]],
}


def test_point_well_inside():
    assert point_in_polygon((900, 500), SAMPLE_ZONE["polygon"]) is True


def test_point_well_outside():
    assert point_in_polygon((100, 500), SAMPLE_ZONE["polygon"]) is False


def test_point_just_inside_left_edge():
    assert point_in_polygon((760, 500), SAMPLE_ZONE["polygon"]) is True


def test_point_just_outside_left_edge():
    assert point_in_polygon((700, 500), SAMPLE_ZONE["polygon"]) is False


def test_get_foot_point_is_bottom_center():
    box = (100, 100, 200, 300)
    assert get_foot_point(box) == (150, 300)


def test_check_box_in_zone_true():
    box = (800, 300, 900, 500)  # foot point (850, 500) - inside
    assert check_box_in_zone(box, SAMPLE_ZONE) is True


def test_check_box_in_zone_false():
    box = (100, 300, 200, 500)  # foot point (150, 500) - outside
    assert check_box_in_zone(box, SAMPLE_ZONE) is False


def test_check_box_partially_overlapping_zone_uses_foot_point():
    # Box spans across the zone boundary, but the FOOT point (bottom-center)
    # is what matters, not the box center or top - this confirms we're not
    # accidentally using centroid logic.
    box = (700, 300, 900, 500)  # center x=800 (inside), foot point (800,500) inside
    assert check_box_in_zone(box, SAMPLE_ZONE) is True

    box2 = (600, 300, 740, 500)  # foot point (670, 500) - outside
    assert check_box_in_zone(box2, SAMPLE_ZONE) is False
