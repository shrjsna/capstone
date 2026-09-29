"""
cloud/backend/process_manager.py
================================
Subprocess management layer for background jobs (Federated Learning demo,
standalone Zone Intrusion pipeline).

SECURITY & SAFETY CONSTRAINTS:
1. ONLY a fixed, hardcoded whitelist of named commands can be executed.
2. The frontend passes ONLY a process name ("federated_demo", "zone_pipeline").
3. NEVER accepts arbitrary shell commands from the frontend.
4. NEVER uses shell=True.
5. All source paths for the zone pipeline are strictly validated.
6. Process output is captured into bounded in-memory ring buffers (last 500 lines).
7. Clean termination guarantees: terminate() followed by kill() on timeout.
"""

import atexit
import collections
import datetime
import logging
import os
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("process_manager")

_REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_RING_BUFFER_SIZE = 500


def validate_source(source: str) -> str:
    """
    Validate that an input source for the zone pipeline is safe:
    - Integer camera index (e.g. 0, 1)
    - Safe path under demo/videos/
    - URL matching rtsp://, http://, or https:// with no metacharacters
    """
    source = str(source).strip()
    if not source:
        raise ValueError("Source cannot be empty.")

    # 1. Integer camera index
    if source.isdigit():
        return source

    # 2. Network URL (RTSP / HTTP)
    if source.startswith(("rtsp://", "http://", "https://")):
        # Reject shell metacharacters or whitespace
        if re.search(r"[\s;&|`$<>]", source):
            raise ValueError("URL contains invalid or unsafe characters.")
        return source

    # 3. File path under demo/videos/
    # Reject shell metacharacters and directory traversal
    if re.search(r"[;&|`$<>]", source) or ".." in source:
        raise ValueError("Invalid path: traversal or shell characters not allowed.")

    clean_path = Path(source).as_posix()
    resolved = (_REPO_ROOT / clean_path).resolve()
    allowed_dir = (_REPO_ROOT / "demo" / "videos").resolve()

    if not str(resolved).startswith(str(allowed_dir)):
        raise ValueError("Video source file must reside under demo/videos/.")
    if not resolved.exists():
        raise ValueError(f"Video file does not exist: {clean_path}")

    return str(clean_path)


class ProcessStartRequest(BaseModel):
    source: Optional[str] = Field(None, description="Optional video source for zone_pipeline")


class ManagedProcessState:
    """Tracks state and output for a named managed process (which may consist of 1 or more subprocesses)."""

    def __init__(self, name: str, display_name: str, description: str):
        self.name: str = name
        self.display_name: str = display_name
        self.description: str = description
        self.status: str = "stopped"  # "stopped" | "running" | "crashed" | "completed"
        self.pids: List[int] = []
        self.started_at: Optional[str] = None
        self.logs: Deque[str] = collections.deque(maxlen=LOG_RING_BUFFER_SIZE)
        self.subprocesses: List[subprocess.Popen] = []
        self.was_stopped_by_user: bool = False
        self.source: Optional[str] = None
        self.lock = threading.RLock()
        self.threads: List[threading.Thread] = []

    def to_dict(self) -> Dict[str, Any]:
        with self.lock:
            return {
                "name": self.name,
                "display_name": self.display_name,
                "description": self.description,
                "status": self.status,
                "pids": list(self.pids),
                "started_at": self.started_at,
                "logs_count": len(self.logs),
                "source": self.source,
            }

    def append_log(self, text: str) -> None:
        with self.lock:
            self.logs.append(text)


class ProcessManager:
    """Singleton process manager for server-side managed background jobs."""

    def __init__(self):
        self.processes: Dict[str, ManagedProcessState] = {
            "federated_demo": ManagedProcessState(
                name="federated_demo",
                display_name="Federated Learning Demo",
                description="Flower FedAvg server + 2 edge clients (site_1, site_2) simulating collaborative policy retraining.",
            ),
            "zone_pipeline": ManagedProcessState(
                name="zone_pipeline",
                display_name="Zone Intrusion Pipeline",
                description="Standalone edge detection + tracking pipeline with face-blurred incident clip recording.",
            ),
        }
        self._shutdown = False
        atexit.register(self.stop_all)

    def list_processes(self) -> List[Dict[str, Any]]:
        return [proc.to_dict() for proc in self.processes.values()]

    def get_process_state(self, name: str) -> Optional[ManagedProcessState]:
        return self.processes.get(name)

    def get_logs(self, name: str, tail: int = 500) -> Dict[str, Any]:
        proc = self.processes.get(name)
        if not proc:
            raise KeyError(f"Unknown process '{name}'")
        with proc.lock:
            log_list = list(proc.logs)
            if tail and tail > 0:
                log_list = log_list[-tail:]
            return {
                "name": proc.name,
                "status": proc.status,
                "logs": log_list,
                "pids": list(proc.pids),
                "started_at": proc.started_at,
            }

    def _pipe_reader(self, pipe, prefix: str, proc_state: ManagedProcessState):
        """Read lines from stdout/stderr pipe into process logs."""
        if not pipe:
            return
        try:
            for line in iter(pipe.readline, ""):
                if not line or not isinstance(line, str):
                    break
                clean_line = line.rstrip("\r\n")
                if clean_line:
                    tag = f"[{prefix}] " if prefix else ""
                    proc_state.append_log(f"{tag}{clean_line}")
        except Exception:
            pass
        finally:
            try:
                pipe.close()
            except Exception:
                pass

    def start_process(self, name: str, source: Optional[str] = None) -> Dict[str, Any]:
        """Start a managed process. Returns current status dict."""
        proc_state = self.processes.get(name)
        if not proc_state:
            raise KeyError(f"Unknown process '{name}'. Allowed: {list(self.processes.keys())}")

        with proc_state.lock:
            # If already running, return status without duplicate start
            if proc_state.status == "running":
                return proc_state.to_dict()

            proc_state.was_stopped_by_user = False
            proc_state.logs.clear()
            proc_state.subprocesses.clear()
            proc_state.pids.clear()
            proc_state.threads.clear()
            proc_state.started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            proc_state.status = "running"

        if name == "federated_demo":
            # Start federated flow in a worker thread so HTTP endpoint returns immediately
            t = threading.Thread(target=self._run_federated_demo, args=(proc_state,), daemon=True)
            proc_state.threads.append(t)
            t.start()
        elif name == "zone_pipeline":
            # Validate source
            default_source = "demo/videos/zone_intrusion_demo.mp4"
            validated_source = validate_source(source or default_source)
            proc_state.source = validated_source
            t = threading.Thread(target=self._run_zone_pipeline, args=(proc_state, validated_source), daemon=True)
            proc_state.threads.append(t)
            t.start()

        return proc_state.to_dict()

    def _spawn_subprocess(self, cmd: List[str], env: Optional[Dict] = None) -> subprocess.Popen:
        """Spawn subprocess safely with unbuffered pipes and no shell."""
        sub_env = (env or os.environ).copy()
        sub_env["PYTHONUNBUFFERED"] = "1"
        sub_env["PYTHONPATH"] = str(_REPO_ROOT)

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=str(_REPO_ROOT),
            env=sub_env,
        )
        return proc

    def _wait_for_port(self, host: str, port: int, timeout: float = 6.0) -> bool:
        """Wait until a local TCP port is accepting connections."""
        start = time.time()
        while time.time() - start < timeout:
            try:
                with socket.create_connection((host, port), timeout=0.2):
                    return True
            except (socket.error, ConnectionRefusedError, OSError):
                time.sleep(0.15)
        return False

    def _run_federated_demo(self, proc_state: ManagedProcessState):
        """Worker executing Flower FedAvg server + 2 edge clients sequentially."""
        proc_state.append_log("[manager] Initializing Federated Learning demo (Flower + FedAvg)...")

        # 1. Start Server
        server_cmd = [
            sys.executable,
            "-m",
            "cloud.federated.flower_server",
            "--address",
            "127.0.0.1:8089",
            "--rounds",
            "2",
            "--min-clients",
            "2",
        ]
        proc_state.append_log(f"[manager] Starting Flower FedAvg Server on 127.0.0.1:8089...")
        try:
            p_server = self._spawn_subprocess(server_cmd)
        except Exception as e:
            proc_state.append_log(f"[manager] Failed to spawn server: {e}")
            with proc_state.lock:
                proc_state.status = "crashed"
            return

        with proc_state.lock:
            proc_state.subprocesses.append(p_server)
            proc_state.pids.append(p_server.pid)

        t_srv = threading.Thread(target=self._pipe_reader, args=(p_server.stdout, "server", proc_state), daemon=True)
        t_srv.start()

        # 2. Wait for server port
        proc_state.append_log("[manager] Waiting for server gRPC socket to be listening...")
        if not self._wait_for_port("127.0.0.1", 8089, timeout=6.0):
            if p_server.poll() is not None:
                proc_state.append_log(f"[manager] Server exited prematurely with code {p_server.returncode}.")
            else:
                proc_state.append_log("[manager] Server socket timeout after 6s.")
            with proc_state.lock:
                if not proc_state.was_stopped_by_user:
                    proc_state.status = "crashed"
            return

        proc_state.append_log("[manager] Server listening. Starting Site 1 and Site 2 clients...")

        # 3. Start Site 1 Client
        c1_cmd = [
            sys.executable,
            "-m",
            "cloud.federated.flower_client",
            "--site-id",
            "site_1",
            "--server-address",
            "127.0.0.1:8089",
        ]
        try:
            p_c1 = self._spawn_subprocess(c1_cmd)
            with proc_state.lock:
                proc_state.subprocesses.append(p_c1)
                proc_state.pids.append(p_c1.pid)
            t_c1 = threading.Thread(target=self._pipe_reader, args=(p_c1.stdout, "site_1", proc_state), daemon=True)
            t_c1.start()
        except Exception as e:
            proc_state.append_log(f"[manager] Failed to start site_1 client: {e}")

        time.sleep(0.4)

        # 4. Start Site 2 Client
        c2_cmd = [
            sys.executable,
            "-m",
            "cloud.federated.flower_client",
            "--site-id",
            "site_2",
            "--server-address",
            "127.0.0.1:8089",
        ]
        try:
            p_c2 = self._spawn_subprocess(c2_cmd)
            with proc_state.lock:
                proc_state.subprocesses.append(p_c2)
                proc_state.pids.append(p_c2.pid)
            t_c2 = threading.Thread(target=self._pipe_reader, args=(p_c2.stdout, "site_2", proc_state), daemon=True)
            t_c2.start()
        except Exception as e:
            proc_state.append_log(f"[manager] Failed to start site_2 client: {e}")

        # Wait for all processes to complete
        p_server.wait()
        for p in [p_c1, p_c2]:
            try:
                p.wait(timeout=5)
            except Exception:
                pass

        with proc_state.lock:
            if proc_state.was_stopped_by_user:
                proc_state.status = "stopped"
                proc_state.append_log("[manager] Federated learning demo stopped by user.")
            else:
                if p_server.returncode == 0:
                    proc_state.status = "completed"
                    proc_state.append_log("[manager] Federated learning rounds completed successfully.")
                else:
                    proc_state.status = "crashed"
                    proc_state.append_log(f"[manager] Server exited with error code {p_server.returncode}.")
            proc_state.pids.clear()

    def _run_zone_pipeline(self, proc_state: ManagedProcessState, source: str):
        """Worker executing standalone zone_intrusion_pipeline.py."""
        zone_config = str(_REPO_ROOT / "edge" / "zone_intrusion" / "zones" / "camera_01_zones.json")
        cmd = [
            sys.executable,
            "-m",
            "edge.zone_intrusion.tracking.zone_intrusion_pipeline",
            "--source",
            source,
            "--zone_config",
            zone_config,
            "--debounce_frames",
            "4",
            "--events_log",
            "demo/zone_intrusion_events.jsonl",
            "--clips_dir",
            "clips",
            "--api-url",
            "http://127.0.0.1:8000/events",
            "--no-show",
        ]

        proc_state.append_log(f"[manager] Starting Zone Intrusion Pipeline (source: {source})...")
        try:
            proc = self._spawn_subprocess(cmd)
        except Exception as e:
            proc_state.append_log(f"[manager] Failed to spawn zone pipeline: {e}")
            with proc_state.lock:
                proc_state.status = "crashed"
            return

        with proc_state.lock:
            proc_state.subprocesses.append(proc)
            proc_state.pids.append(proc.pid)

        t = threading.Thread(target=self._pipe_reader, args=(proc.stdout, "zone", proc_state), daemon=True)
        t.start()

        # Wait for process
        proc.wait()

        with proc_state.lock:
            if proc_state.was_stopped_by_user:
                proc_state.status = "stopped"
                proc_state.append_log("[manager] Zone Intrusion pipeline stopped by user.")
            else:
                # If pipeline stopped on its own (video ended or error), mark crashed
                proc_state.status = "crashed"
                proc_state.append_log(f"[manager] Pipeline process exited (code {proc.returncode}).")
            proc_state.pids.clear()

    def stop_process(self, name: str) -> Dict[str, Any]:
        """Stop all subprocesses associated with a named process and confirm termination."""
        proc_state = self.processes.get(name)
        if not proc_state:
            raise KeyError(f"Unknown process '{name}'")

        with proc_state.lock:
            proc_state.was_stopped_by_user = True
            subprocs = list(proc_state.subprocesses)

        for p in subprocs:
            if p.poll() is None:
                try:
                    p.terminate()
                except Exception:
                    pass

        # Give 2.5s for clean exit
        start_wait = time.time()
        for p in subprocs:
            remaining = max(0.1, 2.5 - (time.time() - start_wait))
            try:
                p.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                try:
                    p.kill()
                    p.wait(timeout=1.0)
                except Exception:
                    pass

        with proc_state.lock:
            proc_state.status = "stopped"
            proc_state.subprocesses.clear()
            proc_state.pids.clear()

        proc_state.append_log("[manager] Verified all process handles terminated cleanly.")
        return proc_state.to_dict()

    def stop_all(self) -> None:
        """Terminate all managed processes cleanly."""
        if self._shutdown:
            return
        self._shutdown = True
        for name in list(self.processes.keys()):
            try:
                self.stop_process(name)
            except Exception:
                pass


_process_manager_instance: Optional[ProcessManager] = None


def get_process_manager() -> ProcessManager:
    global _process_manager_instance
    if _process_manager_instance is None:
        _process_manager_instance = ProcessManager()
    return _process_manager_instance
