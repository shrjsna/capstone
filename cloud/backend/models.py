"""
cloud/backend/models.py
SQLAlchemy ORM database models for events, operator feedback, and policy version history.
"""

from sqlalchemy import Column, String, Float, Integer, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class EventModel(Base):
    __tablename__ = "events"

    event_id = Column(String, primary_key=True, index=True)
    camera_id = Column(String, nullable=False)
    zone_id = Column(String, nullable=False)
    event_type = Column(String, nullable=False)
    class_name = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    tracked_id = Column(String, nullable=False)
    timestamp = Column(String, nullable=False)
    frame_count_triggered = Column(Integer, nullable=False)
    clip_captured = Column(Boolean, nullable=False)

    # Joined decision fields from Bandit
    bandit_action = Column(String, nullable=True)
    policy_version = Column(String, nullable=True)
    threshold_used = Column(Float, nullable=True)

    feedback = relationship("FeedbackModel", back_populates="event", uselist=False, cascade="all, delete-orphan")


class FeedbackModel(Base):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String, ForeignKey("events.event_id"), nullable=False, unique=True, index=True)
    feedback = Column(String, nullable=False)
    operator_id = Column(String, nullable=False)
    timestamp = Column(String, nullable=False)

    event = relationship("EventModel", back_populates="feedback")


class PolicyVersionModel(Base):
    __tablename__ = "policy_versions"

    policy_version = Column(String, primary_key=True, index=True)
    trained_at = Column(String, nullable=False)
    validation_score = Column(Float, nullable=False)
    previous_version = Column(String, nullable=False)
    deployed = Column(Boolean, nullable=False, default=True)
