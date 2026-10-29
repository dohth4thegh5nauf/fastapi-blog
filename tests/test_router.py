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
