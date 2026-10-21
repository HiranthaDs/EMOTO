import os
import tempfile
from pathlib import Path

TEST_DIR = tempfile.mkdtemp(prefix="emoto-tests-")
os.environ["DATA_DIR"] = TEST_DIR
os.environ["BOOTSTRAP_TOKEN"] = "test-bootstrap-token"
os.environ["SESSION_SECRET"] = "test-secret-that-is-long-enough-for-tests"
os.environ["APP_ENV"] = "testing"

import pytest
from fastapi.testclient import TestClient
from app.database import Base, engine
from app.main import app


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as value:
        yield value


@pytest.fixture
def admin(client):
    response = client.post("/api/v1/auth/bootstrap", json={"token": "test-bootstrap-token", "email": "admin@emoto.example.com", "full_name": "Test Admin", "password": "VerySecure123!"})
    assert response.status_code == 201, response.text
    return {"client": client, "headers": {"X-CSRF-Token": response.json()["csrf_token"]}, "user": response.json()["user"]}

