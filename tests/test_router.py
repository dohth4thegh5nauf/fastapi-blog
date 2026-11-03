import jinja2
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fastapi_blog


app = FastAPI()
# TODO - fix this to use PackageLoader
app = fastapi_blog.add_blog_to_fastapi(
  app, jinja2_loader=jinja2.FileSystemLoader('src/fastapi_blog/templates')
)

client = TestClient(app)


def test_blog_index():
  response = client.get('/blog')
  assert response.status_code == 200
  # `<title>` used to be hardcoded to the original fork author's name on
  # every page (TODO 5.9.6): `title`/`metadata` were never actually set in
  # any route's template context, so `layouts/base.html`'s fallback chain
  # always landed on its last, hardcoded branch.
  assert '<title>Daniel Roy Greenfeld</title>' not in response.content.decode()
  assert '<title>Recent Writings</title>' in response.content.decode()


def test_demo_posts_with_unquoted_timestamps_are_not_skipped():
  app = fastapi_blog.add_blog_to_fastapi(
    FastAPI(),
    posts_dirname='tests/examples/posts',
    strict_frontmatter=False,
    jinja2_loader=jinja2.FileSystemLoader('src/fastapi_blog/templates'),
  )
  with TestClient(app) as example_client:
    response = example_client.get('/blog/posts')

  assert response.status_code == 200
  assert 'Advanced Features' in response.text
  assert 'Getting Started with FastAPI Blog' in response.text
  assert 'Welcome to FastAPI Blog' in response.text


def test_html_routes_declare_response_class_without_query_parameters():
  schema = client.get('/openapi.json').json()
  html_paths = (
    '/blog/',
    '/blog/posts',
    '/blog/posts/{post_id}',
    '/blog/tags',
    '/blog/tags/{tag_id}',
    '/blog/{page_id}',
  )

  for path in html_paths:
    operation = schema['paths'][path]['get']
    parameter_names = {item['name'] for item in operation.get('parameters', [])}
    assert 'response_class' not in parameter_names
    assert 'text/html' in operation['responses']['200']['content']


def test_html_tag_has_a_lang_attribute():
  """TODO 5.9.6: `<html>` had no `lang` at all."""
  response = client.get('/blog')
  assert '<html lang="en">' in response.content.decode()


def test_no_fork_author_branding_remains_in_the_base_template():
  """The package must not ship the original fork author's own branding.

  TODO 5.9.6/П3: personal name, photo and social links aren't universal.
  """
  html = client.get('/blog').content.decode()
  assert 'Daniel Roy Greenfeld' not in html
  assert 'danielfeldroy' not in html
  assert 'pydanny' not in html


def test_post_page_has_its_own_title_and_description():
  app = fastapi_blog.add_blog_to_fastapi(
    FastAPI(),
    posts_dirname='tests/examples/posts',
    strict_frontmatter=False,
    jinja2_loader=jinja2.FileSystemLoader('src/fastapi_blog/templates'),
  )
  with TestClient(app) as c:
    html = c.get('/blog/posts/no-tags').content.decode()
  assert '<title>No Tags</title>' in html
  assert '<meta name="description" content="A post with no tags">' in html


def test_blog_post_rejects_path_traversal_post_id():
  """A `..`-based `post_id` must 404, never read a file outside posts_dirname.

  It's already caught by the `_list_posts()` whitelist check, but the route
  also runs the id through `store.safe_document_path` as a second, explicit
  guard before any file read.
  """
  response = client.get('/blog/posts/..%2f..%2fpyproject')
  assert response.status_code == 404


# --- JSON-LD routes (TODO 5.4), off by default ------------------------------


def test_jsonld_routes_are_off_by_default():
  response = client.get('/blog/welcome.jsonld')
  # falls through to the `/{page_id}` catch-all, which 404s for this slug
  assert response.status_code == 404


def _jsonld_app():
  return fastapi_blog.add_blog_to_fastapi(
    FastAPI(),
    posts_dirname='tests/examples/posts',
    strict_frontmatter=False,
    jinja2_loader=jinja2.FileSystemLoader('src/fastapi_blog/templates'),
    jsonld_routes=True,
  )


def test_jsonld_post_route_returns_ld_json():
  with TestClient(_jsonld_app()) as c:
    response = c.get('/blog/no-tags.jsonld')
  assert response.status_code == 200
  assert response.headers['content-type'] == 'application/ld+json'
  assert response.json()['title'] == 'No Tags'


def test_jsonld_post_route_404s_for_a_missing_post():
  with TestClient(_jsonld_app()) as c:
    response = c.get('/blog/does-not-exist.jsonld')
  assert response.status_code == 404


def test_jsonld_routes_only_expose_published_posts(tmp_path, monkeypatch):
  monkeypatch.chdir(tmp_path)
  posts_dir = tmp_path / 'posts'
  posts_dir.mkdir()
  (posts_dir / 'live.md').write_text(
    '---\ntitle: Live Post\ndate: "2024-01-01"\npublished: true\n---\nBody\n'
  )
  (posts_dir / 'draft.md').write_text(
    '---\ntitle: Draft Post\ndate: "2024-01-02"\npublished: false\n---\nBody\n'
  )
  app = fastapi_blog.add_blog_to_fastapi(
    FastAPI(),
    posts_dirname='posts',
    jinja2_loader=jinja2.FileSystemLoader('src/fastapi_blog/templates'),
    jsonld_routes=True,
  )
  with TestClient(app) as c:
    live = c.get('/blog/live.jsonld')
    draft = c.get('/blog/draft.jsonld')
    index = c.get('/blog/index.jsonld')

  assert live.status_code == 200
  assert live.json()['title'] == 'Live Post'
  assert draft.status_code == 404

  titles = {node['title'] for node in index.json()['@graph']}
  assert titles == {'Live Post'}


def test_post_body_survives_a_horizontal_rule():
  """A `---` in the body (e.g. a horizontal rule) must not truncate it."""
  app = fastapi_blog.add_blog_to_fastapi(
    FastAPI(),
    posts_dirname='tests/examples/posts',
    strict_frontmatter=False,
    jinja2_loader=jinja2.FileSystemLoader('src/fastapi_blog/templates'),
  )
  with TestClient(app) as examples_client:
    response = examples_client.get('/blog/posts/thirty-minute-rule')
  assert response.status_code == 200
  html = response.content.decode()
  assert 'Grammar correction thanks to Vadym Khodak' in html
