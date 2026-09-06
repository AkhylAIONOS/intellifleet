"""Exercise the application's actual CORS middleware without external services."""
from pathlib import Path
import runpy

from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
import pytest

from backend.config.config import settings


def application(monkeypatch, frontend_url=None):
    monkeypatch.setattr(settings, "FRONTEND_URL", frontend_url)
    # Build a fresh app without reloading shared modules or starting external services.
    app = runpy.run_path(str(Path(__file__).resolve().parents[1] / "main.py"))["app"]
    assert sum(m.cls is CORSMiddleware for m in app.user_middleware) == 1
    return app


def preflight(client, origin):
    return client.options("/auth/signin", headers={
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,authorization",
    })


@pytest.mark.parametrize("origin", [
    "https://intellifleet-web.onrender.com",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
])
def test_signin_preflight_allows_required_origins(monkeypatch, origin):
    # A configured production origin must not remove either local origin.
    client = TestClient(application(monkeypatch, "https://intellifleet-web.onrender.com"))
    response = preflight(client, origin)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "POST" in response.headers["access-control-allow-methods"]
    assert "authorization" in response.headers["access-control-allow-headers"]
    assert "content-type" in response.headers["access-control-allow-headers"]
    # Invalid signin input still needs readable CORS headers in the browser.
    invalid = client.post("/auth/signin", headers={"Origin": origin}, json={})
    assert invalid.status_code == 422
    assert invalid.headers["access-control-allow-origin"] == origin
    assert invalid.headers["access-control-allow-credentials"] == "true"


def test_custom_frontend_url_is_additive_and_normalized(monkeypatch):
    client = TestClient(application(monkeypatch, " https://custom.example/ "))
    for origin in ("https://custom.example", "https://intellifleet-web.onrender.com"):
        response = preflight(client, origin)
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin


def test_unconfigured_frontend_keeps_render_and_rejects_unknown_origin(monkeypatch):
    client = TestClient(application(monkeypatch))
    assert preflight(client, "https://intellifleet-web.onrender.com").status_code == 200
    response = preflight(client, "https://untrusted.example")
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
