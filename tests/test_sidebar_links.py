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
