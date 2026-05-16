"""Tests for blog i18n functionality."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

import fastapi_blog


def test_blog_shows_default_locale_content():
    """Test blog shows default locale content on clean URLs."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    # /blog/posts shows default locale (English) regardless of Accept-Language
    response = client.get("/blog/posts")
    assert response.status_code == 200
    assert "Articles" in response.text
    assert "Статьи" not in response.text


def test_blog_shows_non_default_locale_with_prefix():
    """Test blog shows Russian content on /ru/blog/* URLs."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    # /ru/blog/posts shows Russian regardless of Accept-Language
    response = client.get("/ru/blog/posts")
    assert response.status_code == 200
    assert "Статьи" in response.text
    assert "Articles" not in response.text


def test_blog_uses_default_locale_when_no_accept_language():
    """Test blog uses default locale when Accept-Language header is missing."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    response = client.get("/blog/posts")
    assert response.status_code == 200
    assert "Articles" in response.text


def test_blog_uses_default_locale_when_accept_language_not_supported():
    """Test blog uses default locale when Accept-Language is not in supported locales."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    response = client.get("/blog/posts", headers={"Accept-Language": "fr"})
    assert response.status_code == 200
    assert "Articles" in response.text


def test_blog_index_translations():
    """Test index page uses translations."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    # English (default locale, clean URL)
    response_en = client.get("/blog/")
    assert "Recent Writings" in response_en.text

    # Russian (non-default locale, prefixed URL)
    response_ru = client.get("/ru/blog/")
    assert "Последние записи" in response_ru.text


def test_blog_tags_page_translations():
    """Test tags page uses translations."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    # English (default, clean URL)
    response_en = client.get("/blog/tags")
    assert ">Tags<" in response_en.text

    # Russian (prefixed URL)
    response_ru = client.get("/ru/blog/tags")
    assert ">Теги<" in response_ru.text


def test_blog_navigation_translations():
    """Test navigation links use translations."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    # English (default, clean URL)
    response_en = client.get("/blog/")
    nav_text = response_en.text
    assert "About" in nav_text
    assert "Articles" in nav_text
    assert "Tags" in nav_text

    # Russian (prefixed URL)
    response_ru = client.get("/ru/blog/")
    nav_text = response_ru.text
    assert "О блоге" in nav_text
    assert "Статьи" in nav_text
    assert "Теги" in nav_text


def test_blog_footer_translations():
    """Test footer uses translations."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    # English (default, clean URL)
    response_en = client.get("/blog/")
    assert "All rights reserved" in response_en.text

    # Russian (prefixed URL)
    response_ru = client.get("/ru/blog/")
    assert "Все права защищены" in response_ru.text


def test_blog_locale_prefix_overrides_all():
    """Test that locale prefix in URL determines language, not Accept-Language."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    # /ru/blog/posts shows Russian even with Accept-Language: en
    response = client.get("/ru/blog/posts", headers={"Accept-Language": "en"})
    assert "Статьи" in response.text

    # /blog/posts shows default (English) even with Accept-Language: ru
    response = client.get("/blog/posts", headers={"Accept-Language": "ru"})
    assert "Articles" in response.text


def test_blog_different_default_locale():
    """Test blog with different default locale."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="ru")
    client = TestClient(app)

    # Clean URL shows default (Russian)
    response = client.get("/blog/posts")
    assert "Статьи" in response.text

    # /en/blog/posts shows English
    response = client.get("/en/blog/posts")
    assert "Articles" in response.text


def test_blog_default_locale_redirects():
    """Test that /en/blog/* redirects to /blog/* when en is default."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app, follow_redirects=False)

    response = client.get("/en/blog/posts")
    assert response.status_code == 302
    assert response.headers["location"] == "/blog/posts"


def test_blog_url_with_locale_ru():
    """Test blog works with /ru/blog/ URL prefix."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    response = client.get("/ru/blog/posts")
    assert response.status_code == 200
    assert "Статьи" in response.text
    assert "Articles" not in response.text


def test_blog_follows_redirects_automatically():
    """Test that redirects are followed automatically by default."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)  # follow_redirects=True by default

    # /en/blog/posts redirects to /blog/posts and shows English
    response = client.get("/en/blog/posts")
    assert response.status_code == 200
    assert "Articles" in response.text


def test_language_switcher_present_in_header():
    """Test that language switcher is present in page header."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    response = client.get("/en/blog/")
    assert response.status_code == 200
    assert "language-switcher" in response.text
    assert "switchLanguage" in response.text
    assert "English" in response.text
    assert "Русский" in response.text


def test_language_switcher_not_shown_for_single_locale():
    """Test that language switcher is hidden when only one locale available."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en"], default_locale="en")
    client = TestClient(app)

    response = client.get("/blog/")
    assert response.status_code == 200
    # Check that the select element is not present
    assert '<select id="language-select"' not in response.text


def test_blog_locale_routes_for_all_pages():
    """Test that locale routes work for all blog pages."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    # Test main page
    response = client.get("/ru/blog/")
    assert response.status_code == 200
    assert "Последние записи" in response.text

    # Test posts page
    response = client.get("/ru/blog/posts")
    assert response.status_code == 200
    assert "Статьи" in response.text

    # Test tags page
    response = client.get("/ru/blog/tags")
    assert response.status_code == 200
    assert "Теги" in response.text


def test_language_switcher_javascript_logic():
    """Test that language switcher JavaScript correctly handles URL transformations."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    # Test that switcher script is present with correct logic
    response = client.get("/en/blog/")
    assert response.status_code == 200
    assert "function switchLanguage" in response.text
    # New logic: locale is first segment
    assert "parts.unshift(targetLocale)" in response.text


def test_clean_urls_show_language_switcher():
    """Test that language switcher appears on clean URLs."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    # Clean URL (default locale) should show switcher
    response = client.get("/blog/")
    assert response.status_code == 200
    assert '<select id="language-select"' in response.text
    assert "English" in response.text
    assert "Русский" in response.text


def test_all_blog_routes_have_language_switcher():
    """Test that all blog routes show language switcher."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    paths = ["/blog/", "/blog/posts", "/blog/tags", "/ru/blog/", "/ru/blog/posts"]
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, f"Failed to load {path}"
        assert '<select id="language-select"' in response.text, (
            f"Language switcher missing on {path}"
        )
        assert "English" in response.text, f"English option missing on {path}"
        assert "Русский" in response.text, f"Русский option missing on {path}"
