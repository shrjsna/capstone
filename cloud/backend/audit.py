"""
cloud/backend/audit.py
======================
Audit logging infrastructure for the AEGIS Industrial Safety System.
Enforces tamper-resistant, append-only security auditing for all sensitive operations and access refusals.
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from cloud.backend.database import get_db
from cloud.backend.models import AuditLogModel

logger = logging.getLogger("aegis.audit")

audit_router = APIRouter(prefix="/admin", tags=["Audit Log"])

# Helper to sanitize credentials from URLs (e.g. rtsp://user:pass@host/...)
_URL_CRED_REGEX = re.compile(r"://([^:@]+):([^@]+)@")


def sanitize_target_url(url: Optional[str]) -> Optional[str]:
    """Strip embedded username:password credentials from URLs before auditing."""
    if not url:
        return url
    return _URL_CRED_REGEX.sub("://***:***@", url)


def record_audit(
    db: Session,
    action: str,
    outcome: str,
    actor: Optional[str] = None,
    role: Optional[str] = None,
    target: Optional[str] = None,
    client_addr: Optional[str] = None,
    detail: Optional[Dict[str, Any] | str] = None,
) -> Optional[AuditLogModel]:
    """
    Append an entry to the audit log.
    Catches and logs any write errors to prevent blocking primary request processing
    or detection pipelines.
    """
    try:
        ts = datetime.now(timezone.utc).isoformat()
        detail_str: Optional[str] = None
        if isinstance(detail, dict):
            # Ensure sensitive keys are stripped
            clean_detail = {
                k: v for k, v in detail.items()
                if k.lower() not in ("password", "token", "key", "secret", "csrf_token", "temp_password")
            }
            detail_str = json.dumps(clean_detail)
        elif detail is not None:
            detail_str = str(detail)

        entry = AuditLogModel(
            ts=ts,
            actor=actor,
            role=role,
            action=action,
            target=sanitize_target_url(target),
            outcome=outcome,
            client_addr=client_addr,
            detail=detail_str,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry
    except Exception as exc:
        db.rollback()
        logger.error("[audit] Failed to write audit record '%s' (outcome: %s): %s", action, outcome, exc)
        return None


@audit_router.get("/audit-log")
def get_audit_log(
    from_date: Optional[str] = Query(None, alias="from", description="ISO 8601 start timestamp"),
    to_date: Optional[str] = Query(None, alias="to", description="ISO 8601 end timestamp"),
    actor: Optional[str] = Query(None, description="Filter by actor identifier"),
    action: Optional[str] = Query(None, description="Filter by action name"),
    outcome: Optional[str] = Query(None, description="Filter by outcome ('success','denied','failed')"),
    limit: int = Query(50, ge=1, le=200, description="Items per page (default 50, max 200)"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
):
    """
    GET /admin/audit-log — Paginated query interface for the append-only audit trail.
    Admin-only route.
    """
    query = db.query(AuditLogModel)

    if from_date:
        query = query.filter(AuditLogModel.ts >= from_date)
    if to_date:
        query = query.filter(AuditLogModel.ts <= to_date)
    if actor:
        query = query.filter(AuditLogModel.actor == actor)
    if action:
        query = query.filter(AuditLogModel.action == action)
    if outcome:
        query = query.filter(AuditLogModel.outcome == outcome)

    total = query.count()
    items = query.order_by(desc(AuditLogModel.ts), desc(AuditLogModel.id)).offset(offset).limit(limit).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": it.id,
                "ts": it.ts,
                "actor": it.actor,
                "role": it.role,
                "action": it.action,
                "target": it.target,
                "outcome": it.outcome,
                "client_addr": it.client_addr,
                "detail": it.detail,
            }
            for it in items
        ]
    }

