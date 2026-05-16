"""Tests for sidebar links locale awareness."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

import fastapi_blog


def test_sidebar_links_use_ru_locale():
    """On Russian page, sidebar links point to /ru/blog/..."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    response = client.get("/ru/blog/posts")
    assert response.status_code == 200

    # Links to tags in navigation should use /ru/ prefix
    assert 'href="/ru/blog/tags"' in response.text
    # Link to blog homepage
    assert 'href="/ru/blog/"' in response.text
    # Link to about page
    assert 'href="/ru/blog/about"' in response.text


def test_sidebar_links_use_default_locale():
    """On default locale page, sidebar links point to /blog/... (no prefix)."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    response = client.get("/blog/posts")
    assert response.status_code == 200

    # Links should not have /en/ prefix
    assert 'href="/blog/tags"' in response.text
    assert 'href="/blog/"' in response.text
    assert 'href="/blog/about"' in response.text

    # Should not have /ru/ links in navigation (except in hreflang)
    # Extract navigation section (before canonical tags)
    nav_section = response.text.split('<link rel="canonical"')[0]
    assert '/ru/blog/tags"' not in nav_section or "hreflang" in nav_section


def test_tag_links_in_tags_page_respect_locale():
    """Links to specific tags on tags page are localized."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    response = client.get("/ru/blog/tags")
    assert response.status_code == 200

    # Find all tag links
    import re

    tag_links = re.findall(r'href="(/[^"]*?/blog/tags/[^"]*?)"', response.text)

    # Filter out canonical/hreflang links
    nav_tag_links = [
        link
        for link in tag_links
        if "hreflang" not in response.text[: response.text.find(link)]
    ]

    # All navigation tag links should start with /ru/
    for link in nav_tag_links:
        if not link.startswith("/ru/"):
            # Allow if it's in hreflang section
            context = response.text[
                max(0, response.text.find(link) - 100) : response.text.find(link)
            ]
            assert "hreflang" in context, f"Tag link not localized: {link}"


def test_post_links_in_listing_respect_locale():
    """Links to posts in listing are localized."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    response = client.get("/ru/blog/posts")
    assert response.status_code == 200

    # Find all post links in the content
    import re

    # Match post links (not canonical or hreflang)
    post_links = re.findall(r'<h2><a href="(/[^"]*?/blog/posts/[^"]*?)"', response.text)

    # All post links in content should start with /ru/
    for link in post_links:
        assert link.startswith("/ru/"), f"Post link not localized: {link}"


def test_tag_links_on_post_page_respect_locale():
    """Tag links on individual post page are localized."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    response = client.get("/ru/blog/")
    assert response.status_code == 200

    # Get first post link
    import re

    post_links = re.findall(r'<h2><a href="(/ru/blog/posts/[^"]*)"', response.text)

    if post_links:
        # Visit the post
        post_response = client.get(post_links[0])
        assert post_response.status_code == 200

        # Tag links on post page should use /ru/ prefix
        tag_links = re.findall(
            r'Tags:.*?href="(/[^"]*?/blog/tags/[^"]*?)"', post_response.text, re.DOTALL
        )
        for link in tag_links:
            if not link.startswith("/ru/"):
                # Check if it's in hreflang context
                context = post_response.text[
                    max(
                        0, post_response.text.find(link) - 100
                    ) : post_response.text.find(link)
                ]
                assert "hreflang" in context, (
                    f"Tag link on post page not localized: {link}"
                )


def test_sidebar_links_on_default_locale_homepage():
    """Homepage sidebar links use default locale (no prefix)."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    response = client.get("/blog/")
    assert response.status_code == 200

    # Navigation links should be clean URLs
    assert 'href="/blog/posts"' in response.text
    assert 'href="/blog/tags"' in response.text


def test_sidebar_links_on_non_default_locale_homepage():
    """Homepage sidebar links use locale prefix for non-default locale."""
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    response = client.get("/ru/blog/")
    assert response.status_code == 200

    # Navigation links should have /ru/ prefix
    assert 'href="/ru/blog/posts"' in response.text
    assert 'href="/ru/blog/tags"' in response.text


def test_no_unprefixed_blog_links_on_ru_pages():
    """Regression test: На русских страницах НЕ должно быть ссылок /blog/ без /ru/ префикса.

    Это защита от регрессии - если где-то в шаблонах останется url_for вместо locale_url_for,
    или если middleware начнёт редиректить /ru/blog/... на /blog/..., этот тест поймает проблему.
    """
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    # Проверяем несколько страниц
    test_pages = [
        "/ru/blog/",
        "/ru/blog/posts",
        "/ru/blog/tags",
    ]

    for page_url in test_pages:
        response = client.get(page_url)
        assert response.status_code == 200, f"Page {page_url} failed to load"

        # Извлекаем все href из body (не из head, т.к. там canonical и hreflang)
        html = response.text
        body_start = html.find("<body")
        assert body_start > 0, f"No <body> tag found in {page_url}"
        body_html = html[body_start:]

        # Находим все href
        import re

        hrefs_in_body = re.findall(r'href="([^"]+)"', body_html)

        # Фильтруем только внутренние ссылки на /blog
        blog_links = [
            h for h in hrefs_in_body if h.startswith("/blog") or "/blog/" in h
        ]

        # Проверяем что НИ ОДНА ссылка на blog не идёт без /ru/ префикса
        # (кроме абсолютных URL типа http://testserver/blog/ которые могут быть в тестах)
        for href in blog_links:
            # Пропускаем абсолютные URLs
            if href.startswith("http://") or href.startswith("https://"):
                continue

            assert href.startswith("/ru/blog"), (
                f"На странице {page_url} найдена ссылка без /ru/ префикса: {href}"
            )


def test_no_redirect_from_ru_blog_to_default():
    """Regression test: Переходы на /ru/blog/... НЕ должны редиректить на /blog/..."""  # noqa: E501
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, locales=["en", "ru"], default_locale="en")
    client = TestClient(app)

    # Проверяем что эти URL возвращают 200, а не редирект
    test_urls = [
        "/ru/blog/",
        "/ru/blog/posts",
        "/ru/blog/tags",
    ]

    for url in test_urls:
        response = client.get(url, follow_redirects=False)
        assert response.status_code == 200, (
            f"URL {url} редиректит (status {response.status_code}) вместо отображения страницы"
        )


def test_admin_sidebar_links_respect_locale():
    """Admin sidebar links должны учитывать текущую локаль.

    На /admin/ru/ все ссылки sidebar должны вести на /ru/admin/...
    """
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(
        app, locales=["en", "ru"], default_locale="en", prefix="blog"
    )

    import secrets

    fastapi_blog.add_admin_to_app(
        app,
        admin_username="admin",
        admin_password="testpass",
        secret_key=secrets.token_hex(32),
        locales=["en", "ru"],
        default_locale="en",
    )

    client = TestClient(app)

    # Login to default admin (English)
    # Note: default locale uses /admin/login, not /admin/en/login
    response = client.post(
        "/admin/login",
        data={"username": "admin", "password": "testpass"},
        follow_redirects=False,
    )
    assert response.status_code in [302, 303]
    cookies = response.cookies

    # Access Russian admin
    # Note: Russian admin is at /ru/admin/, not /admin/ru/
    response = client.get("/ru/admin/user/list", cookies=cookies)
    assert response.status_code == 200

    # Find all admin navigation links in sidebar
    import re

    # Look for navbar-nav section
    html = response.text

    # Find all hrefs that point to /admin
    all_hrefs = re.findall(r'href="([^"]*)"', html)
    admin_links = [
        link
        for link in all_hrefs
        if "/admin" in link
        and "/statics/" not in link
    ]
    
    # Strip http://testserver prefix if present
    admin_links = [
        link.replace("http://testserver", "") if link.startswith("http://testserver") else link
        for link in admin_links
    ]

    # Filter to likely navigation links (short paths, not detail pages)
    nav_links = [
        link
        for link in admin_links
        if link.count("/") <= 4  # /ru/admin/user/list has 4 slashes
    ]

    print(f"\nНайдено {len(nav_links)} навигационных ссылок в admin:")
    for link in nav_links:
        print(f"  {link}")

    # At least some navigation links should exist
    assert len(nav_links) > 0, "No admin navigation links found"

    # All navigation links должны начинаться с /ru/admin
    bad_links = [link for link in nav_links if not link.startswith("/ru/admin")]

    if bad_links:
        print("\n⚠️  Найдены ссылки БЕЗ /ru/ префикса:")
        for link in bad_links:
            print(f"  {link}")

    assert len(bad_links) == 0, (
        f"Found {len(bad_links)} admin links without /ru/ prefix on /admin/ru/ page"
    )
