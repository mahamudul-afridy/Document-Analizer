import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("RATE_LIMIT_STORAGE", "memory://")
if os.environ.get("TEST_DATABASE_URL"):  # must be set before app settings are first imported
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
    os.environ["CELERY_EAGER"] = "true"  # run background jobs inline during integration tests
os.environ.setdefault("STORAGE_DIR", str(Path(__file__).parent / ".storage"))
os.environ.setdefault("EMBEDDINGS_ENABLED", "false")

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "generated"


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Synthetic invoices with known ground truth (generated once per machine)."""
    if not (FIXTURES / "manifest.json").exists():
        subprocess.run([sys.executable, "-m", "scripts.generate_fixtures", "--out", str(FIXTURES), "--count", "12"],
                       cwd=ROOT, check=True)
    return FIXTURES


@pytest.fixture(scope="session")
def manifest(fixtures_dir) -> dict:
    import json

    return json.loads((fixtures_dir / "manifest.json").read_text())
