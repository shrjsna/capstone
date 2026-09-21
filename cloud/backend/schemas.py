"""
cloud/backend/schemas.py
Pydantic data validation schemas matching INTERFACES.md contracts strictly.
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field, ConfigDict


class DetectionEventCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    camera_id: str
    zone_id: str
    event_type: Literal["ppe_violation", "zone_intrusion"]
    class_name: str = Field(..., alias="class")
    confidence: float
    tracked_id: str
    timestamp: str
    frame_count_triggered: int
    clip_captured: bool


class DetectionEventResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    event_id: str
    camera_id: str
    zone_id: str
    event_type: str
    class_name: str = Field(..., alias="class")
    confidence: float
    tracked_id: str
    timestamp: str
    frame_count_triggered: int
    clip_captured: bool
    bandit_action: Optional[str] = None
    policy_version: Optional[str] = None
    threshold_used: Optional[float] = None


class OperatorFeedbackCreate(BaseModel):
    event_id: str
    feedback: Literal["confirmed", "false_alarm"]
    operator_id: str
    timestamp: str


class OperatorFeedbackResponse(BaseModel):
    status: str
    event_id: str
    feedback: str
    operator_id: str
    timestamp: str


class BanditDecisionOutput(BaseModel):
    event_id: str
    action: Literal["escalate", "log_only", "adjust_threshold"]
    policy_version: str
    threshold_used: float


class PolicyUpdateRecord(BaseModel):
    policy_version: str
    trained_at: str
    validation_score: float
    previous_version: str
    deployed: bool
