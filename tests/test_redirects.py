"""Tests for URL redirects without locale."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

import fastapi_blog


def test_root_redirects_to_blog():
    """Test that GET / redirects to /blog/."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app, follow_redirects=False)

    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["location"] == "/blog/"


def test_root_redirects_to_blog_custom_default():
    """Test that GET / redirects to /blog/ regardless of default locale."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="ru")
    client = TestClient(app, follow_redirects=False)

    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["location"] == "/blog/"


def test_blog_redirects_to_blog_slash():
    """Test that GET /blog redirects to /blog/."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app, follow_redirects=False)

    response = client.get("/blog")
    assert response.status_code == 302
    assert response.headers["location"] == "/blog/"


def test_blog_with_trailing_slash_shows_default_locale():
    """Test that GET /blog/ shows default locale content."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    # /blog/ should show default locale (English)
    response = client.get("/blog/")
    assert response.status_code == 200
    assert "Recent Writings" in response.text


def test_default_locale_blog_redirects_to_clean_url():
    """Test that GET /en/blog/* redirects to /blog/* when en is default."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app, follow_redirects=False)

    response = client.get("/en/blog/posts")
    assert response.status_code == 302
    assert response.headers["location"] == "/blog/posts"


def test_default_locale_admin_redirects_to_clean_url():
    """Test that GET /en/admin redirects to /admin when en is default."""
    app = FastAPI()
    fastapi_blog.setup_fastapi_blog(
        app, locales=["en", "ru"], default_locale="en", admin_password="test123"
    )
    client = TestClient(app, follow_redirects=False)

    response = client.get("/en/admin")
    assert response.status_code == 302
    assert response.headers["location"] == "/admin"


def test_default_locale_admin_with_paths_redirects():
    """Test that GET /en/admin/* redirects to /admin/* when en is default."""
    app = FastAPI()
    fastapi_blog.setup_fastapi_blog(
        app, locales=["en", "ru"], default_locale="en", admin_password="test123"
    )
    client = TestClient(app, follow_redirects=False)

    response = client.get("/en/admin/user/list")
    assert response.status_code == 302
    assert response.headers["location"] == "/admin/user/list"


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


def test_non_default_locale_routes_work():
    """Test that non-default locale routes work correctly."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    # /ru/blog/posts should show Russian
    response = client.get("/ru/blog/posts")
    assert response.status_code == 200
    assert "Статьи" in response.text

    # /blog/posts should show default locale (English)
    response = client.get("/blog/posts")
    assert response.status_code == 200
    assert "Articles" in response.text
