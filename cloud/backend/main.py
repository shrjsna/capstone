"""
cloud/backend/main.py
=====================
FastAPI application for Module D Cloud Backend.
Enforces Role-Based Access Control (Admin, Operator, Edge), session security,
audit logging, strict input validation, automated data retention, and resource controls.
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from cloud.backend.config import get_settings, REPO_ROOT
from cloud.backend.database import get_db, init_db
from cloud.backend.models import EventModel, FeedbackModel, PolicyVersionModel, UserModel
from cloud.backend.schemas import (
    DetectionEventCreate,
    DetectionEventResponse,
    OperatorFeedbackCreate,
    OperatorFeedbackResponse,
    PolicyUpdateRecord,
    StreamStartRequest,
    ZoneSaveRequest,
    RetentionCleanupRequest,
    RetentionCleanupResponse,
)
from cloud.backend.security import (
    validate_identifier,
    validate_safe_filename,
    validate_media_source,
    validate_model_path,
    validate_zone_config_path,
)
from cloud.backend.retention import cleanup_old_records
from cloud.backend.adapter import get_bandit_adapter, BanditAdapter
from cloud.backend.stream_manager import (
    start_stream,
    stop_stream,
    stream_status,
    generate_mjpeg_frames,
    get_latest_frame_jpeg,
    get_capture_lock,
    get_stream_state,
)
from cloud.backend.process_manager import (
    get_process_manager,
    ProcessStartRequest,
)

# RBAC, Authentication, and Audit components
from cloud.backend.audit import audit_router, record_audit
from cloud.backend.auth import (
    INTERNAL_STREAM_KEY,
    auth_router,
    get_client_ip,
)
from cloud.backend.permissions import RBACMiddleware, is_builtin_media_source
from cloud.backend.users_admin import admin_users_router

logger = logging.getLogger("aegis.backend")
settings = get_settings()

ZONES_DIR = settings.ZONES_DIR


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables and triggers on startup
    init_db()

    # Populate initial seed policy record if empty and check admin existence
    db = next(get_db())
    try:
        if not db.query(PolicyVersionModel).first():
            seed_policy = PolicyVersionModel(
                policy_version="v1.0.0-mock",
                trained_at="2026-09-20T10:00:00Z",
                validation_score=0.915,
                previous_version="v0.9.0",
                deployed=True,
            )
            db.add(seed_policy)
            db.commit()

        # Check for existence of any active administrator
        admin_exists = db.query(UserModel).filter(UserModel.role == "admin", UserModel.active == 1).first()
        if not admin_exists:
            logger.warning("[security] No administrator exists. Run: python -m cloud.backend.manage create-admin")

        # Run startup data retention cleanup to ensure storage bounds from day 1
        cleanup_old_records(db)
    finally:
        db.close()

    yield

    # Shutdown cleanup
    try:
        stop_stream()
    except Exception:
        pass
    try:
        get_process_manager().stop_all()
    except Exception:
        pass


app = FastAPI(
    title="AEGIS Industrial Safety System — Cloud Backend API",
    version="2.0.0",
    description="Production-grade edge-cloud collaborative AI safety backend with RBAC.",
    lifespan=lifespan,
    docs_url="/docs" if settings.DOCS_ENABLED else None,
    redoc_url="/redoc" if settings.DOCS_ENABLED else None,
    openapi_url="/openapi.json" if settings.DOCS_ENABLED else None,
)

# 1. CORS Middleware: Strict origin matching; rejects wildcard origins with credentials
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# 2. Global RBAC & Session Security Middleware (Default-Deny)
app.add_middleware(RBACMiddleware)

# 3. Mount Specialized Authentication and Administration Routers
app.include_router(auth_router)
app.include_router(admin_users_router)
app.include_router(audit_router)


# ===========================================================================
# Health & Status (Open Read-Only)
# ===========================================================================

@app.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    """Basic health check endpoint for monitoring probes."""
    return {"status": "ok"}


@app.get("/login", include_in_schema=False)
def login_redirect():
    """Redirect clean /login URL to /login.html."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/login.html", status_code=status.HTTP_302_FOUND)


# ===========================================================================
# Event Ingestion & Human-in-the-Loop Feedback (Authenticated)
# ===========================================================================

@app.post(
    "/events",
    response_model=DetectionEventResponse,
    status_code=status.HTTP_201_CREATED,
)
def receive_detection_event(
    event: DetectionEventCreate,
    request: Request,
    db: Session = Depends(get_db),
    adapter: BanditAdapter = Depends(get_bandit_adapter),
):
    """
    POST /events — Accepts Detection Events from edge modules, internal stream worker,
    or simulated events from administrators.
    """
    cam_id = validate_identifier(event.camera_id, "camera_id")
    zone_id = validate_identifier(event.zone_id, "zone_id")
    tracked_id = validate_identifier(event.tracked_id, "tracked_id")

    event_id = str(uuid.uuid4())
    decision = adapter.decide(event, event_id)

    db_event = EventModel(
        event_id=event_id,
        camera_id=cam_id,
        zone_id=zone_id,
        event_type=event.event_type,
        class_name=event.class_name,
        confidence=event.confidence,
        tracked_id=tracked_id,
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

    identity = getattr(request.state, "identity", None)
    # Log simulated events from administrator sessions
    if identity and identity.role == "admin":
        record_audit(
            db=db,
            action="event.simulated",
            outcome="success",
            actor=identity.actor,
            role=identity.role,
            target=f"event:{event_id}",
            client_addr=get_client_ip(request),
            detail=f"Simulated {event.event_type} event ({event.class_name}).",
        )

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
        feedback=None,
    )


@app.post(
    "/feedback",
    response_model=OperatorFeedbackResponse,
    status_code=status.HTTP_200_OK,
)
def submit_operator_feedback(
    feedback: OperatorFeedbackCreate,
    request: Request,
    db: Session = Depends(get_db),
    adapter: BanditAdapter = Depends(get_bandit_adapter),
):
    """
    POST /feedback — Accepts Operator Feedback from the dashboard.
    Provenance guarantee: operator_id is derived from the authenticated session.
    A client-supplied operator_id is ignored to prevent spoofing.
    """
    event_id = validate_identifier(feedback.event_id, "event_id")

    # Authoritative operator identity from session
    identity = getattr(request.state, "identity", None)
    operator_id = identity.actor if (identity and identity.actor) else validate_identifier(feedback.operator_id, "operator_id", min_len=2)

    event_record = db.query(EventModel).filter(EventModel.event_id == event_id).first()
    if not event_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event ID '{event_id}' not found.",
        )

    existing_feedback = db.query(FeedbackModel).filter(FeedbackModel.event_id == event_id).first()
    if existing_feedback:
        existing_feedback.feedback = feedback.feedback
        existing_feedback.operator_id = operator_id
        existing_feedback.timestamp = feedback.timestamp
    else:
        db_feedback = FeedbackModel(
            event_id=event_id,
            feedback=feedback.feedback,
            operator_id=operator_id,
            timestamp=feedback.timestamp,
        )
        db.add(db_feedback)

    db.commit()

    fallback_event_dict = {
        "camera_id": event_record.camera_id,
        "zone_id": event_record.zone_id,
        "event_type": event_record.event_type,
        "class": event_record.class_name,
        "confidence": event_record.confidence,
        "tracked_id": event_record.tracked_id,
        "timestamp": event_record.timestamp,
        "frame_count_triggered": event_record.frame_count_triggered,
        "clip_captured": event_record.clip_captured,
        "bandit_action": event_record.bandit_action,
    }

    # Forward reward to bandit adapter for incremental online learning (with fallback for events across restarts)
    adapter.submit_feedback(
        feedback,
        fallback_event=fallback_event_dict,
        fallback_action=event_record.bandit_action,
    )

    logger.info(
        "[audit] Feedback recorded for event %s: %s by operator '%s'",
        event_id,
        feedback.feedback,
        operator_id,
    )

    return OperatorFeedbackResponse(
        status="success",
        event_id=event_id,
        feedback=feedback.feedback,
        operator_id=operator_id,
        timestamp=feedback.timestamp,
    )


# ===========================================================================
# Alert Feed & Policy History Endpoints (Read-Only)
# ===========================================================================

@app.get("/alerts", status_code=status.HTTP_200_OK)
def get_alerts(
    limit: int = Query(default=100, ge=1, le=500),
    event_type: Optional[str] = Query(default=None),
    camera_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """GET /alerts — Returns recent safety events from the database."""
    query = db.query(EventModel)

    if event_type:
        query = query.filter(EventModel.event_type == event_type)
    if camera_id:
        query = query.filter(EventModel.camera_id == camera_id)

    events = query.order_by(EventModel.timestamp.desc()).limit(limit).all()

    results = []
    for ev in events:
        fb_dict = None
        if ev.feedback:
            fb_dict = {
                "feedback": ev.feedback.feedback,
                "operator_id": ev.feedback.operator_id,
                "timestamp": ev.feedback.timestamp,
            }

        results.append({
            "event_id": ev.event_id,
            "camera_id": ev.camera_id,
            "zone_id": ev.zone_id,
            "event_type": ev.event_type,
            "class": ev.class_name,
            "confidence": ev.confidence,
            "tracked_id": ev.tracked_id,
            "timestamp": ev.timestamp,
            "frame_count_triggered": ev.frame_count_triggered,
            "clip_captured": ev.clip_captured,
            "bandit_action": ev.bandit_action,
            "policy_version": ev.policy_version,
            "threshold_used": ev.threshold_used,
            "feedback": fb_dict,
        })

    return results


@app.get("/alerts/{event_id}", status_code=status.HTTP_200_OK)
def get_alert_detail(event_id: str, db: Session = Depends(get_db)):
    """GET /alerts/{event_id} — Single alert detail view."""
    safe_event_id = validate_identifier(event_id, "event_id")

    ev = db.query(EventModel).filter(EventModel.event_id == safe_event_id).first()
    if not ev:
        raise HTTPException(status_code=404, detail=f"Event ID '{safe_event_id}' not found.")

    fb_dict = None
    if ev.feedback:
        fb_dict = {
            "feedback": ev.feedback.feedback,
            "operator_id": ev.feedback.operator_id,
            "timestamp": ev.feedback.timestamp,
        }

    return {
        "event_id": ev.event_id,
        "camera_id": ev.camera_id,
        "zone_id": ev.zone_id,
        "event_type": ev.event_type,
        "class": ev.class_name,
        "confidence": ev.confidence,
        "tracked_id": ev.tracked_id,
        "timestamp": ev.timestamp,
        "frame_count_triggered": ev.frame_count_triggered,
        "clip_captured": ev.clip_captured,
        "bandit_action": ev.bandit_action,
        "policy_version": ev.policy_version,
        "threshold_used": ev.threshold_used,
        "feedback": fb_dict,
    }


@app.get("/policy-history")
def get_policy_history(db: Session = Depends(get_db)):
    """GET /policy-history — Returns historical policy version progression."""
    records = db.query(PolicyVersionModel).order_by(PolicyVersionModel.trained_at.desc()).all()
    return [
        PolicyUpdateRecord(
            policy_version=r.policy_version,
            trained_at=r.trained_at,
            validation_score=r.validation_score,
            previous_version=r.previous_version,
            deployed=r.deployed,
        )
        for r in records
    ]


@app.post("/policy/checkpoint", response_model=PolicyUpdateRecord, status_code=status.HTTP_200_OK)
def checkpoint_policy(
    request: Request,
    db: Session = Depends(get_db),
    adapter: BanditAdapter = Depends(get_bandit_adapter),
):
    """
    POST /policy/checkpoint — Checkpoint current learned weights into a formal versioned policy release.
    Evaluates current model state against validation dataset, increments policy version, and stores record.
    """
    from datetime import datetime, timezone
    from cloud.decision_layer.train_baseline import generate_seed_dataset

    identity = getattr(request.state, "identity", None)
    actor = identity.actor if identity else "operator"
    role = identity.role if identity else "operator"

    prev_ver = adapter.bandit.policy_version
    training_batch, validation_set = generate_seed_dataset()

    # Incorporate recorded feedback events into retraining batch
    feedbacks = db.query(FeedbackModel).all()
    for fb in feedbacks:
        ev = db.query(EventModel).filter(EventModel.event_id == fb.event_id).first()
        if ev:
            ev_dict = {
                "camera_id": ev.camera_id,
                "zone_id": ev.zone_id,
                "event_type": ev.event_type,
                "class": ev.class_name,
                "confidence": ev.confidence,
                "tracked_id": ev.tracked_id,
                "timestamp": ev.timestamp,
                "frame_count_triggered": ev.frame_count_triggered,
                "clip_captured": ev.clip_captured,
            }
            training_batch.append((ev_dict, ev.bandit_action or "escalate", fb.feedback))

    # Run batch retrain through validation gate
    retrain_res = adapter.bandit.retrain(
        training_batch=training_batch,
        validation_set=validation_set,
        min_validation_score=0.60,
    )

    new_version = retrain_res["policy_version"]
    val_score = round(float(retrain_res["validation_score"]), 3)
    now_str = datetime.now(timezone.utc).isoformat()

    # Save to database
    policy_rec = PolicyVersionModel(
        policy_version=new_version,
        trained_at=now_str,
        validation_score=val_score,
        previous_version=prev_ver,
        deployed=retrain_res["deployed"],
    )
    db.add(policy_rec)
    db.commit()

    record_audit(
        db=db,
        action="policy.checkpoint",
        outcome="success",
        actor=actor,
        role=role,
        target=f"policy:{new_version}",
        client_addr=get_client_ip(request),
        detail=f"Checkpointed policy version {new_version} (score: {val_score}) from {len(training_batch)} training events.",
    )

    return PolicyUpdateRecord(
        policy_version=new_version,
        trained_at=now_str,
        validation_score=val_score,
        previous_version=prev_ver,
        deployed=retrain_res["deployed"],
    )


@app.get("/thresholds")
def get_current_thresholds(adapter: BanditAdapter = Depends(get_bandit_adapter)):
    """GET /thresholds — Returns current live per-zone sensitivity thresholds."""
    return adapter.get_zone_thresholds()


@app.get("/model-weights", status_code=status.HTTP_200_OK)
def get_model_weights(adapter: BanditAdapter = Depends(get_bandit_adapter)):
    """GET /model-weights — Returns live Contextual Bandit ridge regression weights and matrix norms."""
    from datetime import datetime, timezone
    import numpy as np
    bandit = adapter.bandit
    actions_info = {}

    for action in ("escalate", "log_only", "adjust_threshold"):
        A = bandit.A[action]
        b = bandit.b[action]
        theta = np.linalg.solve(A, b).flatten()
        norm = float(np.linalg.norm(theta))
        actions_info[action] = {
            "norm": round(norm, 4),
            "confidence_weight": round(float(theta[0]), 4),
            "threshold_diff_weight": round(float(theta[1]), 4),
            "frame_persistence_weight": round(float(theta[3]), 4),
            "decision_bias": round(float(theta[15]), 4),
            "weights_vector": [round(float(v), 4) for v in theta],
        }

    return {
        "policy_version": bandit.policy_version,
        "update_count": getattr(bandit, "update_count", 0),
        "actions": actions_info,
        "active_thresholds": adapter.get_zone_thresholds(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ===========================================================================
# Stream Endpoints (Start/Stop Authenticated; MJPEG/Latest Frame Open)
# ===========================================================================

@app.post("/stream/start", status_code=status.HTTP_200_OK)
def stream_start(
    req: StreamStartRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    POST /stream/start — Start a background live-inference stream.
    Validates file paths, model paths, and camera sources against traversal/SSRF.
    Passes internal service credential to the stream worker for internal /events ingestion.
    """
    safe_source = validate_media_source(req.source)
    safe_model = validate_model_path(req.model_path)
    safe_zone = validate_zone_config_path(req.zone_config_path)
    safe_cam = validate_identifier(req.camera_id, "camera_id")
    safe_zone_id = validate_identifier(req.zone_id, "zone_id")

    events_api_url = f"http://127.0.0.1:{settings.PORT}/events"

    result = start_stream(
        source=safe_source,
        mode=req.mode,
        model_path=safe_model,
        zone_config_path=safe_zone,
        camera_id=safe_cam,
        zone_id=safe_zone_id,
        events_api_url=events_api_url,
        debounce_frames=req.debounce_frames,
        conf_threshold=req.conf_threshold,
        api_key=INTERNAL_STREAM_KEY,
    )
    if not result["started"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=result.get("error", "Failed to start stream"),
        )

    identity = getattr(request.state, "identity", None)
    actor = identity.actor if identity else "operator"
    role = identity.role if identity else "operator"

    action_name = "stream.start.builtin" if is_builtin_media_source(req.source) else "stream.start.custom_url"
    record_audit(
        db=db,
        action=action_name,
        outcome="success",
        actor=actor,
        role=role,
        target=str(safe_source),
        client_addr=get_client_ip(request),
        detail=f"Started stream in mode '{req.mode}' (cam: {safe_cam}, zone: {safe_zone_id}).",
    )

    return result


@app.post("/stream/stop", status_code=status.HTTP_200_OK)
def stream_stop(
    request: Request,
    db: Session = Depends(get_db),
):
    """POST /stream/stop — Stop running live stream."""
    identity = getattr(request.state, "identity", None)
    actor = identity.actor if identity else "operator"
    role = identity.role if identity else "operator"

    res = stop_stream()
    record_audit(
        db=db,
        action="stream.stop",
        outcome="success",
        actor=actor,
        role=role,
        client_addr=get_client_ip(request),
        detail="Stopped running live stream worker.",
    )
    return res


@app.get("/stream/status")
def stream_status_endpoint():
    """GET /stream/status — Returns current stream state."""
    return stream_status()


@app.get("/stream/mjpeg")
def stream_mjpeg():
    """GET /stream/mjpeg — Multipart MJPEG stream behind session cookie authentication."""
    return StreamingResponse(
        generate_mjpeg_frames(),
        media_type="multipart/x-mixed-replace; boundary=aegisframe",
    )


@app.get("/stream/latest-frame")
def stream_latest_frame():
    """GET /stream/latest-frame — Returns single latest annotated JPEG frame."""
    jpeg = get_latest_frame_jpeg()
    return StreamingResponse(iter([jpeg]), media_type="image/jpeg")


# ===========================================================================
# Capture Frame Endpoint (for Zone Draw Calibration)
# ===========================================================================

@app.get("/capture-frame")
def capture_frame(source: str = Query(..., description="Video source: webcam index, file path, or RTSP URL")):
    """
    GET /capture-frame?source=... — Grab ONE calibrated frame from the source.
    Admin-only route. Validated against path traversal.
    """
    safe_src_str = validate_media_source(source)

    try:
        import cv2
    except ImportError:
        raise HTTPException(status_code=503, detail="cv2 not available on this server.")

    src = int(safe_src_str) if safe_src_str.isdigit() else safe_src_str

    state = get_stream_state()
    if state.is_running():
        jpeg = state.get_latest_frame()
        if jpeg is None:
            jpeg = state.wait_for_frame(timeout=1.0)
        if jpeg:
            import numpy as np
            nparr = np.frombuffer(jpeg, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            h, w = (img.shape[0], img.shape[1]) if img is not None else (480, 640)
            return StreamingResponse(
                iter([jpeg]),
                media_type="image/jpeg",
                headers={
                    "X-Frame-Width": str(w),
                    "X-Frame-Height": str(h),
                },
            )

    capture_lock = get_capture_lock()
    with capture_lock:
        cap = cv2.VideoCapture(src)

        if not cap.isOpened():
            raise HTTPException(
                status_code=422,
                detail=f"Could not open source: {source!r}. Check URL, path, or camera index.",
            )

        # Skip a few frames to let auto-exposure settle
        for _ in range(3):
            cap.read()

        read_res = cap.read()
        cap.release()

    if not read_res or len(read_res) != 2 or not read_res[0] or read_res[1] is None:
        raise HTTPException(
            status_code=422,
            detail=f"Source opened but produced no frames: {source!r}",
        )
    ret, frame = read_res

    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to encode frame as JPEG.")

    return StreamingResponse(
        iter([buf.tobytes()]),
        media_type="image/jpeg",
        headers={
            "X-Frame-Width": str(frame.shape[1]),
            "X-Frame-Height": str(frame.shape[0]),
        },
    )


# ===========================================================================
# Zone Management Endpoints (List Open; Save/Delete Admin-Only)
# ===========================================================================

@app.get("/zones")
def list_zones():
    """GET /zones — List all saved safety zone configurations."""
    ZONES_DIR.mkdir(parents=True, exist_ok=True)
    zones = []
    for f in sorted(ZONES_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            try:
                rel_path = str(f.relative_to(REPO_ROOT))
            except ValueError:
                rel_path = str(f)
            zones.append({
                "camera_id": data.get("camera_id", ""),
                "zone_id": data.get("zone_id", ""),
                "point_count": len(data.get("polygon", [])),
                "polygon": data.get("polygon", []),
                "frame_width": data.get("frame_width"),
                "frame_height": data.get("frame_height"),
                "file_path": rel_path,
                "filename": f.name,
            })
        except Exception:
            pass
    return zones


@app.post("/zones", status_code=status.HTTP_201_CREATED)
def save_zone(
    req: ZoneSaveRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """POST /zones — Save a new zone config JSON. Admin-only."""
    cam_id = validate_identifier(req.camera_id, "camera_id")
    zone_id = validate_identifier(req.zone_id, "zone_id")

    if len(req.polygon) < 3:
        raise HTTPException(status_code=422, detail="A zone polygon needs at least 3 points.")

    ZONES_DIR.mkdir(parents=True, exist_ok=True)

    filename = f"{cam_id}_{zone_id}.json"
    filepath = validate_safe_filename(filename, ZONES_DIR)

    zone_data: Dict[str, Any] = {
        "camera_id": cam_id,
        "zone_id": zone_id,
        "polygon": [[int(pt[0]), int(pt[1])] for pt in req.polygon],
    }
    if req.frame_width:
        zone_data["frame_width"] = req.frame_width
    if req.frame_height:
        zone_data["frame_height"] = req.frame_height

    filepath.write_text(json.dumps(zone_data, indent=2), encoding="utf-8")

    try:
        rel_path = str(filepath.relative_to(REPO_ROOT))
    except ValueError:
        rel_path = str(filepath)

    identity = getattr(request.state, "identity", None)
    actor = identity.actor if identity else "admin"
    record_audit(
        db=db,
        action="zone.create",
        outcome="success",
        actor=actor,
        role="admin",
        target=f"zone:{cam_id}:{zone_id}",
        client_addr=get_client_ip(request),
        detail=f"Created zone '{zone_id}' with {len(req.polygon)} points.",
    )

    return {
        "saved": True,
        "filename": filename,
        "file_path": rel_path,
        "camera_id": cam_id,
        "zone_id": zone_id,
        "point_count": len(req.polygon),
        "polygon": zone_data["polygon"],
    }


@app.delete("/zones/{camera_id}/{zone_id}", status_code=status.HTTP_200_OK)
def delete_zone(
    camera_id: str,
    zone_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """DELETE /zones/{camera_id}/{zone_id} — Remove a saved zone config file. Admin-only."""
    cam_id = validate_identifier(camera_id, "camera_id")
    zid = validate_identifier(zone_id, "zone_id")

    filename = f"{cam_id}_{zid}.json"
    filepath = validate_safe_filename(filename, ZONES_DIR)

    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Zone file not found: {filename}")

    filepath.unlink()

    identity = getattr(request.state, "identity", None)
    actor = identity.actor if identity else "admin"
    record_audit(
        db=db,
        action="zone.delete",
        outcome="success",
        actor=actor,
        role="admin",
        target=f"zone:{cam_id}:{zid}",
        client_addr=get_client_ip(request),
        detail=f"Deleted zone configuration file {filename}.",
    )

    return {"deleted": True, "filename": filename}


# =========================================================================
# Subprocess Management Endpoints (Control Panel) — Admin-Only
# =========================================================================

@app.get("/processes", status_code=status.HTTP_200_OK)
def list_managed_processes():
    """List all managed background subprocesses and their status. Admin-only."""
    return get_process_manager().list_processes()


@app.post("/processes/{name}/start", status_code=status.HTTP_200_OK)
def start_managed_process(
    name: str,
    request: Request,
    req: Optional[ProcessStartRequest] = None,
    db: Session = Depends(get_db),
):
    """
    Start a named managed process (federated_demo or zone_pipeline).
    Admin-only.
    """
    if name not in ("federated_demo", "zone_pipeline"):
        raise HTTPException(status_code=404, detail=f"Unknown process '{name}'.")

    try:
        source = req.source if req else None
        res = get_process_manager().start_process(name, source=source)

        identity = getattr(request.state, "identity", None)
        actor = identity.actor if identity else "admin"

        if name == "federated_demo":
            record_audit(
                db=db,
                action="federated.start",
                outcome="success",
                actor=actor,
                role="admin",
                target="process:federated_demo",
                client_addr=get_client_ip(request),
                detail="Started federated learning (server 127.0.0.1:8089, rounds=2, min_clients=2).",
            )
        else:
            record_audit(
                db=db,
                action="zone_pipeline.start",
                outcome="success",
                actor=actor,
                role="admin",
                target=f"process:zone_pipeline:{source or 'default'}",
                client_addr=get_client_ip(request),
                detail=f"Started zone intrusion pipeline (source: {source}).",
            )

        return res
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/processes/{name}/stop", status_code=status.HTTP_200_OK)
def stop_managed_process(
    name: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Stop a named managed process. Admin-only."""
    if name not in ("federated_demo", "zone_pipeline"):
        raise HTTPException(status_code=404, detail=f"Unknown process '{name}'.")

    try:
        res = get_process_manager().stop_process(name)

        identity = getattr(request.state, "identity", None)
        actor = identity.actor if identity else "admin"

        action_name = "federated.stop" if name == "federated_demo" else "zone_pipeline.stop"
        record_audit(
            db=db,
            action=action_name,
            outcome="success",
            actor=actor,
            role="admin",
            target=f"process:{name}",
            client_addr=get_client_ip(request),
            detail=f"Stopped managed process '{name}'.",
        )

        return res
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/processes/{name}/logs", status_code=status.HTTP_200_OK)
def get_managed_process_logs(
    name: str,
    request: Request,
    tail: int = Query(default=500, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """Fetch bounded recent logs for a managed process. Admin-only."""
    if name not in ("federated_demo", "zone_pipeline"):
        raise HTTPException(status_code=404, detail=f"Unknown process '{name}'.")

    try:
        res = get_process_manager().get_logs(name, tail=tail)

        # Audit read for federated learning logs
        if name == "federated_demo":
            identity = getattr(request.state, "identity", None)
            actor = identity.actor if identity else "admin"
            record_audit(
                db=db,
                action="federated.logs.read",
                outcome="success",
                actor=actor,
                role="admin",
                target="process:federated_demo:logs",
                client_addr=get_client_ip(request),
                detail=f"Inspected federated demo logs ({len(res.get('logs', []))} lines).",
            )

        return res
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


# =========================================================================
# Data Retention / Storage Cleanup Endpoint — Admin-Only
# =========================================================================

@app.post(
    "/retention/cleanup",
    response_model=RetentionCleanupResponse,
    status_code=status.HTTP_200_OK,
)
def trigger_retention_cleanup(
    request: Request,
    req: Optional[RetentionCleanupRequest] = None,
    db: Session = Depends(get_db),
):
    """POST /retention/cleanup — Trigger automated cleanup of aged events and clips. Admin-only."""
    max_days = req.max_age_days if req else None
    max_events = req.max_events if req else None

    result = cleanup_old_records(db, max_age_days=max_days, max_events=max_events)

    identity = getattr(request.state, "identity", None)
    actor = identity.actor if identity else "admin"
    record_audit(
        db=db,
        action="retention.cleanup",
        outcome="success",
        actor=actor,
        role="admin",
        target="data_retention",
        client_addr=get_client_ip(request),
        detail=f"Pruned data: {result.get('purged_events', 0)} events, {result.get('purged_clips', 0)} clips.",
    )

    return RetentionCleanupResponse(**result)


# =========================================================================
# Static Files — Single-Process Dashboard Serving
# Mounted AFTER all API routes so it does not shadow API endpoints.
# =========================================================================
_DASHBOARD_DIR = REPO_ROOT / "dashboard"
if _DASHBOARD_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_DASHBOARD_DIR), html=True), name="dashboard")
