"""
cloud/backend/retention.py
==========================
Data retention and cleanup manager for the AEGIS Safety System.
Enforces privacy and storage bounds per docs/decisions.md:
- Prunes event logs older than a configurable retention window.
- Removes unneeded incident video clips older than retention window.
- Caps maximum database event records to prevent unbounded disk growth.
"""

import logging
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from cloud.backend.config import get_settings, REPO_ROOT
from cloud.backend.models import EventModel, FeedbackModel

logger = logging.getLogger("aegis.retention")


def cleanup_old_records(
    db: Session,
    max_age_days: Optional[int] = None,
    max_events: Optional[int] = None,
    clips_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Execute data retention cleanup:
    1. Prune events older than max_age_days.
    2. Prune excess events beyond max_events cap (FIFO by timestamp).
    3. Delete clip video files older than max_age_days in clips_dir.
    """
    settings = get_settings()
    age_days = max_age_days if max_age_days is not None else settings.RETENTION_DAYS
    event_cap = max_events if max_events is not None else settings.MAX_STORED_EVENTS
    target_clips_dir = clips_dir if clips_dir is not None else settings.CLIPS_DIR

    now_utc = datetime.now(timezone.utc)
    cutoff_dt = now_utc - timedelta(days=age_days)
    cutoff_iso = cutoff_dt.isoformat()

    events_pruned = 0
    clips_deleted = 0
    bytes_freed = 0

    # 1. Prune events older than cutoff date
    try:
        old_events = db.query(EventModel).filter(EventModel.timestamp < cutoff_iso).all()
        events_pruned += len(old_events)
        for e in old_events:
            db.delete(e)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("[retention] Error deleting aged events: %s", exc)

    # 2. Enforce total event record cap
    try:
        total_count = db.query(func.count(EventModel.event_id)).scalar() or 0
        if total_count > event_cap:
            excess = total_count - event_cap
            oldest_events = (
                db.query(EventModel)
                .order_by(EventModel.timestamp.asc())
                .limit(excess)
                .all()
            )
            for e in oldest_events:
                db.delete(e)
            db.commit()
            events_pruned += len(oldest_events)
    except Exception as exc:
        db.rollback()
        logger.error("[retention] Error capping excess events: %s", exc)

    # 3. Clean up video clips in clips_dir older than cutoff
    if target_clips_dir and target_clips_dir.exists() and target_clips_dir.is_dir():
        cutoff_epoch = cutoff_dt.timestamp()
        for ext in ("*.mp4", "*.avi", "*.mkv", "*.jpg"):
            for file_path in target_clips_dir.glob(ext):
                try:
                    mtime = file_path.stat().st_mtime
                    if mtime < cutoff_epoch:
                        file_size = file_path.stat().st_size
                        file_path.unlink()
                        clips_deleted += 1
                        bytes_freed += file_size
                except Exception as file_exc:
                    logger.warning("[retention] Could not delete clip %s: %s", file_path.name, file_exc)

    logger.info(
        "[retention] Cleanup finished: %d events pruned, %d clips deleted, %.2f KB freed (cutoff: %d days)",
        events_pruned,
        clips_deleted,
        bytes_freed / 1024.0,
        age_days,
    )

    return {
        "status": "success",
        "retention_days": age_days,
        "max_events": event_cap,
        "cutoff_timestamp": cutoff_iso,
        "events_pruned": events_pruned,
        "clips_deleted": clips_deleted,
        "bytes_freed": bytes_freed,
    }
