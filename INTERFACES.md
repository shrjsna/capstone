# Shared Interfaces

This is the contract every module builds against. **Do not change this file
without notifying the other 3 people first** — everyone's code depends on
this shape staying stable.

## 1. Detection Event (edge → cloud)

Emitted by both the PPE module and the zone-intrusion module, in the same
shape, over HTTP POST to the backend's `/events` endpoint.

```json
{
  "camera_id": "cam_01",
  "zone_id": "zone_A",
  "event_type": "ppe_violation",
  "class": "no_helmet",
  "confidence": 0.87,
  "tracked_id": "person_142",
  "timestamp": "2026-09-05T14:32:10Z",
  "frame_count_triggered": 4,
  "clip_captured": true
}
```

Field notes:
- `event_type`: `"ppe_violation"` or `"zone_intrusion"`
- `class`: for PPE — `no_helmet`, `no_vest`, `no_gloves`, etc. For zone —
  `person_in_zone`.
- `frame_count_triggered`: how many consecutive frames confirmed this before
  it was emitted (debounce count, should be >= 3).
- `clip_captured`: whether a 10s (5s before/after) blurred clip was saved for
  this event — only true for events meant for anomaly-model training.

## 2. Operator Feedback (dashboard → cloud)

Emitted when an operator clicks Confirm or False Alarm on an alert.

```json
{
  "event_id": "evt_98213",
  "feedback": "confirmed",
  "operator_id": "op_04",
  "timestamp": "2026-09-05T14:33:02Z"
}
```

- `feedback`: `"confirmed"` or `"false_alarm"`
- This becomes the reward signal for the bandit: confirmed → positive,
  false_alarm → negative.

## 3. Bandit Decision Output (cloud, internal)

What the decision layer returns after processing an event.

```json
{
  "event_id": "evt_98213",
  "action": "escalate",
  "policy_version": "policy_v7",
  "threshold_used": 0.75
}
```

- `action`: `"escalate"`, `"log_only"`, or `"adjust_threshold"`

## 4. Policy Update Record (cloud, for versioning/rollback)

```json
{
  "policy_version": "policy_v8",
  "trained_at": "2026-09-05T18:00:00Z",
  "validation_score": 0.91,
  "previous_version": "policy_v7",
  "deployed": true
}
```

- `deployed`: false if this version failed validation against the held-out
  set and was not pushed live.

## Changes to This File

Add an entry here when the schema changes, so it's easy to see what shifted
between reviews:

```
## 2026-09-05 — Initial schema
```
