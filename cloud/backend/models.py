"""
cloud/backend/models.py
=======================
SQLAlchemy ORM database models for events, operator feedback, policy version history,
users, sessions, login attempts, edge keys, and append-only audit log.
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


class UserModel(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # 'admin' or 'operator'
    active = Column(Integer, nullable=False, default=1)
    must_change_password = Column(Integer, nullable=False, default=0)
    created_at = Column(String, nullable=False)
    created_by = Column(String, nullable=True)
    last_login_at = Column(String, nullable=True)

    sessions = relationship("SessionModel", back_populates="user", cascade="all, delete-orphan")


class SessionModel(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    token_hash = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    csrf_token = Column(String, nullable=False)
    created_at = Column(String, nullable=False)
    last_seen_at = Column(String, nullable=False)
    expires_at = Column(String, nullable=False)
    revoked = Column(Integer, nullable=False, default=0)
    client_addr = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)

    user = relationship("UserModel", back_populates="sessions")


class LoginAttemptModel(Base):
    __tablename__ = "login_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, nullable=True, index=True)
    client_addr = Column(String, nullable=True, index=True)
    attempted_at = Column(String, nullable=False)
    success = Column(Integer, nullable=False)


class EdgeKeyModel(Base):
    __tablename__ = "edge_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key_prefix = Column(String, unique=True, nullable=False, index=True)
    key_hash = Column(String, nullable=False)
    label = Column(String, nullable=False)
    created_at = Column(String, nullable=False)
    created_by = Column(String, nullable=True)
    active = Column(Integer, nullable=False, default=1)
    revoked_at = Column(String, nullable=True)
    last_used_at = Column(String, nullable=True)


class AuditLogModel(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(String, nullable=False, index=True)
    actor = Column(String, nullable=True, index=True)
    role = Column(String, nullable=True)
    action = Column(String, nullable=False, index=True)
    target = Column(String, nullable=True)
    outcome = Column(String, nullable=False, index=True)
    client_addr = Column(String, nullable=True)
    detail = Column(String, nullable=True)
