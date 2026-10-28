"""
cloud/backend/config.py
=======================
Centralized configuration for the AEGIS Industrial Safety System.
Loads settings from environment variables with production-safe defaults.
"""

import os
import socket
from pathlib import Path
from typing import List

# Repository Root
REPO_ROOT = Path(__file__).resolve().parents[2]


def get_lan_ip() -> str:
    """Detect the local machine's primary IPv4 address on the local network."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


class Settings:
    """Application settings with environment variable overrides."""

    def __init__(self):
        # Server host & port
        self.HOST: str = os.getenv("AEGIS_HOST", "0.0.0.0")
        self.PORT: int = int(os.getenv("AEGIS_PORT", "8000"))

        # Authentication: shared secret API key
        self.API_KEY: str = os.getenv("AEGIS_API_KEY", "aegis-secret-key-2026")
        self.AUTH_ENABLED: bool = os.getenv("AEGIS_AUTH_ENABLED", "true").lower() in ("true", "1", "yes")

        # Data Retention & Cleanup
        self.RETENTION_DAYS: int = int(os.getenv("AEGIS_RETENTION_DAYS", "7"))
        self.MAX_STORED_EVENTS: int = int(os.getenv("AEGIS_MAX_EVENTS", "5000"))
        self.CLIPS_DIR: Path = REPO_ROOT / os.getenv("AEGIS_CLIPS_DIR", "clips")
        self.ZONES_DIR: Path = REPO_ROOT / "edge" / "zone_intrusion" / "zones"

        # Rate Limiting & Resource Caps
        self.MAX_MJPEG_CLIENTS: int = int(os.getenv("AEGIS_MAX_MJPEG_CLIENTS", "10"))

    @property
    def cors_origins(self) -> List[str]:
        """Compute allowed CORS origins."""
        raw = os.getenv("CORS_ALLOWED_ORIGINS")
        if raw:
            return [o.strip() for o in raw.split(",") if o.strip()]

        lan_ip = get_lan_ip()
        origins = [
            f"http://localhost:{self.PORT}",
            f"http://127.0.0.1:{self.PORT}",
            "http://localhost:8080",
            "http://127.0.0.1:8080",
        ]
        if lan_ip not in ("127.0.0.1", "localhost"):
            origins.extend([
                f"http://{lan_ip}:{self.PORT}",
                f"http://{lan_ip}:8080",
            ])
        return sorted(list(set(origins)))


_settings = Settings()


def get_settings() -> Settings:
    """Return singleton configuration settings."""
    return _settings
