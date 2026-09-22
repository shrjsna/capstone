"""Run zone intrusion + PPE detection tests."""
import subprocess, sys, os, pathlib

repo = pathlib.Path(r"c:\Games\repo-setup\repo-setup")
os.chdir(repo)
venv_python = repo / "venv" / "Scripts" / "python.exe"

result = subprocess.run(
    [str(venv_python), "-m", "pytest",
     "edge/zone_intrusion/tests/",
     "tests/test_ppe_detection.py",
     "-v", "--tb=short"],
    capture_output=False
)
sys.exit(result.returncode)
