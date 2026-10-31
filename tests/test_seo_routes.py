"""Integration coverage for the optional SEO endpoints (TODO 5.9.5)."""

import xml.etree.ElementTree as ET

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fastapi_blog import add_blog_to_fastapi, helpers, main
from fastapi_blog.auth import ConfigurationError
from fastapi_blog.models import FieldSpec, FrontmatterSchema, SeoConfig
from fastapi_blog.seo import seo_fields


NS = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
SITE = 'https://example.test'


def _published_posts():
  return (
    {
      'slug': 'first-post',
      'title': 'First post',
      'date': '2026-01-02',
      'updated': '2026-01-03',
      'tags': ['python'],
      'robots': [],
      'redirect_from': ['old-post'],
    },
    {
      'slug': 'hidden-post',
      'title': 'Hidden post',
      'date': '2026-01-01',
      'robots': ['noindex'],
      'tags': ['private'],
      'redirect_from': ['old-hidden'],
    },
    {
      'slug': 'external-canonical',
      'title': 'External canonical',
      'date': '2025-12-01',
      'canonical': 'https://other.example/post',
      'tags': [],
    },
  )


def _locs(content: bytes) -> list[str]:
  root = ET.fromstring(content)
  return [node.text for node in root.findall('s:url/s:loc', NS)]


def test_sitemap_is_sorted_and_excludes_noindex_and_foreign_canonical(
  monkeypatch,
):
  monkeypatch.setattr(
    helpers, 'list_posts', lambda **kwargs: _published_posts()
  )
  app = FastAPI()
  add_blog_to_fastapi(app, seo=SeoConfig(site_url=SITE), seo_routes=True)
  with TestClient(app) as client:
    first, second = client.get('/sitemap.xml'), client.get('/sitemap.xml')
  assert first.status_code == 200
  assert first.content == second.content
  locs = _locs(first.content)
  assert locs == sorted(locs)
  assert f'{SITE}/blog/' in locs
  assert f'{SITE}/blog/posts' in locs
  assert f'{SITE}/blog/posts/first-post' in locs
  assert f'{SITE}/blog/posts/hidden-post' not in locs
  assert 'https://other.example/post' not in locs
  assert f'{SITE}/blog/posts/external-canonical' not in locs
  assert f'{SITE}/blog/tags/python' in locs
  # Tags of excluded documents don't leak into the sitemap
  assert f'{SITE}/blog/tags/private' not in locs


def test_sitemap_lastmod_prefers_updated_and_has_no_priority(monkeypatch):
  monkeypatch.setattr(
    helpers, 'list_posts', lambda **kwargs: _published_posts()
  )
  app = FastAPI()
  add_blog_to_fastapi(app, seo=SeoConfig(site_url=SITE), seo_routes=True)
  with TestClient(app) as client:
    root = ET.fromstring(client.get('/sitemap.xml').content)
  by_loc = {
    node.find('s:loc', NS).text: node.find('s:lastmod', NS)
    for node in root.findall('s:url', NS)
  }
  assert by_loc[f'{SITE}/blog/posts/first-post'].text == '2026-01-03'
  assert by_loc[f'{SITE}/blog/'] is None
  assert b'priority' not in ET.tostring(root)
  assert b'changefreq' not in ET.tostring(root)


def test_sitemap_omits_tag_pages_when_they_are_noindex(monkeypatch):
  monkeypatch.setattr(
    helpers, 'list_posts', lambda **kwargs: _published_posts()
  )
  app = FastAPI()
  add_blog_to_fastapi(
    app, seo=SeoConfig(site_url=SITE, noindex_tags=True), seo_routes=True
  )
  with TestClient(app) as client:
    locs = _locs(client.get('/sitemap.xml').content)
  assert f'{SITE}/blog/posts/first-post' in locs
  assert not [loc for loc in locs if '/tags/' in loc]


def test_sitemap_is_split_into_an_index_over_the_url_limit(monkeypatch):
  monkeypatch.setattr(
    helpers, 'list_posts', lambda **kwargs: _published_posts()
  )
  monkeypatch.setattr(main, 'SITEMAP_URL_LIMIT', 2)
  app = FastAPI()
  add_blog_to_fastapi(app, seo=SeoConfig(site_url=SITE), seo_routes=True)
  with TestClient(app) as client:
    index = client.get('/sitemap.xml')
    root = ET.fromstring(index.content)
    parts = [n.text for n in root.findall('s:sitemap/s:loc', NS)]
    # blog index, posts, first-post, python tag -> two files of two URLs
    assert parts == [f'{SITE}/sitemap-1.xml', f'{SITE}/sitemap-2.xml']
    first = _locs(client.get('/sitemap-1.xml').content)
    second = _locs(client.get('/sitemap-2.xml').content)
    assert len(first) == len(second) == 2
    assert first + second == sorted(first + second)
    assert client.get('/sitemap-3.xml').status_code == 404
    assert client.get('/sitemap-0.xml').status_code == 404
    assert client.get('/sitemap-x.xml').status_code == 404


def test_sitemap_parts_are_404_when_one_file_is_enough(monkeypatch):
  monkeypatch.setattr(
    helpers, 'list_posts', lambda **kwargs: _published_posts()
  )
  app = FastAPI()
  add_blog_to_fastapi(app, seo=SeoConfig(site_url=SITE), seo_routes=True)
  with TestClient(app) as client:
    assert client.get('/sitemap-1.xml').status_code == 404


def test_robots_txt_and_redirect_from_return_expected_responses(monkeypatch):
  monkeypatch.setattr(
    helpers, 'list_posts', lambda **kwargs: _published_posts()
  )
  app = FastAPI()
  add_blog_to_fastapi(
    app,
    seo=SeoConfig(site_url=SITE, disallow=['/admin', '/private']),
    seo_routes=True,
  )
  with TestClient(app, follow_redirects=False) as client:
    robots = client.get('/robots.txt')
    redirect = client.get('/blog/posts/old-post')
    head_redirect = client.head('/blog/posts/old-post')
    # `noindex` keeps a document out of the sitemap, not out of redirects
    noindex_redirect = client.get('/blog/posts/old-hidden')
    unknown = client.get('/blog/posts/never-existed')
  assert robots.status_code == 200
  assert robots.text.startswith('User-agent: *\n')
  assert 'Disallow: /admin' in robots.text
  assert 'Disallow: /private' in robots.text
  assert 'Allow: /' not in robots.text
  assert f'Sitemap: {SITE}/sitemap.xml' in robots.text
  assert redirect.status_code == 301
  assert redirect.headers['location'] == f'{SITE}/blog/posts/first-post'
  assert head_redirect.status_code == 301
  assert noindex_redirect.status_code == 301
  assert unknown.status_code == 404


def test_robots_txt_allows_everything_without_disallow(monkeypatch):
  monkeypatch.setattr(helpers, 'list_posts', lambda **kwargs: ())
  app = FastAPI()
  add_blog_to_fastapi(app, seo=SeoConfig(site_url=SITE), seo_routes=True)
  with TestClient(app) as client:
    robots = client.get('/robots.txt')
  assert (
    robots.text == f'User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n'
  )


def test_redirect_from_with_a_site_path_and_a_foreign_canonical(monkeypatch):
  posts = (
    {
      'slug': 'moved',
      'title': 'Moved',
      'redirect_from': ['/2019/old-moved/', 'blog/posts/older'],
    },
    {
      'slug': 'elsewhere',
      'title': 'Elsewhere',
      'canonical': 'https://other.example/elsewhere',
      'redirect_from': ['gone'],
    },
  )
  monkeypatch.setattr(helpers, 'list_posts', lambda **kwargs: posts)
  app = FastAPI()
  add_blog_to_fastapi(app, seo=SeoConfig(site_url=SITE), seo_routes=True)
  with TestClient(app, follow_redirects=False) as client:
    path = client.get('/2019/old-moved')
    trailing = client.get('/2019/old-moved/')
    prefixed = client.get('/blog/posts/older')
    foreign = client.get('/blog/posts/gone')
  assert path.status_code == trailing.status_code == 301
  assert path.headers['location'] == f'{SITE}/blog/posts/moved'
  assert prefixed.headers['location'] == f'{SITE}/blog/posts/moved'
  assert foreign.headers['location'] == 'https://other.example/elsewhere'


def test_redirect_from_never_loops_or_hides_a_live_post(monkeypatch):
  posts = (
    {'slug': 'a', 'title': 'A', 'redirect_from': ['a', 'b', 'blog']},
    {'slug': 'b', 'title': 'B', 'redirect_from': ['robots.txt', '/']},
  )
  monkeypatch.setattr(helpers, 'list_posts', lambda **kwargs: posts)
  app = FastAPI()
  add_blog_to_fastapi(app, seo=SeoConfig(site_url=SITE), seo_routes=True)
  with TestClient(
    app, follow_redirects=False, raise_server_exceptions=False
  ) as client:
    # Neither its own address nor a live post's address is an alias (the
    # mocked posts have no files, so the page itself answers 500, not 301)
    assert client.get('/blog/posts/a').status_code != 301
    assert client.get('/blog/posts/b').status_code != 301
    # robots.txt and the site root keep their own answers
    assert client.get('/robots.txt').status_code == 200
    assert client.get('/').status_code == 302


def test_redirect_from_matches_non_ascii_and_encoded_aliases(monkeypatch):
  """Starlette matches the decoded path; the target URL stays encoded."""
  posts = (
    {
      'slug': 'новый',
      'title': 'N',
      'redirect_from': ['старый', '/блог/путь', 'a%20b'],
    },
  )
  monkeypatch.setattr(helpers, 'list_posts', lambda **kwargs: posts)
  app = FastAPI()
  add_blog_to_fastapi(app, seo=SeoConfig(site_url=SITE), seo_routes=True)
  target = f'{SITE}/blog/posts/%D0%BD%D0%BE%D0%B2%D1%8B%D0%B9'
  with TestClient(app, follow_redirects=False) as client:
    for path in ('/blog/posts/старый', '/блог/путь', '/blog/posts/a%20b'):
      response = client.get(path)
      assert response.status_code == 301, path
      assert response.headers['location'] == target


def test_redirect_from_only_redirects_reads(monkeypatch):
  monkeypatch.setattr(
    helpers, 'list_posts', lambda **kwargs: _published_posts()
  )
  app = FastAPI()
  add_blog_to_fastapi(app, seo=SeoConfig(site_url=SITE), seo_routes=True)
  with TestClient(app, follow_redirects=False) as client:
    assert client.post('/blog/posts/old-post').status_code != 301


def test_seo_routes_work_without_a_prefix(monkeypatch):
  """`/{page_id}` is a catch-all there; the SEO routes must win over it."""
  monkeypatch.setattr(
    helpers, 'list_posts', lambda **kwargs: _published_posts()
  )
  app = FastAPI()
  add_blog_to_fastapi(
    app, prefix=None, seo=SeoConfig(site_url=SITE), seo_routes=True
  )
  with TestClient(app, follow_redirects=False) as client:
    robots = client.get('/robots.txt')
    sitemap = client.get('/sitemap.xml')
    redirect = client.get('/posts/old-post')
  assert robots.status_code == 200
  assert robots.headers['content-type'].startswith('text/plain')
  assert sitemap.status_code == 200
  assert f'{SITE}/posts/first-post' in _locs(sitemap.content)
  assert redirect.status_code == 301
  assert redirect.headers['location'] == f'{SITE}/posts/first-post'


def test_seo_routes_are_off_by_default(monkeypatch):
  monkeypatch.setattr(
    helpers, 'list_posts', lambda **kwargs: _published_posts()
  )
  app = FastAPI()
  add_blog_to_fastapi(app, seo=SeoConfig(site_url=SITE))
  with TestClient(app, follow_redirects=False) as client:
    assert client.get('/sitemap.xml').status_code == 404
    assert client.get('/robots.txt').status_code == 404
    assert client.get('/blog/posts/old-post').status_code == 404


def test_seo_routes_use_the_schema_section_too(monkeypatch):
  monkeypatch.setattr(helpers, 'list_posts', lambda **kwargs: ())
  schema = FrontmatterSchema(
    fields=(FieldSpec('title', required=True, role='title'),),
    seo=SeoConfig(site_url=SITE),
  )
  app = FastAPI()
  add_blog_to_fastapi(app, frontmatter_schema=schema, seo_routes=True)
  with TestClient(app) as client:
    assert f'Sitemap: {SITE}/sitemap.xml' in client.get('/robots.txt').text


def test_seo_routes_requires_site_url_at_startup():
  app = FastAPI()
  add_blog_to_fastapi(app, seo_routes=True)
  with pytest.raises(ConfigurationError, match='seo.site_url'):
    with TestClient(app):
      pass


def test_seo_routes_with_an_empty_seo_section_still_need_site_url():
  app = FastAPI()
  add_blog_to_fastapi(app, seo=SeoConfig(), seo_routes=True)
  with pytest.raises(ConfigurationError, match='seo.site_url'):
    with TestClient(app):
      pass


@pytest.mark.parametrize(
  ('value', 'expected'),
  [
    ('2026-01-03', '2026-01-03'),
    ('2026-01-03T10:00:00Z', '2026-01-03T10:00:00Z'),
    ('2026-01-03T10:00:00+02:00', '2026-01-03T10:00:00+02:00'),
    # No zone: not a valid W3C Datetime
    ('2026-01-03T10:00:00', None),
    ('last Tuesday', None),
    ('', None),
  ],
)
def test_lastmod_accepts_only_w3c_datetimes(value, expected):
  assert main._lastmod({'date': value}) == expected


def test_lastmod_handles_date_objects_and_zones():
  import datetime

  aware = datetime.datetime(2026, 1, 3, 10, 0, tzinfo=datetime.UTC)
  assert main._lastmod({'updated': aware}) == '2026-01-03T10:00:00+00:00'
  naive = datetime.datetime(2026, 1, 3, 10, 0)
  assert main._lastmod({'date': naive}) == '2026-01-03'
  assert main._lastmod({'date': datetime.date(2026, 1, 3)}) == '2026-01-03'
  assert main._lastmod({}) is None


@pytest.fixture
def blog_dir(tmp_path, monkeypatch):
  """Create a posts directory with a published and a draft post."""
  posts = tmp_path / 'posts'
  posts.mkdir()
  (posts / 'live.md').write_text(
    '---\ntitle: Live\ndate: 2026-02-01\npublished: true\n'
    'redirect_from: [old-live]\n---\nBody\n',
    encoding='utf-8',
  )
  (posts / 'draft.md').write_text(
    '---\ntitle: Draft\ndate: 2026-02-02\npublished: false\n'
    'redirect_from: [old-draft]\n---\nBody\n',
    encoding='utf-8',
  )
  monkeypatch.chdir(tmp_path)
  helpers.clear_posts_cache()
  yield tmp_path
  helpers.clear_posts_cache()


def _real_schema() -> FrontmatterSchema:
  return FrontmatterSchema(
    fields=(
      FieldSpec('title', required=True, role='title'),
      FieldSpec('date', type='date', role='date'),
      FieldSpec('published', type='bool', default=True, role='published'),
      *seo_fields(),
    ),
  )


def test_unpublished_documents_create_no_redirects_and_no_sitemap_entry(
  blog_dir,
):
  app = FastAPI()
  add_blog_to_fastapi(
    app,
    frontmatter_schema=_real_schema(),
    seo=SeoConfig(site_url=SITE),
    seo_routes=True,
  )
  with TestClient(app, follow_redirects=False) as client:
    live = client.get('/blog/posts/old-live')
    draft = client.get('/blog/posts/old-draft')
    locs = _locs(client.get('/sitemap.xml').content)
  assert live.status_code == 301
  assert live.headers['location'] == f'{SITE}/blog/posts/live'
  assert draft.status_code == 404
  assert f'{SITE}/blog/posts/live' in locs
  assert f'{SITE}/blog/posts/draft' not in locs


def test_redirect_index_follows_changes_in_the_posts_directory(blog_dir):
  app = FastAPI()
  add_blog_to_fastapi(
    app,
    frontmatter_schema=_real_schema(),
    seo=SeoConfig(site_url=SITE),
    seo_routes=True,
  )
  with TestClient(app, follow_redirects=False) as client:
    assert client.get('/blog/posts/newer-alias').status_code == 404
    (blog_dir / 'posts' / 'live.md').write_text(
      '---\ntitle: Live\ndate: 2026-02-01\npublished: true\n'
      'redirect_from: [newer-alias]\n---\nBody, longer now\n',
      encoding='utf-8',
    )
    assert client.get('/blog/posts/newer-alias').status_code == 301
    assert client.get('/blog/posts/old-live').status_code == 404
