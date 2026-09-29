"""
cloud/backend/security.py
=========================
Security hardening module for the AEGIS Safety System:
1. API Key authentication dependency for mutating endpoints.
2. Strict input validation against path traversal, command injection, and SSRF.
3. Operator identification and verification.
"""

import hmac
import logging
import re
from pathlib import Path
from typing import Optional
from fastapi import Header, HTTPException, Query, Request, status

from cloud.backend.config import get_settings, REPO_ROOT

logger = logging.getLogger("aegis.security")

# Strict identifier regex: alphanumeric, underscores, hyphens, and dots only (no path separators)
_SAFE_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.]+$")


def verify_api_key(
    request: Request,
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None),
    api_key: Optional[str] = Query(None),
) -> bool:
    """
    FastAPI dependency ensuring state-changing endpoints are protected by the shared secret API key.
    Checks:
    - 'X-API-Key' header
    - 'Authorization: Bearer <key>' header
    - 'api_key' query parameter
    """
    settings = get_settings()
    if not settings.AUTH_ENABLED:
        return True

    client_key: Optional[str] = None
    if x_api_key:
        client_key = x_api_key.strip()
    elif authorization and authorization.lower().startswith("bearer "):
        client_key = authorization[7:].strip()
    elif api_key:
        client_key = api_key.strip()

    expected_key = settings.API_KEY.strip()

    if not client_key:
        logger.warning(
            "[auth] Rejected %s %s: Missing API key from %s",
            request.method,
            request.url.path,
            request.client.host if request.client else "unknown",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Missing API key. Provide 'X-API-Key' header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(client_key.encode("utf-8"), expected_key.encode("utf-8")):
        logger.warning(
            "[auth] Rejected %s %s: Invalid API key from %s",
            request.method,
            request.url.path,
            request.client.host if request.client else "unknown",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return True


def validate_identifier(val: str, field_name: str = "identifier", min_len: int = 1, max_len: int = 64) -> str:
    """
    Validate that an identifier (camera_id, zone_id, tracked_id, operator_id) is safe:
    - Length between min_len and max_len
    - Alphanumeric, hyphen, underscore, dot only
    - Strictly no path traversal (.., /, \\) or shell metacharacters
    """
    if not isinstance(val, str):
        raise HTTPException(status_code=422, detail=f"Invalid {field_name}: Must be a string.")

    cleaned = val.strip()
    if len(cleaned) < min_len or len(cleaned) > max_len:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid {field_name}: Length must be between {min_len} and {max_len} characters.",
        )

    if not _SAFE_ID_REGEX.match(cleaned) or ".." in cleaned:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid {field_name}: Must be alphanumeric, underscores, hyphens, or dots only. No traversal.",
        )

    return cleaned


def validate_safe_filename(name: str, allowed_dir: Path) -> Path:
    """
    Ensure a filename resides strictly inside allowed_dir with no directory traversal.
    """
    if not name or ".." in name or "/" in name or "\\" in name:
        raise HTTPException(status_code=422, detail="Invalid filename: Directory traversal characters not allowed.")

    resolved_dir = allowed_dir.resolve()
    target_path = (resolved_dir / name).resolve()

    try:
        # Python 3.9+ is_relative_to
        target_path.relative_to(resolved_dir)
    except ValueError:
        raise HTTPException(status_code=422, detail="Path traversal attempt detected.")

    return target_path


def validate_media_source(source: str) -> str:
    """
    Validate video or camera source for inference streams:
    - Integer camera index (0..99)
    - Safe relative file path under repository (e.g. demo/videos/..., clips/...)
    - Clean RTSP/HTTP/HTTPS URL with no whitespace or shell metacharacters
    """
    source = str(source).strip()
    if not source:
        raise HTTPException(status_code=422, detail="Source cannot be empty.")

    # 1. Integer camera index
    if source.isdigit():
        idx = int(source)
        if idx < 0 or idx > 99:
            raise HTTPException(status_code=422, detail="Camera index must be between 0 and 99.")
        return str(idx)

    # 2. Network URL (RTSP / HTTP / HTTPS)
    if source.startswith(("rtsp://", "http://", "https://")):
        if re.search(r"[\s;&|`$<>\\]", source):
            raise HTTPException(status_code=422, detail="URL contains invalid or unsafe characters.")
        return source

    # 3. Local file path
    if re.search(r"[;&|`$<>]", source) or ".." in source:
        raise HTTPException(status_code=422, detail="Invalid file path: Traversal or shell characters not allowed.")

    clean_path = Path(source).as_posix()
    resolved = (REPO_ROOT / clean_path).resolve()

    # Must resolve within repository
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError:
        raise HTTPException(status_code=422, detail="Video file path must reside within the repository root.")

    if not resolved.exists():
        raise HTTPException(status_code=422, detail=f"Source video file does not exist: {clean_path}")

    return str(clean_path)


def validate_model_path(model_path: Optional[str]) -> Optional[str]:
    """Validate that custom model path is a safe .pt file within repo root."""
    if not model_path:
        return None

    path_str = str(model_path).strip()
    if ".." in path_str or re.search(r"[;&|`$<>]", path_str):
        raise HTTPException(status_code=422, detail="Invalid model path: Traversal not allowed.")

    resolved = (REPO_ROOT / Path(path_str).as_posix()).resolve()
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError:
        raise HTTPException(status_code=422, detail="Model path must reside within repository.")

    if not resolved.name.endswith(".pt"):
        raise HTTPException(status_code=422, detail="Model file must have a .pt extension.")

    if not resolved.exists():
        raise HTTPException(status_code=422, detail=f"Model file not found: {path_str}")

    return str(resolved)


def validate_zone_config_path(zone_path: Optional[str]) -> Optional[str]:
    """Validate that zone configuration path is a safe .json file within zones directory."""
    if not zone_path:
        return None

    path_str = str(zone_path).strip()
    if ".." in path_str or re.search(r"[;&|`$<>]", path_str):
        raise HTTPException(status_code=422, detail="Invalid zone config path: Traversal not allowed.")

    resolved = (REPO_ROOT / Path(path_str).as_posix()).resolve()
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError:
        raise HTTPException(status_code=422, detail="Zone config path must reside within repository.")

    if not resolved.name.endswith(".json"):
        raise HTTPException(status_code=422, detail="Zone config must have a .json extension.")

    if not resolved.exists():
        raise HTTPException(status_code=422, detail=f"Zone config file not found: {path_str}")

    return str(resolved)
