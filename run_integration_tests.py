"""Run integration tests only."""
import subprocess, sys, pathlib, os
repo = pathlib.Path(r"c:\Games\repo-setup\repo-setup")
os.chdir(repo)
venv_python = repo / "venv" / "Scripts" / "python.exe"
result = subprocess.run(
    [str(venv_python), "-m", "pytest", "tests/test_integration.py", "-v", "--tb=short"],
    capture_output=False
)
sys.exit(result.returncode)
