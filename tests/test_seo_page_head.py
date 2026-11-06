"""Page-level SEO head output through the blog routes."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fastapi_blog import add_blog_to_fastapi, helpers
from fastapi_blog.models import FieldSpec, FrontmatterSchema, SeoConfig
from fastapi_blog.seo import seo_fields


def _schema() -> FrontmatterSchema:
  return FrontmatterSchema(
    fields=(
      FieldSpec('title', required=True, role='title'),
      FieldSpec('date', type='date', role='date'),
      FieldSpec('published', type='bool', default=True, role='published'),
      FieldSpec('tags', type='list[str]', role='tags'),
      *seo_fields(),
    ),
  )


@pytest.fixture
def site(tmp_path, monkeypatch):
  posts = tmp_path / 'posts'
  posts.mkdir()
  (tmp_path / 'pages').mkdir()
  (posts / 'plain.md').write_text(
    '---\ntitle: Plain\ndate: 2026-01-01\ntags: [t]\n---\nHello\n',
    encoding='utf-8',
  )
  (posts / 'moved.md').write_text(
    '---\ntitle: Moved\ndate: 2026-01-02\n'
    'canonical: https://other.example/moved\n---\nHello\n',
    encoding='utf-8',
  )
  (tmp_path / 'pages' / 'about.md').write_text(
    '---\ntitle: About\n---\nAbout us\n', encoding='utf-8'
  )
  monkeypatch.chdir(tmp_path)
  helpers.clear_posts_cache()
  yield tmp_path
  helpers.clear_posts_cache()


def _client(**seo) -> TestClient:
  app = FastAPI()
  add_blog_to_fastapi(
    app,
    frontmatter_schema=_schema(),
    seo=SeoConfig(**seo),
    locales=['en', 'ru'],
  )
  return TestClient(app, follow_redirects=False)


def test_ordinary_post_keeps_hreflang_alternates(site):
  html = _client().get('/blog/posts/plain').text
  assert 'hreflang="ru"' in html
  assert 'hreflang="x-default"' in html


def test_post_with_foreign_canonical_has_no_hreflang(site):
  html = _client().get('/blog/posts/moved').text
  assert '<link rel="canonical" href="https://other.example/moved">' in html
  assert 'hreflang' not in html


def test_tag_pages_are_noindex_when_configured(site):
  html = _client(noindex_tags=True).get('/blog/tags/t').text
  assert '<meta name="robots" content="noindex">' in html
  other = _client(noindex_tags=True).get('/blog/posts/plain').text
  assert 'name="robots"' not in other


def test_static_pages_do_not_inherit_the_index_description(site):
  client = _client(index_description='Site blurb')
  assert 'Site blurb' in client.get('/blog/posts').text
  assert 'Site blurb' not in client.get('/blog/about').text


def test_page_excerpt_comes_from_the_markdown_body(site):
  html = _client(description_fallback='excerpt').get('/blog/about').text
  assert '<meta name="description" content="About us">' in html


def test_site_url_wins_over_the_host_header(site):
  client = _client(site_url='https://example.test')
  html = client.get('/blog/posts/plain', headers={'host': 'evil.test'}).text
  canonical = (
    '<link rel="canonical" href="https://example.test/blog/posts/plain">'
  )
  assert canonical in html
