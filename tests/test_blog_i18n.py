"""Tests for blog i18n functionality."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

import fastapi_blog


def test_blog_responds_to_accept_language_en():
    """Test blog uses English when Accept-Language is 'en'."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    response = client.get("/blog/posts", headers={"Accept-Language": "en"})
    assert response.status_code == 200
    assert "Articles" in response.text
    assert "Статьи" not in response.text


def test_blog_responds_to_accept_language_ru():
    """Test blog uses Russian when Accept-Language is 'ru'."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    response = client.get("/blog/posts", headers={"Accept-Language": "ru"})
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

    # English
    response_en = client.get("/blog/", headers={"Accept-Language": "en"})
    assert "Recent Writings" in response_en.text

    # Russian
    response_ru = client.get("/blog/", headers={"Accept-Language": "ru"})
    assert "Последние записи" in response_ru.text


def test_blog_tags_page_translations():
    """Test tags page uses translations."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    # English
    response_en = client.get("/blog/tags", headers={"Accept-Language": "en"})
    assert ">Tags<" in response_en.text

    # Russian
    response_ru = client.get("/blog/tags", headers={"Accept-Language": "ru"})
    assert ">Теги<" in response_ru.text


def test_blog_navigation_translations():
    """Test navigation links use translations."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    # English
    response_en = client.get("/blog/", headers={"Accept-Language": "en"})
    # Check navigation contains English words (with possible whitespace)
    nav_text = response_en.text
    assert "About" in nav_text
    assert "Articles" in nav_text
    assert "Tags" in nav_text

    # Russian
    response_ru = client.get("/blog/", headers={"Accept-Language": "ru"})
    # Check navigation contains Russian words
    nav_text = response_ru.text
    assert "О блоге" in nav_text
    assert "Статьи" in nav_text
    assert "Теги" in nav_text


def test_blog_footer_translations():
    """Test footer uses translations."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    # English
    response_en = client.get("/blog/", headers={"Accept-Language": "en"})
    assert "All rights reserved" in response_en.text

    # Russian
    response_ru = client.get("/blog/", headers={"Accept-Language": "ru"})
    assert "Все права защищены" in response_ru.text


def test_blog_accept_language_quality_parsing():
    """Test Accept-Language header with quality values."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    # Russian has higher priority
    response = client.get(
        "/blog/posts", headers={"Accept-Language": "ru;q=0.9,en;q=0.8"}
    )
    assert "Статьи" in response.text

    # English has higher priority
    response = client.get(
        "/blog/posts", headers={"Accept-Language": "en;q=0.9,ru;q=0.8"}
    )
    assert "Articles" in response.text


def test_blog_accept_language_with_region():
    """Test Accept-Language header with region codes (e.g., en-US)."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    # en-US should match 'en'
    response = client.get("/blog/posts", headers={"Accept-Language": "en-US"})
    assert "Articles" in response.text

    # ru-RU should match 'ru'
    response = client.get("/blog/posts", headers={"Accept-Language": "ru-RU"})
    assert "Статьи" in response.text


def test_blog_url_with_locale_en():
    """Test blog works with /blog/en/ URL prefix."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    response = client.get("/blog/en/posts")
    assert response.status_code == 200
    assert "Articles" in response.text
    assert "Статьи" not in response.text


def test_blog_url_with_locale_ru():
    """Test blog works with /blog/ru/ URL prefix."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    response = client.get("/blog/ru/posts")
    assert response.status_code == 200
    assert "Статьи" in response.text
    assert "Articles" not in response.text


def test_blog_url_locale_overrides_accept_language():
    """Test that URL locale parameter takes priority over Accept-Language."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    # URL says 'en', header says 'ru' - URL should win
    response = client.get("/blog/en/posts", headers={"Accept-Language": "ru"})
    assert response.status_code == 200
    assert "Articles" in response.text
    assert "Статьи" not in response.text


def test_language_switcher_present_in_header():
    """Test that language switcher is present in page header."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    response = client.get("/blog/en/")
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
    response = client.get("/blog/ru/")
    assert response.status_code == 200
    assert "Последние записи" in response.text

    # Test posts page
    response = client.get("/blog/ru/posts")
    assert response.status_code == 200
    assert "Статьи" in response.text

    # Test tags page
    response = client.get("/blog/ru/tags")
    assert response.status_code == 200
    assert "Теги" in response.text


def test_language_switcher_javascript_logic():
    """Test that language switcher JavaScript correctly handles URL transformations."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    # Test that switcher script is present with correct logic
    response = client.get("/blog/en/")
    assert response.status_code == 200
    assert "function switchLanguage" in response.text
    assert "parts.findIndex" in response.text
    assert "parts.splice(1, 0, targetLocale)" in response.text


def test_legacy_routes_show_language_switcher():
    """Test that language switcher appears on legacy routes without locale."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    # Legacy route should still show switcher
    response = client.get("/blog/")
    assert response.status_code == 200
    assert '<select id="language-select"' in response.text
    assert "English" in response.text
    assert "Русский" in response.text


def test_all_legacy_routes_have_language_switcher():
    """Test that all legacy routes (without locale) show language switcher."""
    import pytest
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)
    
    paths = ["/blog/", "/blog/posts", "/blog/tags"]
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200, f"Failed to load {path}"
        assert '<select id="language-select"' in response.text, \
            f"Language switcher missing on {path}"
        assert "English" in response.text, f"English option missing on {path}"
        assert "Русский" in response.text, f"Русский option missing on {path}"
