"""
Pydantic schemas for the Industrial Safety Cloud Backend.
==========================================================
All schemas match the shared data contracts in INTERFACES.md exactly.
Using Pydantic v2 model_config instead of the deprecated Config class.
"""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


# ─────────────────────────────────────────────────────────────
# Section 1 — Detection Event  (edge → cloud, POST /events)
# ─────────────────────────────────────────────────────────────

class DetectionEvent(BaseModel):
    """
    Emitted by PPE or zone-intrusion module and POSTed to /events.
    'class' is a reserved Python keyword so we alias it via Field.
    """

    camera_id: str
    zone_id: str
    event_type: Literal["ppe_violation", "zone_intrusion"]
    class_name: str = Field(..., alias="class")
    confidence: float = Field(..., ge=0.0, le=1.0)
    tracked_id: Optional[str] = None
    timestamp: Optional[str] = None
    frame_count_triggered: int = Field(default=3, ge=1)
    clip_captured: bool = False
    event_id: Optional[str] = None   # caller may supply; backend generates if absent

    model_config = {"populate_by_name": True}


# ─────────────────────────────────────────────────────────────
# Section 2 — Operator Feedback  (dashboard → cloud, POST /feedback)
# ─────────────────────────────────────────────────────────────

class OperatorFeedback(BaseModel):
    """Emitted when an operator clicks Confirm or False Alarm on the dashboard."""

    event_id: str
    feedback: Literal["confirmed", "false_alarm"]
    operator_id: str
    timestamp: Optional[str] = None


# ─────────────────────────────────────────────────────────────
# Section 3 — Bandit Decision Output  (cloud, internal → response)
# ─────────────────────────────────────────────────────────────

class BanditDecision(BaseModel):
    """Returned by POST /events after the bandit selects an action."""

    event_id: str
    action: Literal["escalate", "log_only", "adjust_threshold"]
    policy_version: str
    threshold_used: float


# ─────────────────────────────────────────────────────────────
# Section 4 — Policy Update Record  (cloud, POST /retrain response)
# ─────────────────────────────────────────────────────────────

class PolicyUpdateRecord(BaseModel):
    """Returned by POST /retrain after validation gate runs."""

    policy_version: str
    trained_at: str
    validation_score: float
    previous_version: str
    deployed: bool


# ─────────────────────────────────────────────────────────────
# Alert record stored in memory for the dashboard GET /alerts
# ─────────────────────────────────────────────────────────────

class AlertRecord(BaseModel):
    """
    Full alert record held in memory — combines the original detection event
    with the bandit decision so the dashboard has everything it needs.
    """

    event_id: str
    camera_id: str
    zone_id: str
    event_type: str
    class_name: str
    confidence: float
    tracked_id: Optional[str] = None
    timestamp: Optional[str] = None
    clip_captured: bool = False
    action: str
    policy_version: str
    threshold_used: float
    feedback: Optional[str] = None          # filled in when operator responds
    operator_id: Optional[str] = None
    feedback_timestamp: Optional[str] = None
    status: Literal["pending", "acknowledged"] = "pending"


# ─────────────────────────────────────────────────────────────
# Retrain request body  (POST /retrain)
# ─────────────────────────────────────────────────────────────

class RetrainRequest(BaseModel):
    """
    Optional body for POST /retrain.
    If min_validation_score is omitted the backend uses the project-standard 0.70.
    """
    min_validation_score: float = Field(default=0.70, ge=0.0, le=1.0)
