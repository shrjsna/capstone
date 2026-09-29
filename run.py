#!/usr/bin/env python3
"""
run.py
======
Single-command launcher for the AEGIS Industrial Safety System.

Starts the unified FastAPI backend + Dashboard static server on 0.0.0.0:8000,
prints local & LAN access URLs, polls /health to automatically open the browser,
and cleanly terminates all child workers/streams on Ctrl+C.
"""

import os
import signal
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

# Ensure repo root is on sys.path
_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def get_lan_ip() -> str:
    """Detect the local machine's primary IPv4 address on the local network."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Connect to a public IP to inspect routing socket (no packets are sent)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


def wait_and_open_browser(url: str, health_url: str, timeout: float = 15.0) -> None:
    """Poll the backend health endpoint until ready, then open the browser."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(health_url, timeout=0.6) as resp:
                if resp.status == 200:
                    time.sleep(0.3)
                    print(f"[*] Backend confirmed ready. Opening browser: {url}")
                    webbrowser.open(url)
                    return
        except Exception:
            time.sleep(0.25)
    print(f"[!] Server did not respond to /health within {timeout}s. Open manually: {url}")


def cleanup() -> None:
    """Guarantee all video stream threads and child subprocesses are reaped."""
    print("\n[*] Shutting down AEGIS Safety System...")
    try:
        from cloud.backend.stream_manager import stop_stream
        stop_stream()
    except Exception as e:
        pass

    try:
        from cloud.backend.process_manager import get_process_manager
        get_process_manager().stop_all()
    except Exception as e:
        pass
    print("[*] Cleanup complete. Exiting.")


def main():
    port = 8000
    host = "0.0.0.0"
    lan_ip = get_lan_ip()

    local_url = f"http://127.0.0.1:{port}"
    lan_url = f"http://{lan_ip}:{port}"
    health_url = f"http://127.0.0.1:{port}/health"

    banner = f"""
======================================================================
  AEGIS — Collaborative AI Safety Operations Console
======================================================================
  Localhost URL:   {local_url}
  LAN / Phone URL: {lan_url}
  Health Check:    {health_url}
  Press Ctrl+C to shut down all processes cleanly.
======================================================================
"""
    print(banner)

    # Spawn background thread to poll /health and launch browser
    browser_thread = threading.Thread(
        target=wait_and_open_browser,
        args=(local_url, health_url, 15.0),
        daemon=True,
    )
    browser_thread.start()

    # Register exit handlers
    def sig_handler(signum, frame):
        cleanup()
        sys.exit(0)

    try:
        signal.signal(signal.SIGINT, sig_handler)
        signal.signal(signal.SIGTERM, sig_handler)
    except Exception:
        pass

    try:
        import uvicorn
        uvicorn.run(
            "cloud.backend.main:app",
            host=host,
            port=port,
            log_level="info",
            reload=False,
        )
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()


if __name__ == "__main__":
    main()
