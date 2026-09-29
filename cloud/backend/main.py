"""
cloud/backend/main.py
=====================
FastAPI application for Module D Cloud Backend.
Hardened for production deployment with API authentication, strict input validation,
configurable CORS, automated data retention, and resource controls.
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from cloud.backend.config import get_settings, REPO_ROOT
from cloud.backend.database import get_db, init_db
from cloud.backend.models import EventModel, FeedbackModel, PolicyVersionModel
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
    verify_api_key,
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
)
from cloud.backend.process_manager import (
    get_process_manager,
    ProcessStartRequest,
)

logger = logging.getLogger("aegis.backend")
settings = get_settings()

ZONES_DIR = settings.ZONES_DIR


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables on startup
    init_db()

    # Populate initial seed policy record if empty
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
    version="1.1.0",
    description="Production-grade edge-cloud collaborative AI safety backend.",
    lifespan=lifespan,
)

# Explicit CORS Origins Configuration (Configured from config.py / .env, never hardcoded '*')
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ===========================================================================
# Health & Status (Open Read-Only)
# ===========================================================================

@app.get("/health", status_code=status.HTTP_200_OK)
def health_check():
    """Basic health check endpoint for monitoring probes."""
    return {"status": "ok"}


# ===========================================================================
# Event Ingestion & Human-in-the-Loop Feedback (State-Changing: Authenticated)
# ===========================================================================

@app.post(
    "/events",
    response_model=DetectionEventResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_api_key)],
)
def receive_detection_event(
    event: DetectionEventCreate,
    db: Session = Depends(get_db),
    adapter: BanditAdapter = Depends(get_bandit_adapter),
):
    """
    POST /events — Accepts Detection Events from edge modules or live stream.
    Validates identifiers against path traversal/injection, queries Bandit for decision, persists to DB.
    Requires API key authentication.
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

    logger.info(
        "[audit] Event received: %s (%s, %s, conf=%.2f) -> bandit %s",
        db_event.event_id,
        db_event.event_type,
        db_event.class_name,
        db_event.confidence,
        db_event.bandit_action,
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
    dependencies=[Depends(verify_api_key)],
)
def submit_operator_feedback(
    feedback: OperatorFeedbackCreate,
    db: Session = Depends(get_db),
    adapter: BanditAdapter = Depends(get_bandit_adapter),
):
    """
    POST /feedback — Accepts Operator Feedback from the dashboard.
    Validates operator_id and event_id, persists reward signal, and updates Bandit.
    Requires API key authentication.
    """
    event_id = validate_identifier(feedback.event_id, "event_id")
    operator_id = validate_identifier(feedback.operator_id, "operator_id", min_len=2)

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

    # Forward reward to bandit adapter for incremental online learning
    adapter.submit_feedback(feedback)

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
# Alert Feed & Telemetry (Open Read-Only with Multi-Parameter Filtering)
# ===========================================================================

@app.get("/alerts", response_model=List[DetectionEventResponse])
def get_alerts(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    event_type: Optional[str] = Query(None, description="Filter by event_type: ppe_violation or zone_intrusion"),
    camera_id: Optional[str] = Query(None, description="Filter by camera_id"),
    zone_id: Optional[str] = Query(None, description="Filter by zone_id"),
    class_name: Optional[str] = Query(None, description="Filter by class/violation type"),
    start_time: Optional[str] = Query(None, description="Filter events >= start_time (ISO8601)"),
    end_time: Optional[str] = Query(None, description="Filter events <= end_time (ISO8601)"),
    db: Session = Depends(get_db),
):
    """
    GET /alerts — Returns recent events with bandit decision data and feedback status.
    Supports comprehensive filtering by type, camera, zone, class, and date range.
    """
    query = db.query(EventModel)

    if event_type:
        query = query.filter(EventModel.event_type == event_type.strip())
    if camera_id:
        query = query.filter(EventModel.camera_id == camera_id.strip())
    if zone_id:
        query = query.filter(EventModel.zone_id == zone_id.strip())
    if class_name:
        query = query.filter(EventModel.class_name == class_name.strip())
    if start_time:
        query = query.filter(EventModel.timestamp >= start_time.strip())
    if end_time:
        query = query.filter(EventModel.timestamp <= end_time.strip())

    events = query.order_by(EventModel.timestamp.desc()).offset(offset).limit(limit).all()

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
            feedback=e.feedback.feedback if e.feedback else None,
        )
        for e in events
    ]


@app.get("/alerts/{event_id}", response_model=DetectionEventResponse)
def get_alert_detail(event_id: str, db: Session = Depends(get_db)):
    """GET /alerts/{event_id} — Single alert detail view."""
    e = db.query(EventModel).filter(EventModel.event_id == event_id).first()
    if not e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert with ID '{event_id}' not found.",
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
        feedback=e.feedback.feedback if e.feedback else None,
    )


@app.get("/policy-history", response_model=List[PolicyUpdateRecord])
def get_policy_history(db: Session = Depends(get_db)):
    """GET /policy-history — Returns history of bandit policy updates."""
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


@app.get("/thresholds")
def get_current_thresholds(adapter: BanditAdapter = Depends(get_bandit_adapter)):
    """GET /thresholds — Returns current live per-zone sensitivity thresholds."""
    return adapter.get_zone_thresholds()


# ===========================================================================
# Stream Endpoints (Start/Stop Authenticated; MJPEG/Latest Frame Open)
# ===========================================================================

@app.post("/stream/start", status_code=status.HTTP_200_OK, dependencies=[Depends(verify_api_key)])
def stream_start(req: StreamStartRequest):
    """
    POST /stream/start — Start a background live-inference stream.
    Validates all file paths, model paths, and camera sources against traversal and injection.
    Requires API key authentication.
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
    )
    if not result["started"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=result.get("error", "Failed to start stream"),
        )
    return result


@app.post("/stream/stop", status_code=status.HTTP_200_OK, dependencies=[Depends(verify_api_key)])
def stream_stop():
    """POST /stream/stop — Stop the running stream. Requires API key authentication."""
    return stop_stream()


@app.get("/stream/status")
def stream_status_endpoint():
    """GET /stream/status — Returns current stream state."""
    return stream_status()


@app.get("/stream/mjpeg")
def stream_mjpeg():
    """
    GET /stream/mjpeg — MJPEG multipart/x-mixed-replace stream.
    Capped to MAX_MJPEG_CLIENTS to prevent socket exhaustion.
    """
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
    Validated against path traversal. Guarded by a hardware capture lock.
    """
    safe_src_str = validate_media_source(source)

    try:
        import cv2
    except ImportError:
        raise HTTPException(status_code=503, detail="cv2 not available on this server.")

    src = int(safe_src_str) if safe_src_str.isdigit() else safe_src_str

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

        ret, frame = cap.read()
        cap.release()

    if not ret or frame is None:
        raise HTTPException(
            status_code=422,
            detail=f"Source opened but produced no frames: {source!r}",
        )

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
# Zone Management Endpoints (List Open; Save/Delete Authenticated)
# ===========================================================================

@app.get("/zones")
def list_zones():
    """
    GET /zones — List all saved zone configs.
    Returns [{camera_id, zone_id, point_count, polygon, file_path, filename}]
    Includes full polygon coordinate array so dashboard 'Load' button works.
    """
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


@app.post("/zones", status_code=status.HTTP_201_CREATED, dependencies=[Depends(verify_api_key)])
def save_zone(req: ZoneSaveRequest):
    """
    POST /zones — Save a new zone config JSON.
    Strictly validates identifiers and file paths against traversal.
    Requires API key authentication.
    """
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

    logger.info("[audit] Saved zone config: %s (%d points)", filename, len(req.polygon))

    return {
        "saved": True,
        "filename": filename,
        "file_path": rel_path,
        "camera_id": cam_id,
        "zone_id": zone_id,
        "point_count": len(req.polygon),
        "polygon": zone_data["polygon"],
    }


@app.delete("/zones/{camera_id}/{zone_id}", status_code=status.HTTP_200_OK, dependencies=[Depends(verify_api_key)])
def delete_zone(camera_id: str, zone_id: str):
    """
    DELETE /zones/{camera_id}/{zone_id} — Remove a saved zone config file.
    Validates against path traversal. Requires API key authentication.
    """
    cam_id = validate_identifier(camera_id, "camera_id")
    zid = validate_identifier(zone_id, "zone_id")

    filename = f"{cam_id}_{zid}.json"
    filepath = validate_safe_filename(filename, ZONES_DIR)

    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Zone file not found: {filename}")

    filepath.unlink()
    logger.info("[audit] Deleted zone config: %s", filename)
    return {"deleted": True, "filename": filename}


# =========================================================================
# Subprocess Management Endpoints (Control Panel)
# List/Logs Open; Start/Stop Authenticated
# =========================================================================

@app.get("/processes", status_code=status.HTTP_200_OK)
def list_managed_processes():
    """List all managed background subprocesses and their status."""
    return get_process_manager().list_processes()


@app.post("/processes/{name}/start", status_code=status.HTTP_200_OK, dependencies=[Depends(verify_api_key)])
def start_managed_process(name: str, req: Optional[ProcessStartRequest] = None):
    """
    Start a named managed process (federated_demo or zone_pipeline).
    Requires API key authentication.
    """
    if name not in ("federated_demo", "zone_pipeline"):
        raise HTTPException(status_code=404, detail=f"Unknown process '{name}'.")

    try:
        source = req.source if req else None
        return get_process_manager().start_process(name, source=source)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/processes/{name}/stop", status_code=status.HTTP_200_OK, dependencies=[Depends(verify_api_key)])
def stop_managed_process(name: str):
    """
    Stop a named managed process and confirm all its child processes have terminated.
    Requires API key authentication.
    """
    if name not in ("federated_demo", "zone_pipeline"):
        raise HTTPException(status_code=404, detail=f"Unknown process '{name}'.")

    try:
        return get_process_manager().stop_process(name)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/processes/{name}/logs", status_code=status.HTTP_200_OK)
def get_managed_process_logs(name: str, tail: int = Query(default=500, ge=1, le=1000)):
    """Fetch bounded recent logs for a managed process."""
    if name not in ("federated_demo", "zone_pipeline"):
        raise HTTPException(status_code=404, detail=f"Unknown process '{name}'.")

    try:
        return get_process_manager().get_logs(name, tail=tail)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


# =========================================================================
# Data Retention / Storage Cleanup Endpoint
# =========================================================================

@app.post(
    "/retention/cleanup",
    response_model=RetentionCleanupResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(verify_api_key)],
)
def trigger_retention_cleanup(
    req: Optional[RetentionCleanupRequest] = None,
    db: Session = Depends(get_db),
):
    """
    POST /retention/cleanup — Trigger automated cleanup of aged events and video clips.
    Requires API key authentication.
    """
    max_days = req.max_age_days if req else None
    max_events = req.max_events if req else None

    result = cleanup_old_records(db, max_age_days=max_days, max_events=max_events)
    return RetentionCleanupResponse(**result)


# =========================================================================
# Static Files — Single-Process Dashboard Serving
# Mounted AFTER all API routes so it does not shadow API endpoints.
# =========================================================================
_DASHBOARD_DIR = REPO_ROOT / "dashboard"
if _DASHBOARD_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(_DASHBOARD_DIR), html=True), name="dashboard")
