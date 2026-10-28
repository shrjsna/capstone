"""
Cloud Backend — FastAPI Application
=====================================
Industrial Safety Monitoring System: event ingestion, bandit decision layer,
operator feedback loop, policy retrain / rollback, and dashboard alert feed.

Design decisions documented in docs/decisions.md.

Endpoints
---------
POST /events            — Receive detection event from edge; return bandit decision.
POST /feedback          — Receive operator feedback; update bandit online.
GET  /alerts            — List alert records for the dashboard.
GET  /alerts/{event_id} — Get a single alert record.
GET  /policy            — Current active policy info.
POST /retrain           — Trigger batch retrain on acknowledged feedback history.
POST /rollback          — Roll back to previous policy version.
GET  /health            — Liveness probe.
"""

from __future__ import annotations

import datetime
import logging
from collections import OrderedDict
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from cloud.backend.models import (
    AlertRecord,
    BanditDecision,
    DetectionEvent,
    OperatorFeedback,
    PolicyUpdateRecord,
    RetrainRequest,
)
from cloud.decision_layer.bandit import ContextualBandit
from cloud.decision_layer.train_baseline import train_offline_baseline

# ──────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("safety_backend")

# ──────────────────────────────────────────────────────────────────
# Application-level state
# ──────────────────────────────────────────────────────────────────

# Global bandit instance — initialised at startup via lifespan
bandit: ContextualBandit = None  # type: ignore[assignment]

# In-memory alert store: OrderedDict preserves insertion order for the dashboard.
# Key = event_id, Value = AlertRecord.
# Capped at MAX_ALERTS entries (oldest evicted) to prevent unbounded growth.
MAX_ALERTS = 5_000
alerts: OrderedDict[str, AlertRecord] = OrderedDict()

# Acknowledged (feedback received) batch stored for periodic retraining.
# Each entry: (event_dict, action, feedback_str)
feedback_history: list = []


# ──────────────────────────────────────────────────────────────────
# Lifespan — startup and shutdown
# ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Bootstrap the bandit with the offline-trained baseline policy at startup."""
    global bandit
    logger.info("Starting up: training offline baseline policy …")
    try:
        record = train_offline_baseline()
        bandit = ContextualBandit(
            strategy="linucb",
            policy_version=record["policy_version"],
        )
        logger.info(
            "Bandit ready. policy_version=%s  validation_score=%.2f",
            record["policy_version"],
            record["validation_score"],
        )
    except Exception as exc:
        logger.error("Baseline training failed, falling back to cold-start bandit: %s", exc)
        bandit = ContextualBandit(strategy="linucb", policy_version="policy_v0")

    yield  # application runs here

    logger.info("Shutting down.")


# ──────────────────────────────────────────────────────────────────
# FastAPI application
# ──────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Industrial Safety Monitoring — Cloud Backend",
    description=(
        "Cloud-side REST API for the Edge-Cloud AI safety system. "
        "Receives detection events from Jetson Nano edge devices, routes them through "
        "the Contextual Bandit decision layer, and exposes an operator feedback loop "
        "for adaptive online learning."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Allow the dashboard (served separately) to call this API from a browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────────────────────────
# Helper
# ──────────────────────────────────────────────────────────────────

def _evict_oldest_alert() -> None:
    """Remove the oldest alert when the in-memory store is full."""
    if len(alerts) >= MAX_ALERTS:
        alerts.popitem(last=False)


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ──────────────────────────────────────────────────────────────────
# POST /events — Detection event ingestion
# ──────────────────────────────────────────────────────────────────

@app.post(
    "/events",
    response_model=BanditDecision,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest detection event and receive bandit decision",
    tags=["Events"],
)
def post_event(event: DetectionEvent) -> BanditDecision:
    """
    Receive a detection event from an edge camera, feed it to the
    Contextual Bandit, store the alert record, and return the decision.

    The returned `action` tells the edge/dashboard what to do:
    - **escalate** → trigger immediate operator alarm
    - **log_only** → quietly write to database, no alarm
    - **adjust_threshold** → tune camera detection sensitivity
    """
    # Build plain dict matching extract_features() field names
    event_dict = {
        "camera_id": event.camera_id,
        "zone_id": event.zone_id,
        "event_type": event.event_type,
        "class": event.class_name,
        "confidence": event.confidence,
        "frame_count_triggered": event.frame_count_triggered,
        "clip_captured": event.clip_captured,
        "timestamp": event.timestamp or _now_iso(),
    }

    try:
        decision = bandit.predict(event_dict, event_id=event.event_id or None)
    except ValueError as exc:
        # Duplicate event_id — inform caller
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    # Store enriched alert record for the dashboard
    _evict_oldest_alert()
    alerts[decision["event_id"]] = AlertRecord(
        event_id=decision["event_id"],
        camera_id=event.camera_id,
        zone_id=event.zone_id,
        event_type=event.event_type,
        class_name=event.class_name,
        confidence=event.confidence,
        tracked_id=event.tracked_id,
        timestamp=event_dict["timestamp"],
        clip_captured=event.clip_captured,
        action=decision["action"],
        policy_version=decision["policy_version"],
        threshold_used=decision["threshold_used"],
    )

    logger.info(
        "Event %s → action=%s  conf=%.2f  cam=%s",
        decision["event_id"],
        decision["action"],
        event.confidence,
        event.camera_id,
    )

    return BanditDecision(**decision)


# ──────────────────────────────────────────────────────────────────
# POST /feedback — Operator feedback ingestion
# ──────────────────────────────────────────────────────────────────

@app.post(
    "/feedback",
    status_code=status.HTTP_200_OK,
    summary="Submit operator feedback for a pending alert",
    tags=["Feedback"],
)
def post_feedback(feedback: OperatorFeedback) -> dict:
    """
    Receive operator feedback (confirmed / false_alarm) for a previous decision.
    Triggers an immediate online update of the Contextual Bandit weights.

    Returns `{"updated": true}` on success, `{"updated": false}` if the event_id
    is unknown (e.g., already acknowledged or never issued).
    """
    updated = bandit.update(feedback.event_id, feedback.feedback)

    if not updated:
        # event_id not in pending_events — either already processed or never seen
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"event_id '{feedback.event_id}' not found in pending decisions. "
                "It may have already been acknowledged or was never issued by this backend."
            ),
        )

    # Mark alert as acknowledged in the in-memory store
    if feedback.event_id in alerts:
        rec = alerts[feedback.event_id]
        rec.feedback = feedback.feedback
        rec.operator_id = feedback.operator_id
        rec.feedback_timestamp = feedback.timestamp or _now_iso()
        rec.status = "acknowledged"

    # Accumulate for batch retraining
    if feedback.event_id in alerts:
        rec = alerts[feedback.event_id]
        feedback_history.append(
            (
                {
                    "event_type": rec.event_type,
                    "class": rec.class_name,
                    "confidence": rec.confidence,
                    "camera_id": rec.camera_id,
                    "zone_id": rec.zone_id,
                    "timestamp": rec.timestamp,
                },
                rec.action,
                feedback.feedback,
            )
        )

    logger.info(
        "Feedback %s → %s  (operator=%s)",
        feedback.event_id,
        feedback.feedback,
        feedback.operator_id,
    )

    return {"updated": True, "event_id": feedback.event_id, "feedback": feedback.feedback}


# ──────────────────────────────────────────────────────────────────
# GET /alerts — Dashboard alert feed
# ──────────────────────────────────────────────────────────────────

@app.get(
    "/alerts",
    response_model=List[AlertRecord],
    summary="List all alert records (newest first)",
    tags=["Dashboard"],
)
def get_alerts(
    status_filter: Optional[str] = None,
    limit: int = 100,
) -> List[AlertRecord]:
    """
    Return the most recent alert records for the operator dashboard.

    Query parameters:
    - **status_filter**: `pending` | `acknowledged` (omit for all)
    - **limit**: max records to return (default 100, max 1000)
    """
    limit = min(limit, 1_000)
    records = list(reversed(list(alerts.values())))   # newest first

    if status_filter in ("pending", "acknowledged"):
        records = [r for r in records if r.status == status_filter]

    return records[:limit]


@app.get(
    "/alerts/{event_id}",
    response_model=AlertRecord,
    summary="Get a single alert record by event_id",
    tags=["Dashboard"],
)
def get_alert(event_id: str) -> AlertRecord:
    """Return the full alert record for a specific event_id."""
    if event_id not in alerts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert '{event_id}' not found.",
        )
    return alerts[event_id]


# ──────────────────────────────────────────────────────────────────
# GET /policy — Current policy information
# ──────────────────────────────────────────────────────────────────

@app.get(
    "/policy",
    summary="Get current active policy metadata",
    tags=["Policy"],
)
def get_policy() -> dict:
    """Return current policy version, strategy, and pending-feedback queue size."""
    return {
        "policy_version": bandit.policy_version,
        "previous_version": bandit.previous_version,
        "strategy": bandit.strategy,
        "pending_decisions": len(bandit.pending_events),
        "feedback_history_size": len(feedback_history),
        "alert_store_size": len(alerts),
    }


# ──────────────────────────────────────────────────────────────────
# POST /retrain — Batch retrain
# ──────────────────────────────────────────────────────────────────

@app.post(
    "/retrain",
    response_model=PolicyUpdateRecord,
    summary="Trigger batch retrain using accumulated operator feedback",
    tags=["Policy"],
)
def post_retrain(body: RetrainRequest = RetrainRequest()) -> PolicyUpdateRecord:
    """
    Train a candidate policy on all accumulated operator feedback, run the
    validation gate, and deploy if the score meets `min_validation_score`.

    The full feedback history is used as the training batch; the backend
    automatically holds out the last 20% as the validation set.

    If the gate fails, the existing policy remains active and `deployed` will
    be `false` in the response.
    """
    if len(feedback_history) < 5:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Not enough feedback to retrain: {len(feedback_history)} records. "
                "Need at least 5. Collect more operator feedback first."
            ),
        )

    record = bandit.retrain(
        training_batch=feedback_history,
        min_validation_score=body.min_validation_score,
    )

    logger.info(
        "Retrain complete: version=%s  score=%.2f  deployed=%s",
        record["policy_version"],
        record["validation_score"],
        record["deployed"],
    )

    return PolicyUpdateRecord(**record)


# ──────────────────────────────────────────────────────────────────
# POST /rollback — Policy rollback
# ──────────────────────────────────────────────────────────────────

@app.post(
    "/rollback",
    summary="Roll back to the previous policy version",
    tags=["Policy"],
)
def post_rollback() -> dict:
    """
    Immediately roll back the active Contextual Bandit weights to the
    previous policy version. Useful if a newly deployed policy shows
    degraded real-world performance.
    """
    restored_version = bandit.rollback()
    logger.warning("Policy rolled back to: %s", restored_version)
    return {
        "rolled_back_to": restored_version,
        "message": f"Active policy is now {restored_version}.",
    }


# ──────────────────────────────────────────────────────────────────
# GET /health — Liveness probe
# ──────────────────────────────────────────────────────────────────

@app.get(
    "/health",
    summary="Backend liveness probe",
    tags=["System"],
)
def health() -> dict:
    """Simple health check for load balancers and CI pipelines."""
    return {
        "status": "ok",
        "policy_version": bandit.policy_version if bandit else "not_initialised",
        "timestamp": _now_iso(),
    }
