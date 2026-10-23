import os
import tempfile
from pathlib import Path

TEST_DIR = tempfile.mkdtemp(prefix="emoto-tests-")
os.environ["DATA_DIR"] = TEST_DIR
os.environ["SESSION_SECRET"] = "test-secret-that-is-long-enough-for-tests"
os.environ["APP_ENV"] = "testing"
os.environ["INITIAL_ADMIN_EMAIL"] = "admin@gmail.com"
os.environ["INITIAL_ADMIN_PASSWORD"] = "admin@123"
os.environ["INITIAL_ADMIN_NAME"] = "Test Admin"

import pytest
from fastapi.testclient import TestClient
from app.database import Base, engine
from app.main import app
from app.migrate import ensure_initial_admin


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    ensure_initial_admin()
    yield


@pytest.fixture
def client():
    with TestClient(app) as value:
        yield value


@pytest.fixture
def admin(client):
    response = client.post("/api/v1/auth/login", json={"email": "admin@gmail.com", "password": "admin@123"})
    assert response.status_code == 200, response.text
    return {"client": client, "headers": {"X-CSRF-Token": response.json()["csrf_token"]}, "user": response.json()["user"]}

