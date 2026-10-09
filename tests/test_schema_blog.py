"""Tests for the blog (helpers and routes) with a custom frontmatter schema."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fastapi_blog
from fastapi_blog import FieldSpec, FrontmatterSchema, helpers


# A schema that renames every built-in field, like an external service would.
EXTERNAL_SCHEMA = FrontmatterSchema(
    fields=(
        FieldSpec("headline", alias="title", required=True, role="title"),
        FieldSpec("pub_date", alias="pubDate", required=True, role="date"),
        FieldSpec("is_public", alias="isPublic", type="bool", role="published"),
        FieldSpec("labels", type="list[str]", role="tags"),
        FieldSpec("summary", role="description"),
        FieldSpec("author"),
    ),
)


def _write(directory, slug, frontmatter):
    text = f"---\n{frontmatter}\n---\n\nBody of {slug}\n"
    (directory / f"{slug}.md").write_text(text)


@pytest.fixture
def posts_dir(tmp_path, monkeypatch):
    posts = tmp_path / "posts"
    posts.mkdir()
    (tmp_path / "pages").mkdir()
    monkeypatch.chdir(tmp_path)
    helpers.list_posts.cache_clear()
    yield posts
    helpers.list_posts.cache_clear()


@pytest.fixture
def external_posts(posts_dir):
    _write(
        posts_dir,
        "first",
        "title: First\npubDate: '2024-01-01'\nisPublic: true\n"
        "labels: [alpha, beta]\nsummary: First summary\nauthor: Ann",
    )
    _write(
        posts_dir,
        "second",
        "title: Second\npubDate: '2024-03-01'\nisPublic: true\nlabels: [alpha]",
    )
    _write(posts_dir, "hidden", "title: Hidden\npubDate: '2024-02-01'\nisPublic: false")
    return posts_dir


# --- helpers.list_posts ------------------------------------------------------


def test_default_behavior_is_unchanged_without_schema():
    helpers.list_posts.cache_clear()
    posts = helpers.list_posts(posts_dirname="tests/examples/posts", strict=False)
    assert len(posts) == 19
    assert posts[0]["title"] == "No Tags"


def test_roles_are_exposed_under_role_names(external_posts):
    posts = helpers.list_posts(posts_dirname="posts", schema=EXTERNAL_SCHEMA)
    assert [p["slug"] for p in posts] == ["second", "first"]  # newest first
    first = posts[1]
    assert first["title"] == "First"
    assert first["date"] == "2024-01-01"
    assert first["tags"] == ["alpha", "beta"]
    assert first["description"] == "First summary"
    # The internal field names are still there
    assert first["headline"] == "First"
    assert first["pub_date"] == "2024-01-01"
    assert first["author"] == "Ann"


def test_published_role_filters_drafts(external_posts):
    drafts = helpers.list_posts(
        published=False, posts_dirname="posts", schema=EXTERNAL_SCHEMA
    )
    assert [p["slug"] for p in drafts] == ["hidden"]


def test_posts_not_matching_the_schema_are_skipped(external_posts, caplog):
    _write(external_posts, "old-format", "title: Old\ndate: '2024-05-01'")
    posts = helpers.list_posts(posts_dirname="posts", schema=EXTERNAL_SCHEMA)
    assert "old-format" not in [p["slug"] for p in posts]
    assert any("Skipping" in rec.message for rec in caplog.records)


def test_schema_extra_overrides_strict_flag(posts_dir):
    _write(posts_dir, "extra", "title: T\ndate: '2024-01-01'\ncover: pic.png")
    loose = fastapi_blog.FrontmatterSchema(
        fields=(
            FieldSpec("title", required=True, role="title"),
            FieldSpec("date", required=True, role="date"),
        ),
        extra="allow",
    )
    # `strict=True` would reject the extra key, but the schema says `allow`
    posts = helpers.list_posts(posts_dirname="posts", strict=True, schema=loose)
    assert [p["slug"] for p in posts] == ["extra"]
    assert posts[0]["cover"] == "pic.png"


def test_no_roles_means_slug_title_and_all_published(posts_dir):
    schema = FrontmatterSchema(fields=(FieldSpec("author"),))
    _write(posts_dir, "b-post", "author: Bob")
    _write(posts_dir, "a-post", "author: Ann")
    posts = helpers.list_posts(posts_dirname="posts", schema=schema)
    assert [p["slug"] for p in posts] == ["a-post", "b-post"]  # by slug
    assert [p["title"] for p in posts] == ["a-post", "b-post"]  # slug fallback
    drafts = helpers.list_posts(published=False, posts_dirname="posts", schema=schema)
    assert drafts == ()


def test_undated_posts_come_after_dated_ones(posts_dir):
    schema = FrontmatterSchema(
        fields=(
            FieldSpec("title", required=True, role="title"),
            FieldSpec("when", type="date", role="date"),
        )
    )
    _write(posts_dir, "undated", "title: U")
    _write(posts_dir, "old", "title: O\nwhen: 2020-01-01")  # YAML date, unquoted
    _write(posts_dir, "new", "title: N\nwhen: 2024-01-01")
    posts = helpers.list_posts(posts_dirname="posts", schema=schema)
    assert [p["slug"] for p in posts] == ["new", "old", "undated"]


def test_build_post_title_falls_back_to_slug():
    post = helpers.build_post({"headline": ""}, "my-slug", EXTERNAL_SCHEMA)
    assert post["title"] == "my-slug"
    assert post["slug"] == "my-slug"


def test_resolve_schema():
    assert helpers.resolve_schema(True) is fastapi_blog.DEFAULT_SCHEMA
    assert helpers.resolve_schema(False).extra == "allow"
    assert helpers.resolve_schema(False, EXTERNAL_SCHEMA) is EXTERNAL_SCHEMA


# --- Blog routes -------------------------------------------------------------


@pytest.fixture
def client(external_posts):
    app = FastAPI()
    fastapi_blog.add_blog_to_fastapi(app, frontmatter_schema=EXTERNAL_SCHEMA)
    return TestClient(app)


def test_posts_page_lists_posts_with_role_values(client):
    response = client.get("/blog/posts")
    assert response.status_code == 200
    assert "First" in response.text
    assert "Second" in response.text
    assert "Hidden" not in response.text
    assert "2024-03-01" in response.text
    assert "First summary" in response.text


def test_single_post_page(client):
    response = client.get("/blog/posts/first")
    assert response.status_code == 200
    assert "<h1>First</h1>" in response.text
    assert "Body of first" in response.text
    assert "alpha" in response.text


def test_draft_post_page_is_not_found(client):
    assert client.get("/blog/posts/hidden").status_code == 404


def test_tag_pages_use_the_tags_role(client):
    tags = client.get("/blog/tags")
    assert tags.status_code == 200
    assert "alpha" in tags.text and "beta" in tags.text

    tag = client.get("/blog/tags/beta")
    assert tag.status_code == 200
    assert "First" in tag.text
    assert "Second" not in tag.text


def test_index_shows_recent_posts(client):
    response = client.get("/blog/")
    assert response.status_code == 200
    assert "Second" in response.text
