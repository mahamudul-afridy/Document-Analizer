"""Integration tests run the real API + pipeline against PostgreSQL (pgvector).

Run inside Docker:  docker compose run --rm -e TEST_DATABASE_URL=postgresql+psycopg://documind:<pw>@db:5432/documind_test api pytest
The test database is created/dropped automatically. Tests are skipped when TEST_DATABASE_URL is not set.
"""
import os

import pytest

TEST_DB = os.environ.get("TEST_DATABASE_URL")  # DATABASE_URL/CELERY_EAGER are set in tests/conftest.py


def pytest_collection_modifyitems(config, items):
    if not TEST_DB:
        skip = pytest.mark.skip(reason="TEST_DATABASE_URL not set (needs PostgreSQL with pgvector)")
        for item in items:
            if "integration" in str(item.fspath):
                item.add_marker(skip)


@pytest.fixture(scope="session")
def client(tmp_path_factory):
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    url = make_url(TEST_DB)
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()

    os.environ["STORAGE_DIR"] = str(tmp_path_factory.mktemp("storage"))
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config("alembic.ini"), "head")

    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def admin_headers(client):
    r = client.post("/api/v1/auth/setup", json={"email": "admin@example.com", "password": "Admin#12345",
                                                "full_name": "Test Admin"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
