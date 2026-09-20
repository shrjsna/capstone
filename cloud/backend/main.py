"""
cloud/backend/main.py
FastAPI application for Module D Cloud Backend.
"""

import uuid
from typing import List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from cloud.backend.database import get_db, init_db
from cloud.backend.models import EventModel, FeedbackModel, PolicyVersionModel
from cloud.backend.schemas import (
    DetectionEventCreate,
    DetectionEventResponse,
    OperatorFeedbackCreate,
    OperatorFeedbackResponse,
    PolicyUpdateRecord,
)
from cloud.backend.adapter import get_bandit_adapter, BanditAdapter


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables on startup
    init_db()
    # Populate initial seed policy record if empty
    db = next(get_db())
    if not db.query(PolicyVersionModel).first():
        seed_policy = PolicyVersionModel(
            policy_version="v1.0.0-mock",
            trained_at="2026-09-20T10:00:00Z",
            validation_score=0.915,
            previous_version="v0.9.0",
            deployed=True
        )
        db.add(seed_policy)
        db.commit()
    db.close()
    yield


app = FastAPI(
    title="Edge-Cloud Safety System — Cloud Backend API",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for local dashboard development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    """Basic health check endpoint."""
    return {"status": "ok"}


@app.post("/events", response_model=DetectionEventResponse, status_code=status.HTTP_201_CREATED)
def receive_detection_event(
    event: DetectionEventCreate,
    db: Session = Depends(get_db),
    adapter: BanditAdapter = Depends(get_bandit_adapter)
):
    """
    POST /events — Accepts Detection Events from edge modules.
    Assigns a server-side UUID event_id, queries BanditAdapter for action, and persists to DB.
    """
    event_id = str(uuid.uuid4())
    decision = adapter.decide(event, event_id)

    db_event = EventModel(
        event_id=event_id,
        camera_id=event.camera_id,
        zone_id=event.zone_id,
        event_type=event.event_type,
        class_name=event.class_name,
        confidence=event.confidence,
        tracked_id=event.tracked_id,
        timestamp=event.timestamp,
        frame_count_triggered=event.frame_count_triggered,
        clip_captured=event.clip_captured,
        bandit_action=decision.action,
        policy_version=decision.policy_version,
        threshold_used=decision.threshold_used,
    )
    db.add(db_event)
    db.commit()
    db.refresh(db_event)

    return DetectionEventResponse(
        event_id=db_event.event_id,
        camera_id=db_event.camera_id,
        zone_id=db_event.zone_id,
        event_type=db_event.event_type,
        class_name=db_event.class_name,
        confidence=db_event.confidence,
        tracked_id=db_event.tracked_id,
        timestamp=db_event.timestamp,
        frame_count_triggered=db_event.frame_count_triggered,
        clip_captured=db_event.clip_captured,
        bandit_action=db_event.bandit_action,
        policy_version=db_event.policy_version,
        threshold_used=db_event.threshold_used,
    )


@app.post("/feedback", response_model=OperatorFeedbackResponse, status_code=status.HTTP_200_OK)
def submit_operator_feedback(
    feedback: OperatorFeedbackCreate,
    db: Session = Depends(get_db),
    adapter: BanditAdapter = Depends(get_bandit_adapter)
):
    """
    POST /feedback — Accepts Operator Feedback from the dashboard.
    Validates that event_id exists, persists feedback, and forwards reward signal to BanditAdapter.
    """
    # Validate event_id exists
    event_record = db.query(EventModel).filter(EventModel.event_id == feedback.event_id).first()
    if not event_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event ID '{feedback.event_id}' not found."
        )

    # Check if feedback already exists for this event
    existing_feedback = db.query(FeedbackModel).filter(FeedbackModel.event_id == feedback.event_id).first()
    if existing_feedback:
        existing_feedback.feedback = feedback.feedback
        existing_feedback.operator_id = feedback.operator_id
        existing_feedback.timestamp = feedback.timestamp
    else:
        db_feedback = FeedbackModel(
            event_id=feedback.event_id,
            feedback=feedback.feedback,
            operator_id=feedback.operator_id,
            timestamp=feedback.timestamp
        )
        db.add(db_feedback)

    db.commit()

    # Forward reward to adapter
    adapter.submit_feedback(feedback)

    return OperatorFeedbackResponse(
        status="success",
        event_id=feedback.event_id,
        feedback=feedback.feedback,
        operator_id=feedback.operator_id,
        timestamp=feedback.timestamp
    )


@app.get("/alerts", response_model=List[DetectionEventResponse])
def get_alerts(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db)
):
    """
    GET /alerts — Returns recent events for the dashboard's live feed.
    """
    events = (
        db.query(EventModel)
        .order_by(EventModel.timestamp.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [
        DetectionEventResponse(
            event_id=e.event_id,
            camera_id=e.camera_id,
            zone_id=e.zone_id,
            event_type=e.event_type,
            class_name=e.class_name,
            confidence=e.confidence,
            tracked_id=e.tracked_id,
            timestamp=e.timestamp,
            frame_count_triggered=e.frame_count_triggered,
            clip_captured=e.clip_captured,
            bandit_action=e.bandit_action,
            policy_version=e.policy_version,
            threshold_used=e.threshold_used,
        )
        for e in events
    ]


@app.get("/alerts/{event_id}", response_model=DetectionEventResponse)
def get_alert_detail(event_id: str, db: Session = Depends(get_db)):
    """
    GET /alerts/{event_id} — Single alert detail view.
    """
    e = db.query(EventModel).filter(EventModel.event_id == event_id).first()
    if not e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert with ID '{event_id}' not found."
        )

    return DetectionEventResponse(
        event_id=e.event_id,
        camera_id=e.camera_id,
        zone_id=e.zone_id,
        event_type=e.event_type,
        class_name=e.class_name,
        confidence=e.confidence,
        tracked_id=e.tracked_id,
        timestamp=e.timestamp,
        frame_count_triggered=e.frame_count_triggered,
        clip_captured=e.clip_captured,
        bandit_action=e.bandit_action,
        policy_version=e.policy_version,
        threshold_used=e.threshold_used,
    )


@app.get("/policy-history", response_model=List[PolicyUpdateRecord])
def get_policy_history(db: Session = Depends(get_db)):
    """
    GET /policy-history — Returns policy update records.
    """
    records = db.query(PolicyVersionModel).order_by(PolicyVersionModel.trained_at.desc()).all()
    return [
        PolicyUpdateRecord(
            policy_version=r.policy_version,
            trained_at=r.trained_at,
            validation_score=r.validation_score,
            previous_version=r.previous_version,
            deployed=r.deployed
        )
        for r in records
    ]


@app.get("/thresholds")
def get_current_thresholds(adapter: BanditAdapter = Depends(get_bandit_adapter)):
    """
    GET /thresholds — Returns current live per-zone sensitivity thresholds.
    """
    return adapter.get_zone_thresholds()
