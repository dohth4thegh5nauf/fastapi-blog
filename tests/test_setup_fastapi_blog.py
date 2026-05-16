"""Tests for setup_fastapi_blog() unified facade."""

from fastapi import FastAPI

import fastapi_blog


def test_setup_fastapi_blog_basic():
    """Test that setup_fastapi_blog() configures both blog and admin."""
    app = FastAPI()

    # Use unified facade
    admins = fastapi_blog.setup_fastapi_blog(
        app,
        posts_dirname="posts",
        include_api=False,
        locales=["en"],
        default_locale="en",
        admin_username="admin",
        admin_password="test123",
        secret_key="a" * 64,  # Strong secret
        enable_role_management=False,
    )

    # Verify admin is configured
    assert admins is not None
    assert isinstance(admins, dict)
    assert "en" in admins

    # Verify routes are registered
    routes = [route.path for route in app.routes]

    # Blog routes should be present
    assert any("/blog" in path for path in routes), "Blog routes not found"

    # Admin routes should be present (new structure: /en/admin)
    assert any("/en/admin" in path for path in routes), "Admin routes not found"


def test_setup_fastapi_blog_with_api():
    """Test setup_fastapi_blog() with REST API enabled."""
    app = FastAPI()

    admins = fastapi_blog.setup_fastapi_blog(
        app,
        include_api=True,  # Enable REST API
        locales=["en"],
        default_locale="en",
        admin_username="admin",
        admin_password="test123",
        secret_key="a" * 64,
    )

    assert admins is not None

    # Verify API routes are registered
    routes = [route.path for route in app.routes]
    assert any("/api/posts" in path for path in routes), "API routes not found"


def test_setup_fastapi_blog_multiple_locales():
    """Test setup_fastapi_blog() with multiple locales."""
    app = FastAPI()

    admins = fastapi_blog.setup_fastapi_blog(
        app,
        locales=["en", "ru"],
        default_locale="ru",  # Russian by default
        admin_username="admin",
        admin_password="test123",
        secret_key="a" * 64,
    )

    # Both locales should be configured
    assert "en" in admins
    assert "ru" in admins

    # Verify both admin instances are mounted (new structure: /en/admin, /ru/admin)
    routes = [route.path for route in app.routes]
    assert any("/en/admin" in path for path in routes), "English admin not found"
    assert any("/ru/admin" in path for path in routes), "Russian admin not found"


def test_setup_fastapi_blog_with_role_management():
    """Test setup_fastapi_blog() with role management enabled."""
    app = FastAPI()

    admins = fastapi_blog.setup_fastapi_blog(
        app,
        locales=["en"],
        default_locale="en",
        admin_username="admin",
        admin_password="test123",
        secret_key="a" * 64,
        enable_role_management=True,
    )

    assert admins is not None
    admin = admins["en"]
    assert admin is not None


def test_setup_fastapi_blog_is_convenience_wrapper():
    """Verify setup_fastapi_blog() is equivalent to separate calls."""
    app1 = FastAPI()
    app2 = FastAPI()

    # Method 1: Unified facade
    admins1 = fastapi_blog.setup_fastapi_blog(
        app1,
        posts_dirname="posts",
        include_api=False,
        locales=["en"],
        default_locale="en",
        admin_username="admin",
        admin_password="test123",
        secret_key="a" * 64,
        enable_role_management=False,
    )

    # Method 2: Separate calls
    fastapi_blog.add_blog_to_fastapi(
        app2,
        posts_dirname="posts",
        include_api=False,
    )
    admins2 = fastapi_blog.add_admin_to_app(
        app2,
        locales=["en"],
        default_locale="en",
        admin_username="admin",
        admin_password="test123",
        secret_key="a" * 64,
        enable_role_management=False,
    )

    # Both should result in same number of routes
    routes1 = [route.path for route in app1.routes]
    routes2 = [route.path for route in app2.routes]

    # Filter out openapi/redoc routes (may differ in order)
    blog_admin_routes1 = [r for r in routes1 if "/blog" in r or "/admin" in r]
    blog_admin_routes2 = [r for r in routes2 if "/blog" in r or "/admin" in r]

    assert len(blog_admin_routes1) == len(blog_admin_routes2), (
        "Unified facade should create same routes as separate calls"
    )

    # Admin instances should be equivalent
    assert set(admins1.keys()) == set(admins2.keys())
