"""Tests for the REST API with a custom frontmatter schema."""

import pathlib

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fastapi_blog
from fastapi_blog import FieldSpec, FrontmatterSchema, helpers
from fastapi_blog.editor import add_editor_to_app


# Every built-in field is renamed, like an external service would do.
EXTERNAL_SCHEMA = FrontmatterSchema(
  fields=(
    FieldSpec('headline', alias='title', required=True, role='title'),
    FieldSpec('pub_date', alias='pubDate', required=True, role='date'),
    FieldSpec('is_public', alias='isPublic', type='bool', role='published'),
    FieldSpec('labels', type='list[str]', role='tags'),
    FieldSpec('summary', role='description'),
    FieldSpec('author'),
  ),
)

VALID = {
  'frontmatter': {
    'title': 'Hello',
    'pubDate': '2024-05-01',
    'isPublic': True,
    'labels': ['x', 'y'],
    'summary': 'Short text',
  },
  'content': 'Body of the post',
}


def _read_frontmatter(path: pathlib.Path) -> dict:
  return yaml.safe_load(path.read_text().split('---')[1])


@pytest.fixture
def workdir(tmp_path, monkeypatch):
  (tmp_path / 'posts').mkdir()
  (tmp_path / 'pages').mkdir()
  monkeypatch.chdir(tmp_path)
  helpers.list_posts.cache_clear()
  yield tmp_path
  helpers.list_posts.cache_clear()


@pytest.fixture
def client(workdir):
  app = FastAPI()
  fastapi_blog.add_blog_to_fastapi(
    app,
    include_api=True,
    api_require_auth=False,
    frontmatter_schema=EXTERNAL_SCHEMA,
  )
  return TestClient(app)


def test_create_writes_external_keys(client, workdir):
  response = client.post('/api/posts/create/hello', json=VALID)
  assert response.status_code == 201

  frontmatter = _read_frontmatter(workdir / 'posts' / 'hello.md')
  assert frontmatter == {
    'title': 'Hello',
    'pubDate': '2024-05-01',
    'isPublic': True,
    'labels': ['x', 'y'],
    'summary': 'Short text',
  }
  assert 'headline' not in frontmatter
  assert 'pub_date' not in frontmatter


def test_created_post_is_visible_in_the_blog(client):
  client.post('/api/posts/create/hello', json=VALID)
  response = client.get('/blog/posts/hello')
  assert response.status_code == 200
  assert '<h1>Hello</h1>' in response.text
  assert 'Body of the post' in response.text
  assert 'Hello' in client.get('/blog/posts').text


def test_internal_names_are_accepted_too(client, workdir):
  payload = {
    'frontmatter': {'headline': 'By name', 'pub_date': '2024-05-02'},
    'content': 'Text',
  }
  assert (
    client.post('/api/posts/create/by-name', json=payload).status_code == 201
  )
  frontmatter = _read_frontmatter(workdir / 'posts' / 'by-name.md')
  assert frontmatter['title'] == 'By name'
  assert frontmatter['pubDate'] == '2024-05-02'


@pytest.mark.parametrize(
  'frontmatter',
  [
    {'title': 'No date'},  # required field is missing
    {'pubDate': '2024-05-01'},  # required field is missing
    {'title': 'T', 'pubDate': '2024-05-01', 'unknown': 1},  # extra is forbidden
    {'title': 'T', 'date': '2024-05-01'},  # key of the built-in format
  ],
)
def test_invalid_frontmatter_is_rejected(client, workdir, frontmatter):
  payload = {'frontmatter': frontmatter, 'content': 'Text'}
  response = client.post('/api/posts/create/bad', json=payload)
  assert response.status_code == 422
  assert not (workdir / 'posts' / 'bad.md').exists()


def test_create_conflict(client):
  assert client.post('/api/posts/create/dup', json=VALID).status_code == 201
  assert client.post('/api/posts/create/dup', json=VALID).status_code == 409


def test_update_changes_the_post(client, workdir):
  client.post('/api/posts/create/hello', json=VALID)
  updated = {
    'frontmatter': {**VALID['frontmatter'], 'title': 'Changed'},
    'content': 'New body',
  }
  assert client.put('/api/posts/update/hello', json=updated).status_code == 200
  assert _read_frontmatter(workdir / 'posts' / 'hello.md')['title'] == 'Changed'
  assert 'Changed' in client.get('/blog/posts/hello').text


def test_raw_returns_external_keys_and_can_be_sent_back(client):
  client.post('/api/posts/create/hello', json=VALID)
  raw = client.get('/api/posts/hello/raw').json()
  assert raw['slug'] == 'hello'
  assert raw['frontmatter']['pubDate'] == '2024-05-01'
  assert raw['content'].strip() == 'Body of the post'

  payload = {'frontmatter': raw['frontmatter'], 'content': raw['content']}
  assert client.put('/api/posts/update/hello', json=payload).status_code == 200


def test_delete(client, workdir):
  client.post('/api/posts/create/hello', json=VALID)
  assert client.delete('/api/posts/delete/hello').status_code == 204
  assert not (workdir / 'posts' / 'hello.md').exists()
  assert client.get('/blog/posts/hello').status_code == 404


def test_save_creates_then_updates_and_validates(client, workdir):
  data = {'slug': 'saved', **VALID}
  assert client.post('/api/posts/save', json=data).status_code == 201
  assert client.post('/api/posts/save', json=data).status_code == 200
  bad = {'slug': 'saved', 'frontmatter': {'title': 'T'}, 'content': 'Text'}
  assert client.post('/api/posts/save', json=bad).status_code == 400
  assert _read_frontmatter(workdir / 'posts' / 'saved.md')['title'] == 'Hello'


def test_openapi_documents_external_keys(client):
  text = client.get('/openapi.json').text
  assert 'pubDate' in text
  assert 'isPublic' in text


def test_draft_is_written_but_hidden_from_the_blog(client):
  payload = {
    'frontmatter': {**VALID['frontmatter'], 'isPublic': False},
    'content': 'Draft text',
  }
  assert client.post('/api/posts/create/draft', json=payload).status_code == 201
  assert client.get('/blog/posts/draft').status_code == 404


def test_date_type_round_trips_as_yaml_date(workdir):
  schema = FrontmatterSchema(
    fields=(
      FieldSpec('title', required=True, role='title'),
      FieldSpec('when', type='date', required=True, role='date'),
    )
  )
  app = FastAPI()
  fastapi_blog.add_blog_to_fastapi(
    app, include_api=True, api_require_auth=False, frontmatter_schema=schema
  )
  client = TestClient(app)
  payload = {
    'frontmatter': {'title': 'T', 'when': '2024-05-01'},
    'content': 'x',
  }
  assert client.post('/api/posts/create/dated', json=payload).status_code == 201
  assert 'when: 2024-05-01' in (workdir / 'posts' / 'dated.md').read_text()
  assert '2024-05-01' in client.get('/blog/posts').text


def test_extra_allow_keeps_unknown_keys(workdir):
  schema = FrontmatterSchema(
    fields=(FieldSpec('title', required=True, role='title'),), extra='allow'
  )
  app = FastAPI()
  fastapi_blog.add_blog_to_fastapi(
    app, include_api=True, api_require_auth=False, frontmatter_schema=schema
  )
  payload = {'frontmatter': {'title': 'T', 'cover': 'a.png'}, 'content': 'x'}
  response = TestClient(app).post('/api/posts/create/extra', json=payload)
  assert response.status_code == 201
  assert _read_frontmatter(workdir / 'posts' / 'extra.md')['cover'] == 'a.png'


def test_without_schema_the_api_is_unchanged(workdir):
  app = FastAPI()
  fastapi_blog.add_blog_to_fastapi(
    app, include_api=True, api_require_auth=False
  )
  payload = {
    'frontmatter': {'title': 'T', 'date': '2024-05-01', 'tags': ['a']},
    'content': 'x',
  }
  client = TestClient(app)
  assert client.post('/api/posts/create/plain', json=payload).status_code == 201
  assert _read_frontmatter(workdir / 'posts' / 'plain.md') == {
    'title': 'T',
    'date': '2024-05-01',
    'published': False,
    'tags': ['a'],
  }


def test_add_editor_to_app_accepts_a_schema(workdir):
  app = FastAPI()
  add_editor_to_app(
    app, ui=False, require_auth=False, frontmatter_schema=EXTERNAL_SCHEMA
  )
  response = TestClient(app).post('/api/posts/create/hello', json=VALID)
  assert response.status_code == 201
  assert (
    _read_frontmatter(workdir / 'posts' / 'hello.md')['pubDate'] == '2024-05-01'
  )


def test_deprecated_ui_with_a_schema_warns(workdir):
  app = FastAPI()
  with pytest.warns(UserWarning, match='doesn’t support `frontmatter_schema`'):
    add_editor_to_app(
      app, ui=True, require_auth=False, frontmatter_schema=EXTERNAL_SCHEMA
    )
