"""
cloud/backend/main.py
FastAPI application for Module D Cloud Backend.
"""

import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
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
from cloud.backend.stream_manager import (
    start_stream,
    stop_stream,
    stream_status,
    generate_mjpeg_frames,
    get_latest_frame_jpeg,
)

# Zone storage directory — persists zone configs as JSON files
_REPO_ROOT = Path(__file__).resolve().parents[2]
ZONES_DIR = _REPO_ROOT / "edge" / "zone_intrusion" / "zones"


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


# ===========================================================================
# Pydantic models for new endpoints
# ===========================================================================

class StreamStartRequest(BaseModel):
    source: str                          # "0", file path, or RTSP/HTTP URL
    mode: str = "ppe"                    # "ppe" | "zone_intrusion"
    model_path: Optional[str] = None     # defaults to ppe_final_v4.pt
    zone_config_path: Optional[str] = None
    camera_id: str = "stream_cam"
    zone_id: str = "stream_zone"
    debounce_frames: int = 3
    conf_threshold: float = 0.25


class ZoneSaveRequest(BaseModel):
    camera_id: str
    zone_id: str
    polygon: List[List[float]]           # [[x,y], ...] in pixel coords
    frame_width: Optional[int] = None
    frame_height: Optional[int] = None


# ===========================================================================
# Stream endpoints
# ===========================================================================

@app.post("/stream/start", status_code=status.HTTP_200_OK)
def stream_start(req: StreamStartRequest):
    """
    POST /stream/start — Start a background live-inference stream.
    Stops any currently running stream first.
    Body: {source, mode, model_path?, zone_config_path?, camera_id, zone_id, debounce_frames, conf_threshold}
    Returns: {started, error, source, mode}
    """
    # Build the backend's own /events URL so the stream worker can self-post events
    events_api_url = "http://127.0.0.1:8000/events"

    result = start_stream(
        source=req.source,
        mode=req.mode,
        model_path=req.model_path,
        zone_config_path=req.zone_config_path,
        camera_id=req.camera_id,
        zone_id=req.zone_id,
        events_api_url=events_api_url,
        debounce_frames=req.debounce_frames,
        conf_threshold=req.conf_threshold,
    )
    if not result["started"]:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=result.get("error", "Failed to start stream"))
    return result


@app.post("/stream/stop", status_code=status.HTTP_200_OK)
def stream_stop():
    """POST /stream/stop — Stop the currently running stream."""
    return stop_stream()


@app.get("/stream/status")
def stream_status_endpoint():
    """GET /stream/status — Returns current stream state."""
    return stream_status()


@app.get("/stream/mjpeg")
def stream_mjpeg():
    """
    GET /stream/mjpeg — MJPEG multipart/x-mixed-replace stream.
    Point an <img> tag src at this URL to display continuous live video.
    Returns a placeholder frame when no stream is running.
    """
    return StreamingResponse(
        generate_mjpeg_frames(),
        media_type="multipart/x-mixed-replace; boundary=aegisframe",
    )


@app.get("/stream/latest-frame")
def stream_latest_frame():
    """
    GET /stream/latest-frame — Returns the single latest annotated JPEG frame.
    Polling fallback: call every 200-500ms and refresh an <img> src.
    Returns 200 + image/jpeg (placeholder when no stream is running).
    """
    jpeg = get_latest_frame_jpeg()
    return StreamingResponse(iter([jpeg]), media_type="image/jpeg")


# ===========================================================================
# Capture-frame endpoint (for Zone Draw tool — grab one still frame)
# ===========================================================================

@app.get("/capture-frame")
def capture_frame(source: str = Query(..., description="Video source: webcam index, file path, or RTSP URL")):
    """
    GET /capture-frame?source=... — Open the source briefly via cv2, grab ONE
    frame, encode as JPEG, return it, and immediately release the capture.
    Used by the dashboard's Draw Zone tool to get a background frame for
    polygon calibration.
    """
    try:
        import cv2
    except ImportError:
        raise HTTPException(status_code=503, detail="cv2 not available on this server.")

    src = int(source) if source.isdigit() else source
    cap = cv2.VideoCapture(src)

    if not cap.isOpened():
        raise HTTPException(
            status_code=422,
            detail=f"Could not open source: {source!r}. Check the URL, path, or camera index."
        )

    # Skip a few frames to let auto-exposure settle (especially for webcams)
    for _ in range(3):
        cap.read()

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        raise HTTPException(
            status_code=422,
            detail=f"Source opened but produced no frames: {source!r}"
        )

    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to encode frame as JPEG.")

    return StreamingResponse(iter([buf.tobytes()]), media_type="image/jpeg",
                             headers={"X-Frame-Width": str(frame.shape[1]),
                                      "X-Frame-Height": str(frame.shape[0])})


# ===========================================================================
# Zone management endpoints
# ===========================================================================

@app.get("/zones")
def list_zones():
    """
    GET /zones — List all saved zone configs.
    Returns [{camera_id, zone_id, point_count, file_path}] for each JSON in the zones dir.
    """
    ZONES_DIR.mkdir(parents=True, exist_ok=True)
    zones = []
    for f in sorted(ZONES_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            try:
                rel_path = str(f.relative_to(_REPO_ROOT))
            except ValueError:
                rel_path = str(f)
            zones.append({
                "camera_id": data.get("camera_id", ""),
                "zone_id": data.get("zone_id", ""),
                "point_count": len(data.get("polygon", [])),
                "file_path": rel_path,
                "filename": f.name,
            })
        except Exception:
            pass
    return zones


@app.post("/zones", status_code=status.HTTP_201_CREATED)
def save_zone(req: ZoneSaveRequest):
    """
    POST /zones — Save a new zone config.
    Writes the exact same JSON structure as draw_zone.py (and expected by zone_check.py).
    If a zone with the same camera_id + zone_id already exists it is overwritten.
    Body: {camera_id, zone_id, polygon: [[x,y],...], frame_width?, frame_height?}
    """
    if len(req.polygon) < 3:
        raise HTTPException(status_code=422, detail="A zone polygon needs at least 3 points.")

    ZONES_DIR.mkdir(parents=True, exist_ok=True)

    # File name: <camera_id>_<zone_id>.json  (matches draw_zone.py naming convention)
    safe_cam = req.camera_id.replace("/", "_").replace("\\", "_")
    safe_zone = req.zone_id.replace("/", "_").replace("\\", "_")
    filename = f"{safe_cam}_{safe_zone}.json"
    filepath = ZONES_DIR / filename

    zone_data: Dict[str, Any] = {
        "camera_id": req.camera_id,
        "zone_id": req.zone_id,
        "polygon": [[int(pt[0]), int(pt[1])] for pt in req.polygon],
    }
    if req.frame_width:
        zone_data["frame_width"] = req.frame_width
    if req.frame_height:
        zone_data["frame_height"] = req.frame_height

    filepath.write_text(json.dumps(zone_data, indent=2), encoding="utf-8")

    try:
        rel_path = str(filepath.relative_to(_REPO_ROOT))
    except ValueError:
        rel_path = str(filepath)

    return {
        "saved": True,
        "filename": filename,
        "file_path": rel_path,
        "camera_id": req.camera_id,
        "zone_id": req.zone_id,
        "point_count": len(req.polygon),
    }


@app.delete("/zones/{camera_id}/{zone_id}", status_code=status.HTTP_200_OK)
def delete_zone(camera_id: str, zone_id: str):
    """DELETE /zones/{camera_id}/{zone_id} — Remove a saved zone config file."""
    safe_cam = camera_id.replace("/", "_").replace("\\", "_")
    safe_zone = zone_id.replace("/", "_").replace("\\", "_")
    filename = f"{safe_cam}_{safe_zone}.json"
    filepath = ZONES_DIR / filename

    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Zone file not found: {filename}")

    filepath.unlink()
    return {"deleted": True, "filename": filename}

