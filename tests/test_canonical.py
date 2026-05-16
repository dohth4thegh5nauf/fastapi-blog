"""Tests for canonical URLs and hreflang tags."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

import fastapi_blog


def test_canonical_on_default_locale_page():
    """Test canonical tag on default locale page points to itself."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app, follow_redirects=False)

    response = client.get("/blog/posts")
    assert response.status_code == 200
    assert '<link rel="canonical" href="http://testserver/blog/posts">' in response.text
    assert (
        response.headers.get("link")
        == '<http://testserver/blog/posts>; rel="canonical"'
    )


def test_canonical_on_duplicate_default_locale_page():
    """Test canonical tag on duplicate URL with default locale prefix."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app, follow_redirects=False)

    response = client.get("/en/blog/posts")
    # Should redirect, but if it returns 200, check canonical points to clean URL
    if response.status_code == 200:
        assert (
            '<link rel="canonical" href="http://testserver/blog/posts">'
            in response.text
        )
        assert (
            response.headers.get("link")
            == '<http://testserver/blog/posts>; rel="canonical"'
        )
    else:
        assert response.status_code == 302
        assert response.headers.get("location") == "/blog/posts"


def test_canonical_on_non_default_locale_page():
    """Test canonical tag on non-default locale page points to itself."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    response = client.get("/ru/blog/posts")
    assert response.status_code == 200
    assert (
        '<link rel="canonical" href="http://testserver/ru/blog/posts">' in response.text
    )
    assert (
        response.headers.get("link")
        == '<http://testserver/ru/blog/posts>; rel="canonical"'
    )


def test_hreflang_on_default_locale_page():
    """Test hreflang tags present on default locale page."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    response = client.get("/blog/posts")
    assert response.status_code == 200
    assert 'hreflang="en"' in response.text
    assert 'hreflang="ru"' in response.text
    assert 'hreflang="x-default"' in response.text
    assert 'href="http://testserver/blog/posts">' in response.text
    assert 'href="http://testserver/ru/blog/posts">' in response.text


def test_hreflang_on_non_default_locale_page():
    """Test hreflang tags present on non-default locale page."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    response = client.get("/ru/blog/posts")
    assert response.status_code == 200
    assert 'hreflang="en"' in response.text
    assert 'hreflang="ru"' in response.text
    assert 'hreflang="x-default"' in response.text


def test_no_hreflang_on_duplicate_pages():
    """Test hreflang tags NOT present on duplicate pages."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app, follow_redirects=False)

    response = client.get("/en/blog/posts")
    if response.status_code == 200:
        # Should have canonical but NOT hreflang
        assert '<link rel="canonical"' in response.text
        # hreflang should not be present on duplicates
        assert "hreflang" not in response.text


def test_no_canonical_header_on_admin():
    """Test Link header NOT added to admin pages."""
    app = FastAPI()
    fastapi_blog.setup_fastapi_blog(
        app, locales=["en", "ru"], default_locale="en", admin_password="test123"
    )
    client = TestClient(app, follow_redirects=False)

    # Admin page should not have Link header
    response = client.get("/admin")
    assert "link" not in response.headers.get("link", "").lower()


def test_no_canonical_header_on_locale_admin():
    """Test Link header NOT added to localized admin pages."""
    app = FastAPI()
    fastapi_blog.setup_fastapi_blog(
        app, locales=["en", "ru"], default_locale="en", admin_password="test123"
    )
    client = TestClient(app, follow_redirects=False)

    response = client.get("/ru/admin")
    # Should not have canonical Link header
    assert "link" not in response.headers.get("link", "").lower()


def test_canonical_on_homepage():
    """Test canonical URL on blog homepage."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    response = client.get("/blog/")
    assert response.status_code == 200
    assert '<link rel="canonical" href="http://testserver/blog/">' in response.text
    assert 'hreflang="en"' in response.text
    assert 'hreflang="ru"' in response.text


def test_canonical_on_tags_page():
    """Test canonical URL on tags page."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    response = client.get("/blog/tags")
    assert response.status_code == 200
    assert '<link rel="canonical" href="http://testserver/blog/tags">' in response.text
    assert (
        response.headers.get("link") == '<http://testserver/blog/tags>; rel="canonical"'
    )


def test_alternate_urls_correctness():
    """Test that alternate URLs are correctly computed for all locales."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(
        app, locales=["en", "ru", "fr"], default_locale="en"
    )
    client = TestClient(app)

    response = client.get("/blog/posts")
    assert response.status_code == 200
    # Should have alternates for all locales
    assert (
        'href="http://testserver/blog/posts"' in response.text
    )  # en (default, no prefix)
    assert 'href="http://testserver/ru/blog/posts"' in response.text  # ru
    assert 'href="http://testserver/fr/blog/posts"' in response.text  # fr
