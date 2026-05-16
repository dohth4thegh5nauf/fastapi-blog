"""Tests for URL redirects without locale."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

import fastapi_blog


def test_root_redirects_to_default_locale():
    """Test that GET / redirects to /{default_locale}/blog/."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app, follow_redirects=False)

    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["location"] == "/en/blog/"


def test_root_redirects_to_custom_default_locale():
    """Test that GET / redirects to custom default locale."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="ru")
    client = TestClient(app, follow_redirects=False)

    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["location"] == "/ru/blog/"


def test_blog_redirects_to_default_locale():
    """Test that GET /blog redirects to /{default_locale}/blog/."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app, follow_redirects=False)

    response = client.get("/blog")
    assert response.status_code == 302
    assert response.headers["location"] == "/en/blog/"


def test_blog_with_trailing_slash_uses_accept_language():
    """Test that GET /blog/ uses Accept-Language (legacy router)."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    # Legacy route /blog/ with Accept-Language should work
    response = client.get("/blog/", headers={"Accept-Language": "ru"})
    assert response.status_code == 200
    assert "Последние записи" in response.text


def test_blog_redirect_to_custom_default_locale():
    """Test that GET /blog redirects to custom default locale."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="ru")
    client = TestClient(app, follow_redirects=False)

    response = client.get("/blog")
    assert response.status_code == 302
    assert response.headers["location"] == "/ru/blog/"


def test_admin_redirects_to_default_locale():
    """Test that GET /admin redirects to /{default_locale}/admin."""
    app = FastAPI()
    fastapi_blog.setup_fastapi_blog(
        app, locales=["en", "ru"], default_locale="en", admin_password="test123"
    )
    client = TestClient(app, follow_redirects=False)

    response = client.get("/admin")
    assert response.status_code in (307, 302)  # Allow both temporary redirect codes
    assert response.headers["location"] == "/en/admin"


def test_admin_with_trailing_slash_redirects():
    """Test that GET /admin/ redirects to /{default_locale}/admin."""
    app = FastAPI()
    fastapi_blog.setup_fastapi_blog(
        app, locales=["en", "ru"], default_locale="en", admin_password="test123"
    )
    client = TestClient(app, follow_redirects=False)

    response = client.get("/admin/")
    assert response.status_code in (307, 302)
    assert response.headers["location"] == "/en/admin"


def test_redirects_are_followed_by_default():
    """Test that redirects are followed by default and pages load correctly."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)  # follow_redirects=True by default

    # GET / → /en/ → page loads
    response = client.get("/")
    assert response.status_code == 200

    # GET /blog → /en/blog/ → page loads
    response = client.get("/blog")
    assert response.status_code == 200
    assert "Recent Writings" in response.text


def test_legacy_blog_routes_still_work():
    """Test that legacy /blog/* routes (with Accept-Language) still work."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    # /blog/posts with Accept-Language should still work
    response = client.get("/blog/posts", headers={"Accept-Language": "ru"})
    assert response.status_code == 200
    assert "Статьи" in response.text

    response = client.get("/blog/posts", headers={"Accept-Language": "en"})
    assert response.status_code == 200
    assert "Articles" in response.text
