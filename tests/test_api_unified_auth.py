"""Test REST API with unified authentication."""

import base64

from fastapi import FastAPI
from fastapi.testclient import TestClient

import fastapi_blog


def test_api_with_unified_auth_via_basic():
    """Test that REST API works with Basic auth when credentials provided."""
    app = FastAPI()
    fastapi_blog.setup_fastapi_blog(
        app,
        include_api=True,
        admin_username="testadmin",
        admin_password="testpass",
    )

    client = TestClient(app)

    # Create credentials
    credentials = base64.b64encode(b"testadmin:testpass").decode("utf-8")
    headers = {"Authorization": f"Basic {credentials}"}

    # Test that API endpoints require auth
    response = client.get("/api/posts/test-post/raw")
    assert response.status_code == 401

    # Test that API endpoints work with Basic auth
    response = client.get("/api/posts/test-post/raw", headers=headers)
    assert response.status_code == 404  # Post doesn't exist, but auth worked


def test_api_without_credentials_uses_legacy_auth():
    """Test that API without credentials falls back to session-only auth."""
    app = FastAPI()
    # Don't provide admin_username/admin_password
    fastapi_blog.add_blog_to_fastapi(app, include_api=True)

    client = TestClient(app)

    # Without session or Basic auth -> 401
    response = client.get("/api/posts/test-post/raw")
    assert response.status_code == 401
    # Should mention authentication required
    assert "authentication required" in response.json()["detail"].lower()


def test_api_with_invalid_basic_auth():
    """Test that API rejects invalid Basic auth credentials."""
    app = FastAPI()
    fastapi_blog.setup_fastapi_blog(
        app,
        include_api=True,
        admin_username="testadmin",
        admin_password="testpass",
    )

    client = TestClient(app)

    # Wrong password
    credentials = base64.b64encode(b"testadmin:wrongpass").decode("utf-8")
    headers = {"Authorization": f"Basic {credentials}"}
    response = client.get("/api/posts/test-post/raw", headers=headers)
    assert response.status_code == 401

    # Wrong username
    credentials = base64.b64encode(b"wrongadmin:testpass").decode("utf-8")
    headers = {"Authorization": f"Basic {credentials}"}
    response = client.get("/api/posts/test-post/raw", headers=headers)
    assert response.status_code == 401
