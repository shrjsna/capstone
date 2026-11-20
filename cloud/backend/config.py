"""
cloud/backend/config.py
=======================
Centralized configuration for the AEGIS Industrial Safety System.
Loads settings from environment variables with production-safe defaults.
"""

import logging
import os
import socket
from pathlib import Path
from typing import List

logger = logging.getLogger("aegis.config")

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

        # Legacy auth settings deprecation handling
        if "AEGIS_AUTH_ENABLED" in os.environ:
            logger.warning(
                "[config] Notice: AEGIS_AUTH_ENABLED is deprecated and ignored; "
                "Role-Based Access Control is permanently enabled."
            )
        if "AEGIS_API_KEY" in os.environ:
            logger.warning(
                "[config] Notice: AEGIS_API_KEY shared secret is deprecated; "
                "Use scoped edge keys or user session credentials."
            )

        # RBAC & Session Tunables
        self.SESSION_IDLE_MIN: int = int(os.getenv("AEGIS_SESSION_IDLE_MIN", "30"))
        self.SESSION_ABSOLUTE_HOURS: int = int(os.getenv("AEGIS_SESSION_ABSOLUTE_HOURS", "12"))
        self.COOKIE_SECURE: bool = os.getenv("AEGIS_COOKIE_SECURE", "false").lower() in ("true", "1", "yes")
        self.LOGIN_MAX_FAILURES: int = int(os.getenv("AEGIS_LOGIN_MAX_FAILURES", "5"))
        self.LOGIN_LOCKOUT_MINUTES: int = int(os.getenv("AEGIS_LOGIN_LOCKOUT_MINUTES", "5"))
        self.MIN_PASSWORD_LENGTH: int = int(os.getenv("AEGIS_MIN_PASSWORD_LENGTH", "12"))
        self.DOCS_ENABLED: bool = os.getenv("AEGIS_DOCS_ENABLED", "true").lower() in ("true", "1", "yes")

        # Proxy settings
        raw_proxies = os.getenv("AEGIS_TRUSTED_PROXIES", "")
        self.TRUSTED_PROXIES: List[str] = [p.strip() for p in raw_proxies.split(",") if p.strip()]

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
            origins = [o.strip() for o in raw.split(",") if o.strip()]
            if "*" in origins:
                raise ValueError(
                    "Wildcard '*' in CORS_ALLOWED_ORIGINS is rejected when cookie credentials are used. "
                    "Specify exact origins."
                )
            return origins

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
