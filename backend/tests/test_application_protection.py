import pytest
from pydantic import ValidationError

from app.config import Settings


def test_crawlers_are_denied(client):
    response = client.get("/robots.txt")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "User-agent: *\nDisallow: /" in response.text
    for crawler in ("GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-SearchBot", "Claude-User", "Google-Extended"):
        assert f"User-agent: {crawler}\nDisallow: /" in response.text


def test_private_responses_are_not_indexed_or_cached(client):
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.headers["x-robots-tag"] == "noindex, nofollow, noarchive, nosnippet, noimageindex"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-security-policy"].startswith("default-src 'self'")
    assert response.headers["x-frame-options"] == "DENY"


def test_default_openapi_location_is_not_exposed(client):
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/api/openapi.json").status_code == 200


def test_production_rejects_an_unsafe_session_secret():
    with pytest.raises(ValidationError, match="SESSION_SECRET"):
        Settings(app_env="production", session_secret="too-short", _env_file=None)
