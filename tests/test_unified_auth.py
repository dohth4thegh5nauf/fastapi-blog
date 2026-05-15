"""Tests for unified authentication (session + Basic auth)."""

import base64

from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from fastapi_blog.auth import get_current_user, require_current_user


def test_get_current_user_from_basic_auth():
    """Test authentication via Authorization: Basic header."""
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret-key")

    async def auth_dependency(
        request: Request,
    ):
        return await get_current_user(
            request, admin_username="admin", admin_password="secret"
        )

    @app.get("/test")
    async def test_endpoint(user: str | None = Depends(auth_dependency)):
        return {"user": user}

    client = TestClient(app)

    # No auth
    response = client.get("/test")
    assert response.status_code == 200
    assert response.json() == {"user": None}

    # With Basic auth
    credentials = base64.b64encode(b"admin:secret").decode("utf-8")
    response = client.get("/test", headers={"Authorization": f"Basic {credentials}"})
    assert response.status_code == 200
    assert response.json() == {"user": "admin"}


def test_get_current_user_invalid_basic_auth():
    """Test that invalid Basic auth credentials are rejected."""
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret-key")

    async def auth_dependency(request: Request):
        return await get_current_user(
            request, admin_username="admin", admin_password="secret"
        )

    @app.get("/test")
    async def test_endpoint(user: str | None = Depends(auth_dependency)):
        return {"user": user}

    client = TestClient(app)

    # Wrong password
    credentials = base64.b64encode(b"admin:wrongpassword").decode("utf-8")
    response = client.get("/test", headers={"Authorization": f"Basic {credentials}"})
    assert response.status_code == 200
    assert response.json() == {"user": None}

    # Wrong username
    credentials = base64.b64encode(b"wronguser:secret").decode("utf-8")
    response = client.get("/test", headers={"Authorization": f"Basic {credentials}"})
    assert response.status_code == 200
    assert response.json() == {"user": None}


def test_require_current_user_raises_401():
    """Test that require_current_user raises 401 when not authenticated."""
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret-key")

    async def auth_dependency(request: Request):
        return await require_current_user(
            request, admin_username="admin", admin_password="secret"
        )

    @app.get("/test")
    async def test_endpoint(user: str = Depends(auth_dependency)):
        return {"user": user}

    client = TestClient(app)

    # No auth -> 401
    response = client.get("/test")
    assert response.status_code == 401
    assert "Authentication required" in response.json()["detail"]


def test_require_current_user_allows_authenticated():
    """Test that require_current_user allows authenticated requests."""
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret-key")

    async def auth_dependency(request: Request):
        return await require_current_user(
            request, admin_username="admin", admin_password="secret"
        )

    @app.get("/test")
    async def test_endpoint(user: str = Depends(auth_dependency)):
        return {"user": user}

    client = TestClient(app)

    # With Basic auth -> 200
    credentials = base64.b64encode(b"admin:secret").decode("utf-8")
    response = client.get("/test", headers={"Authorization": f"Basic {credentials}"})
    assert response.status_code == 200
    assert response.json() == {"user": "admin"}


def test_unified_auth_with_basic():
    """Test that credentials work via Basic auth."""
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret-key")

    async def auth_dependency(request: Request):
        return await require_current_user(
            request, admin_username="testuser", admin_password="testpass"
        )

    @app.get("/protected")
    async def protected_endpoint(user: str = Depends(auth_dependency)):
        return {"message": f"Hello, {user}!"}

    client = TestClient(app)

    # Via Basic auth
    credentials = base64.b64encode(b"testuser:testpass").decode("utf-8")
    response = client.get(
        "/protected", headers={"Authorization": f"Basic {credentials}"}
    )
    assert response.status_code == 200
    assert response.json() == {"message": "Hello, testuser!"}


def test_invalid_basic_auth_format():
    """Test that malformed Basic auth is handled gracefully."""
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret-key")

    async def auth_dependency(request: Request):
        return await get_current_user(
            request, admin_username="admin", admin_password="secret"
        )

    @app.get("/test")
    async def test_endpoint(user: str | None = Depends(auth_dependency)):
        return {"user": user}

    client = TestClient(app)

    # Malformed base64
    response = client.get("/test", headers={"Authorization": "Basic not-valid-base64!"})
    assert response.status_code == 200
    assert response.json() == {"user": None}

    # Missing colon in credentials
    credentials = base64.b64encode(b"adminnoseparator").decode("utf-8")
    response = client.get("/test", headers={"Authorization": f"Basic {credentials}"})
    assert response.status_code == 200
    assert response.json() == {"user": None}
