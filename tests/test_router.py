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
  assert '<title>Daniel Roy Greenfeld</title>' in response.content.decode()


def test_blog_post_rejects_path_traversal_post_id():
  """A `..`-based `post_id` must 404, never read a file outside posts_dirname.

  It's already caught by the `_list_posts()` whitelist check, but the route
  also runs the id through `store.safe_document_path` as a second, explicit
  guard before any file read.
  """
  response = client.get('/blog/posts/..%2f..%2fpyproject')
  assert response.status_code == 404


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
