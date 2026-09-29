"""
cloud/backend/schemas.py
========================
Pydantic data validation schemas matching INTERFACES.md contracts strictly,
hardened with bounds checking and regex constraints for production readiness.
"""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict


class DetectionEventCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    camera_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_\-\.]+$")
    zone_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_\-\.]+$")
    event_type: Literal["ppe_violation", "zone_intrusion"]
    class_name: str = Field(..., alias="class", min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_\-\. ]+$")
    confidence: float = Field(..., ge=0.0, le=1.0)
    tracked_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_\-\.]+$")
    timestamp: str = Field(..., min_length=10, max_length=64)
    frame_count_triggered: int = Field(..., ge=0, le=1000000)
    clip_captured: bool = False


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
    feedback: Optional[str] = None  # "confirmed" | "false_alarm" | None


class OperatorFeedbackCreate(BaseModel):
    event_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_\-\.]+$")
    feedback: Literal["confirmed", "false_alarm"]
    operator_id: str = Field(..., min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9_\-\.]+$")
    timestamp: str = Field(..., min_length=10, max_length=64)


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


class StreamStartRequest(BaseModel):
    source: str = Field(..., min_length=1, max_length=256)
    mode: str = Field("all", pattern=r"^(all|combined|ppe|zone_intrusion)$")
    model_path: Optional[str] = Field(None, max_length=256)
    zone_config_path: Optional[str] = Field(None, max_length=256)
    camera_id: str = Field("stream_cam", min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_\-\.]+$")
    zone_id: str = Field("stream_zone", min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_\-\.]+$")
    debounce_frames: int = Field(3, ge=1, le=100)
    conf_threshold: float = Field(0.25, ge=0.01, le=1.0)


class ZoneSaveRequest(BaseModel):
    camera_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_\-\.]+$")
    zone_id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_\-\.]+$")
    polygon: List[List[float]] = Field(..., min_length=3, max_length=500)
    frame_width: Optional[int] = Field(None, ge=16, le=7680)
    frame_height: Optional[int] = Field(None, ge=16, le=4320)


class RetentionCleanupRequest(BaseModel):
    max_age_days: Optional[int] = Field(None, ge=1, le=365)
    max_events: Optional[int] = Field(None, ge=10, le=1000000)


class RetentionCleanupResponse(BaseModel):
    status: str
    retention_days: int
    max_events: int
    cutoff_timestamp: str
    events_pruned: int
    clips_deleted: int
    bytes_freed: int
