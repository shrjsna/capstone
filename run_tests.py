"""Helper: run pytest suite using venv python and capture output."""
import subprocess, sys, os, pathlib

repo = pathlib.Path(r"c:\Games\repo-setup\repo-setup")
os.chdir(repo)

venv_python = repo / "venv" / "Scripts" / "python.exe"
if not venv_python.exists():
    venv_python = sys.executable  # fallback

result = subprocess.run(
    [str(venv_python), "-m", "pytest",
     "tests/test_setup.py",
     "tests/test_bandit.py",
     "tests/test_backend.py",
     "tests/test_dashboard.py",
     "tests/test_federated.py",
     "-v", "--tb=short"],
    capture_output=False
)
sys.exit(result.returncode)
