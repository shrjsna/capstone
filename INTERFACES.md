# INTERFACES.md — Shared System JSON Schemas

This document specifies the exact JSON schemas for communication between edge detection modules, the cloud backend, the human operator dashboard, and the decision layer.

---

## 1. Detection Event Schema (Module A/B -> Module D)
Emitted by edge detection modules (`infer.py`) upon detecting a safety violation.

```json
{
  "camera_id": "string",
  "zone_id": "string",
  "event_type": "ppe_violation | zone_intrusion",
  "class": "string",
  "confidence": 0.95,
  "tracked_id": "string",
  "timestamp": "2026-09-20T12:00:00Z",
  "frame_count_triggered": 12,
  "clip_captured": true
}
```

*Note: Server assigns a unique `event_id` (UUID string) upon receipt.*

---

## 2. Operator Feedback Schema (Dashboard -> Module D -> Module C)
Emitted when a human safety officer confirms or refutes an alert.

```json
{
  "event_id": "string (UUID)",
  "feedback": "confirmed | false_alarm",
  "operator_id": "string",
  "timestamp": "2026-09-20T12:01:30Z"
}
```

---

## 3. Bandit Decision Output Schema (Module C -> Module D)
Emitted by the decision layer when evaluating a detection event.

```json
{
  "event_id": "string (UUID)",
  "action": "escalate | log_only | adjust_threshold",
  "policy_version": "v1.2.0",
  "threshold_used": 0.75
}
```

---

## 4. Policy Update Record Schema (Module D / FL -> System)
Tracks federated or local policy weight training and validation history.

```json
{
  "policy_version": "v1.2.0",
  "trained_at": "2026-09-20T10:00:00Z",
  "validation_score": 0.92,
  "previous_version": "v1.1.0",
  "deployed": true
}
```
