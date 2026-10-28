import sys
from pathlib import Path
import pytest

# Add repo root to sys.path for test discovery
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(autouse=True)
def bypass_auth_for_legacy_tests():
    """
    Allow pre-existing unit and integration tests written before security hardening
    to execute without mandatory X-API-Key headers.
    Security and production-readiness tests explicitly manage their own auth headers and overrides.
    """
    from cloud.backend.main import app
    from cloud.backend.security import verify_api_key

    app.dependency_overrides[verify_api_key] = lambda: True
    yield
    app.dependency_overrides.pop(verify_api_key, None)
