"""
demo_inject_events.py
---
Injects two realistic demo events directly into the running backend
(one PPE violation, one zone intrusion) without needing a real camera,
YOLO model, or video file. Use this for the live demo when a GPU/camera
feed is not available.

Usage (with backend already running on port 8000):
    python demo/demo_inject_events.py
    python demo/demo_inject_events.py --api-url http://127.0.0.1:8000

Output: prints the full server response for each event (including bandit decision).
"""

import argparse
import json
import datetime
import sys

try:
    import requests
except ImportError:
    print("ERROR: 'requests' not installed. Run: pip install requests")
    sys.exit(1)


def post_event(api_url: str, payload: dict) -> dict:
    resp = requests.post(f"{api_url}/events", json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser(description="Inject demo events into backend")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000",
                        help="Backend base URL (default: http://127.0.0.1:8000)")
    args = parser.parse_args()
    api_url = args.api_url.rstrip("/")

    now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── Event 1: PPE violation (no_helmet, high confidence) ────────────────
    ppe_event = {
        "camera_id": "cam_01",
        "zone_id": "zone_a",
        "event_type": "ppe_violation",
        "class": "no_helmet",
        "confidence": 0.91,
        "tracked_id": "person_042",
        "timestamp": now,
        "frame_count_triggered": 5,
        "clip_captured": True,
    }

    print("=" * 55)
    print("Injecting Module A — PPE Violation Event")
    print("=" * 55)
    print(f"Payload:\n{json.dumps(ppe_event, indent=2)}\n")
    try:
        ppe_resp = post_event(api_url, ppe_event)
        print(f"Response from backend:\n{json.dumps(ppe_resp, indent=2)}")
        print(f"\n→ Bandit Action : {ppe_resp.get('bandit_action')}")
        print(f"→ Policy Version: {ppe_resp.get('policy_version')}")
        print(f"→ Threshold Used: {ppe_resp.get('threshold_used')}")
        ppe_event_id = ppe_resp["event_id"]
    except Exception as e:
        print(f"ERROR posting PPE event: {e}")
        sys.exit(1)

    # ── Event 2: Zone intrusion (person_in_zone, high confidence) ──────────
    zone_event = {
        "camera_id": "cam_north_01",
        "zone_id": "zone_red_1",
        "event_type": "zone_intrusion",
        "class": "person_in_zone",
        "confidence": 0.87,
        "tracked_id": "person_117",
        "timestamp": now,
        "frame_count_triggered": 6,
        "clip_captured": True,
    }

    print("\n" + "=" * 55)
    print("Injecting Module B — Zone Intrusion Event")
    print("=" * 55)
    print(f"Payload:\n{json.dumps(zone_event, indent=2)}\n")
    try:
        zone_resp = post_event(api_url, zone_event)
        print(f"Response from backend:\n{json.dumps(zone_resp, indent=2)}")
        print(f"\n→ Bandit Action : {zone_resp.get('bandit_action')}")
        print(f"→ Policy Version: {zone_resp.get('policy_version')}")
        print(f"→ Threshold Used: {zone_resp.get('threshold_used')}")
        zone_event_id = zone_resp["event_id"]
    except Exception as e:
        print(f"ERROR posting zone event: {e}")
        sys.exit(1)

    print("\n" + "=" * 55)
    print("Both events injected successfully.")
    print(f"Open http://127.0.0.1:8080 to see them in the dashboard.")
    print(f"\nPPE event ID  : {ppe_event_id}")
    print(f"Zone event ID : {zone_event_id}")
    print("=" * 55)


if __name__ == "__main__":
    main()
