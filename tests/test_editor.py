import pathlib
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fastapi_blog import add_blog_to_fastapi, add_editor_to_app, helpers
from fastapi_blog.config import CollectionSpec
from fastapi_blog.editor import get_api_router
from fastapi_blog.i18n_collections import I18nConfig
from fastapi_blog.models import FieldSpec, FrontmatterSchema
from fastapi_blog.templates import SLUG_TAGS_DEFAULT, parse_template
from fastapi_blog.validators import Validator


@pytest.fixture
def app_dir(tmp_path, monkeypatch):
  (tmp_path / 'posts').mkdir()
  (tmp_path / 'pages').mkdir()
  monkeypatch.chdir(tmp_path)
  helpers.list_posts.cache_clear()
  yield tmp_path
  helpers.list_posts.cache_clear()


@pytest.fixture
def client(app_dir):
  app = FastAPI()
  app = add_blog_to_fastapi(app, prefix='blog')
  app = add_editor_to_app(app, require_auth=False)  # Disable auth for tests
  return TestClient(app)


@pytest.fixture
def loose_client(app_dir):
  app = FastAPI()
  app = add_blog_to_fastapi(
    app, prefix='blog', strict_frontmatter=False, sanitize_html=False
  )
  # Disable auth for tests
  app = add_editor_to_app(app, strict=False, require_auth=False)
  return TestClient(app)


@pytest.fixture
def auth_client(app_dir):
  """Client with authentication enabled."""
  # Sessions need `itsdangerous` (extra `admin`)
  pytest.importorskip('itsdangerous')
  from starlette.middleware.sessions import SessionMiddleware

  app = FastAPI()
  app.add_middleware(SessionMiddleware, secret_key='test-secret-key')
  app = add_blog_to_fastapi(app, prefix='blog')
  app = add_editor_to_app(app, require_auth=True)  # Auth enabled
  return TestClient(app)


VALID_PAYLOAD = {
  'frontmatter': {
    'title': 'Hello World',
    'date': '2026-04-18',
    'published': True,
    'tags': ['greeting'],
    'description': 'First post',
  },
  'content': '# Hello\n\nThis is a test post.',
}


def test_create_post_success(client, app_dir):
  response = client.post('/api/posts/create/hello-world', json=VALID_PAYLOAD)
  assert response.status_code == 201
  assert response.json() == {'slug': 'hello-world', 'status': 'created'}
  assert (app_dir / 'posts' / 'hello-world.md').is_file()


def test_generated_slug_api_create(app_dir):
  spec = CollectionSpec(
    name='posts',
    dir=app_dir / 'posts',
    slug_template=parse_template(
      '{seq|pad(4)}-{title_slug}',
      SLUG_TAGS_DEFAULT,
      {'title', 'date', 'published', 'tags', 'description'},
    ),
  )
  app = FastAPI()
  app = add_blog_to_fastapi(app, prefix='blog')
  app = add_editor_to_app(
    app, ui=False, require_auth=False, collection_spec=spec
  )
  client = TestClient(app)

  response = client.post(
    '/api/posts/create',
    json={
      'frontmatter': {
        'title': 'Hello Generated',
        'date': '2026-10-31',
        'published': True,
        'tags': ['generated'],
        'description': 'Generated slug test',
      },
      'content': 'Body',
    },
  )

  assert response.status_code == 201
  assert response.json() == {
    'slug': '0001-hello-generated',
    'status': 'created',
  }
  assert response.headers.get('etag')
  assert (app_dir / 'posts' / '0001-hello-generated.md').is_file()


def test_manual_slug_cannot_reuse_a_unique_sequence(app_dir):
  (app_dir / 'posts' / '0001-existing.md').write_text(
    '---\ntitle: Existing\n---\nBody\n', encoding='utf-8'
  )
  spec = CollectionSpec(
    name='posts',
    dir=app_dir / 'posts',
    slug_template=parse_template(
      '{seq|pad(4)}-{title_slug}',
      SLUG_TAGS_DEFAULT,
      {'title', 'date', 'published', 'tags', 'description'},
    ),
    unique=('seq',),
  )
  app = FastAPI()
  app = add_blog_to_fastapi(app, prefix='blog')
  app = add_editor_to_app(
    app, ui=False, require_auth=False, collection_spec=spec
  )
  response = TestClient(app).post(
    '/api/posts/create/0001-another', json=VALID_PAYLOAD
  )
  assert response.status_code == 409
  assert 'unique field' in response.json()['detail']
  assert not (app_dir / 'posts' / '0001-another.md').exists()


def test_generated_slug_uses_utc_first_save_when_date_is_empty(
  app_dir, monkeypatch
):
  from fastapi_blog import service

  class FrozenDateTime:
    @staticmethod
    def now(tz):
      assert tz is UTC
      return datetime(2024, 2, 3, 23, 30, tzinfo=UTC)

  # The first-save timestamp is taken by the document service.
  monkeypatch.setattr(service, 'datetime', FrozenDateTime)
  schema = FrontmatterSchema(
    fields=(FieldSpec('title', required=True, role='title'),)
  )
  spec = CollectionSpec(
    name='posts',
    dir=app_dir / 'posts',
    schema=schema,
    slug_template=parse_template(
      '{year}-{month}-{day}-{title_slug}',
      SLUG_TAGS_DEFAULT,
      {'title'},
    ),
  )
  app = FastAPI()
  app = add_blog_to_fastapi(app, prefix='blog', frontmatter_schema=schema)
  app = add_editor_to_app(
    app,
    ui=False,
    require_auth=False,
    frontmatter_schema=schema,
    collection_spec=spec,
  )
  client = TestClient(app)

  response = client.post(
    '/api/posts/create',
    json={'frontmatter': {'title': 'First Save'}, 'content': 'Body'},
  )

  assert response.status_code == 201
  assert response.json()['slug'] == '2024-02-03-first-save'


def test_generated_slug_runs_blocking_validators_and_rolls_back(app_dir):
  events = []
  spec = CollectionSpec(
    name='posts',
    dir=app_dir / 'posts',
    slug_template=parse_template(
      '{seq|pad(4)}-{title_slug}',
      SLUG_TAGS_DEFAULT,
      {'title', 'date', 'published', 'tags', 'description'},
    ),
    on_change=events.append,
    validators=(
      Validator.from_dict(
        {
          'name': 'reject',
          'argv': [sys.executable, '-c', 'import sys; sys.exit(1)'],
          'blocking': ['error'],
        }
      ),
    ),
  )
  app = FastAPI()
  app = add_editor_to_app(
    app, ui=False, require_auth=False, collection_spec=spec
  )
  client = TestClient(app)

  response = client.post(
    '/api/posts/create',
    json={
      'frontmatter': {
        'title': 'Rejected Generated',
        'date': '2026-10-31',
        'published': True,
        'tags': [],
        'description': '',
      },
      'content': 'Body',
    },
  )

  assert response.status_code == 422
  assert not (app_dir / 'posts' / '0001-rejected-generated.md').exists()
  assert events == []


def test_generated_slug_save_endpoint(app_dir):
  spec = CollectionSpec(
    name='posts',
    dir=app_dir / 'posts',
    slug_template=parse_template(
      '{seq|pad(4)}-{title_slug}',
      SLUG_TAGS_DEFAULT,
      {'title', 'date', 'published', 'tags', 'description'},
    ),
  )
  app = FastAPI()
  app = add_blog_to_fastapi(app, prefix='blog')
  app = add_editor_to_app(
    app, ui=False, require_auth=False, collection_spec=spec
  )
  client = TestClient(app)

  response = client.post(
    '/api/posts/save',
    json={'slug': '', **VALID_PAYLOAD},
  )

  assert response.status_code == 201
  assert response.json()['slug'] == '0001-hello-world'
  assert (app_dir / 'posts' / '0001-hello-world.md').is_file()


def test_create_post_conflict(client, app_dir):
  (app_dir / 'posts' / 'hello-world.md').write_text(
    "---\ntitle: x\ndate: '2026-01-01'\n---\nbody\n"
  )
  response = client.post('/api/posts/create/hello-world', json=VALID_PAYLOAD)
  assert response.status_code == 409


def test_create_post_invalid_slug(client):
  response = client.post('/api/posts/create/Bad_Slug', json=VALID_PAYLOAD)
  assert response.status_code == 422


def test_create_post_path_traversal(client):
  response = client.post(
    '/api/posts/create/..%2F..%2Fetc%2Fpasswd', json=VALID_PAYLOAD
  )
  assert response.status_code in {404, 422}


def test_create_post_invalid_frontmatter(client):
  bad = {'frontmatter': {'title': 'x'}, 'content': 'body'}  # missing date
  response = client.post('/api/posts/create/missing-date', json=bad)
  assert response.status_code == 422


def test_create_post_strict_rejects_extras(client):
  bad = {
    'frontmatter': {**VALID_PAYLOAD['frontmatter'], 'image': '/x.png'},
    'content': 'body',
  }
  response = client.post('/api/posts/create/with-extra', json=bad)
  assert response.status_code == 422


def test_create_post_loose_accepts_extras(loose_client, app_dir):
  body = {
    'frontmatter': {**VALID_PAYLOAD['frontmatter'], 'image': '/x.png'},
    'content': 'body',
  }
  response = loose_client.post('/api/posts/create/with-extra', json=body)
  assert response.status_code == 201
  saved = (app_dir / 'posts' / 'with-extra.md').read_text()
  assert 'image: /x.png' in saved


def test_get_raw_success(client, app_dir):
  client.post('/api/posts/create/hello-world', json=VALID_PAYLOAD)
  response = client.get('/api/posts/hello-world/raw')
  assert response.status_code == 200
  body = response.json()
  assert body['slug'] == 'hello-world'
  assert body['frontmatter']['title'] == 'Hello World'
  assert '# Hello' in body['content']


def test_get_raw_not_found(client):
  response = client.get('/api/posts/missing/raw')
  assert response.status_code == 404


def test_update_post_success(client, app_dir):
  client.post('/api/posts/create/hello-world', json=VALID_PAYLOAD)
  updated = {
    **VALID_PAYLOAD,
    'frontmatter': {**VALID_PAYLOAD['frontmatter'], 'title': 'Updated'},
    'content': 'new body',
  }
  response = client.put('/api/posts/update/hello-world', json=updated)
  assert response.status_code == 200
  saved = (app_dir / 'posts' / 'hello-world.md').read_text()
  assert 'title: Updated' in saved
  assert 'new body' in saved


def test_update_post_not_found(client):
  response = client.put('/api/posts/update/missing', json=VALID_PAYLOAD)
  assert response.status_code == 404


def test_delete_post_success(client, app_dir):
  client.post('/api/posts/create/hello-world', json=VALID_PAYLOAD)
  response = client.delete('/api/posts/delete/hello-world')
  assert response.status_code == 204
  assert not (app_dir / 'posts' / 'hello-world.md').exists()


def test_delete_post_not_found(client):
  response = client.delete('/api/posts/delete/missing')
  assert response.status_code == 404


def test_create_invalidates_cache(client, app_dir):
  # populate cache with empty list
  assert helpers.list_posts(posts_dirname='posts') == ()
  client.post('/api/posts/create/hello-world', json=VALID_PAYLOAD)
  posts = helpers.list_posts(posts_dirname='posts')
  assert len(posts) == 1
  assert posts[0]['title'] == 'Hello World'


def test_blog_index_after_create(client):
  client.post('/api/posts/create/hello-world', json=VALID_PAYLOAD)
  response = client.get('/blog/posts')
  assert response.status_code == 200
  assert 'Hello World' in response.text


def test_ui_list_empty(client):
  response = client.get('/admin/editor/')
  assert response.status_code == 200
  assert 'No posts yet' in response.text


def test_ui_list_shows_posts(client):
  client.post('/api/posts/create/hello-world', json=VALID_PAYLOAD)
  response = client.get('/admin/editor/')
  assert response.status_code == 200
  assert 'Hello World' in response.text
  assert 'hello-world' in response.text


def test_ui_new_page(client):
  response = client.get('/admin/editor/new')
  assert response.status_code == 200
  assert 'easymde' in response.text.lower()
  assert 'id="slug"' in response.text


def test_ui_edit_page_prefills(client):
  client.post('/api/posts/create/hello-world', json=VALID_PAYLOAD)
  response = client.get('/admin/editor/hello-world')
  assert response.status_code == 200
  assert 'Hello World' in response.text
  assert 'greeting' in response.text
  assert 'readonly' in response.text


def test_ui_edit_404_for_missing(client):
  response = client.get('/admin/editor/does-not-exist')
  assert response.status_code == 404


def test_ui_disabled(app_dir):
  from fastapi import FastAPI

  app = FastAPI()
  app = add_blog_to_fastapi(app, prefix='blog')
  app = add_editor_to_app(app, ui=False)
  ui_client = TestClient(app)
  response = ui_client.get('/admin/editor/')
  assert response.status_code == 404


# ============================================================================
# Authentication Tests
# ============================================================================


def test_create_post_requires_auth(auth_client, app_dir):
  """Test that creating a post without authentication fails."""
  response = auth_client.post('/api/posts/create/test-post', json=VALID_PAYLOAD)
  assert response.status_code == 401
  assert 'authentication required' in response.json()['detail'].lower()


def test_update_post_requires_auth(auth_client, app_dir):
  """Test that updating a post without authentication fails."""
  # Create post first (without auth, so it will fail)
  (app_dir / 'posts' / 'test-post.md').write_text(
    "---\ntitle: Test\ndate: '2026-01-01'\npublished: true\n---\nbody\n"
  )
  response = auth_client.put('/api/posts/update/test-post', json=VALID_PAYLOAD)
  assert response.status_code == 401


def test_delete_post_requires_auth(auth_client, app_dir):
  """Test that deleting a post without authentication fails."""
  (app_dir / 'posts' / 'test-post.md').write_text(
    "---\ntitle: Test\ndate: '2026-01-01'\npublished: true\n---\nbody\n"
  )
  response = auth_client.delete('/api/posts/delete/test-post')
  assert response.status_code == 401


def test_get_raw_requires_auth(auth_client, app_dir):
  """Test that getting raw post data without authentication fails."""
  (app_dir / 'posts' / 'test-post.md').write_text(
    "---\ntitle: Test\ndate: '2026-01-01'\npublished: true\n---\nbody\n"
  )
  response = auth_client.get('/api/posts/test-post/raw')
  assert response.status_code == 401


def test_save_post_requires_auth(auth_client, app_dir):
  """Test that saving a post without authentication fails."""
  data = {
    'slug': 'test-post',
    'frontmatter': VALID_PAYLOAD['frontmatter'],
    'content': VALID_PAYLOAD['content'],
  }
  response = auth_client.post('/api/posts/save', json=data)
  assert response.status_code == 401


def test_require_auth_false_allows_public_access(app_dir):
  """Test that require_auth=False allows public access (for testing)."""
  app = FastAPI()
  app = add_blog_to_fastapi(app, prefix='blog')
  app = add_editor_to_app(app, require_auth=False)  # Public access

  client = TestClient(app)

  # Should be able to create without auth
  response = client.post('/api/posts/create/public-test', json=VALID_PAYLOAD)
  assert response.status_code == 201
  assert (app_dir / 'posts' / 'public-test.md').is_file()


@pytest.mark.skip(
  reason=(
    'Session cookie handling in TestClient needs integration '
    'with actual admin panel'
  )
)
def test_create_post_with_auth(app_dir):
  """Test that creating a post WITH authentication succeeds.

  Note: This test is skipped because manually creating session cookies
  for TestClient is complex. The authentication requirement is already
  tested in other tests (test_create_post_requires_auth, etc.).

  In a real application, authentication would be done through:
  1. Login via admin panel (starlette-admin)
  2. Session cookie automatically set by SessionMiddleware
  3. Subsequent requests use that session
  """
  pass


def test_ui_routes_require_auth(auth_client, app_dir):
  """Test that all UI editor routes require authentication."""
  # Create a test post for edit route
  (app_dir / 'posts' / 'test-post.md').write_text(
    "---\ntitle: Test\ndate: '2026-01-01'\npublished: true\n---\nbody\n"
  )

  # Test all UI routes without authentication
  ui_routes = [
    '/admin/editor/',
    '/admin/editor/new',
    '/admin/editor/test-post',
  ]

  for route in ui_routes:
    response = auth_client.get(route)
    assert response.status_code == 401, f'Route {route} should require auth'


# --- etag / If-Match concurrency via the REST API (TODO 4.7) ----------------


def test_get_raw_returns_an_etag_header(client, app_dir):
  client.post('/api/posts/create/hello-world', json=VALID_PAYLOAD)
  response = client.get('/api/posts/hello-world/raw')
  assert response.status_code == 200
  assert response.headers['etag']


def test_create_returns_an_etag_header(client, app_dir):
  response = client.post('/api/posts/create/hello-world', json=VALID_PAYLOAD)
  assert response.status_code == 201
  assert response.headers['etag']


def test_update_without_if_match_succeeds_unconditionally(client, app_dir):
  client.post('/api/posts/create/hello-world', json=VALID_PAYLOAD)
  updated = {**VALID_PAYLOAD, 'content': 'New content'}
  response = client.put('/api/posts/update/hello-world', json=updated)
  assert response.status_code == 200


def test_update_with_matching_if_match_succeeds(client, app_dir):
  client.post('/api/posts/create/hello-world', json=VALID_PAYLOAD)
  etag = client.get('/api/posts/hello-world/raw').headers['etag']
  updated = {**VALID_PAYLOAD, 'content': 'New content'}
  response = client.put(
    '/api/posts/update/hello-world',
    json=updated,
    headers={'If-Match': etag},
  )
  assert response.status_code == 200
  assert response.headers['etag'] != etag


def test_update_with_stale_if_match_is_rejected(client, app_dir):
  client.post('/api/posts/create/hello-world', json=VALID_PAYLOAD)
  stale_etag = client.get('/api/posts/hello-world/raw').headers['etag']
  # A concurrent writer moves the post on.
  client.put(
    '/api/posts/update/hello-world',
    json={**VALID_PAYLOAD, 'content': 'Someone else got here first'},
  )
  response = client.put(
    '/api/posts/update/hello-world',
    json={**VALID_PAYLOAD, 'content': 'My stale change'},
    headers={'If-Match': stale_etag},
  )
  assert response.status_code == 412


def test_delete_with_stale_if_match_is_rejected(client, app_dir):
  client.post('/api/posts/create/hello-world', json=VALID_PAYLOAD)
  stale_etag = client.get('/api/posts/hello-world/raw').headers['etag']
  client.put(
    '/api/posts/update/hello-world',
    json={**VALID_PAYLOAD, 'content': 'Changed'},
  )
  response = client.delete(
    '/api/posts/delete/hello-world', headers={'If-Match': stale_etag}
  )
  assert response.status_code == 412
  assert client.get('/api/posts/hello-world/raw').status_code == 200


def test_delete_with_matching_if_match_succeeds(client, app_dir):
  client.post('/api/posts/create/hello-world', json=VALID_PAYLOAD)
  etag = client.get('/api/posts/hello-world/raw').headers['etag']
  response = client.delete(
    '/api/posts/delete/hello-world', headers={'If-Match': etag}
  )
  assert response.status_code == 204


@pytest.fixture
def require_if_match_client(app_dir):
  app = FastAPI()
  app = add_blog_to_fastapi(app, prefix='blog')
  app = add_editor_to_app(
    app, ui=False, require_auth=False, require_if_match=True
  )
  return TestClient(app)


def test_require_if_match_rejects_update_without_the_header(
  require_if_match_client,
):
  require_if_match_client.post(
    '/api/posts/create/hello-world', json=VALID_PAYLOAD
  )
  response = require_if_match_client.put(
    '/api/posts/update/hello-world',
    json={**VALID_PAYLOAD, 'content': 'New'},
  )
  assert response.status_code == 428


def test_require_if_match_rejects_delete_without_the_header(
  require_if_match_client,
):
  require_if_match_client.post(
    '/api/posts/create/hello-world', json=VALID_PAYLOAD
  )
  response = require_if_match_client.delete('/api/posts/delete/hello-world')
  assert response.status_code == 428


def test_require_if_match_accepts_update_with_the_header(
  require_if_match_client,
):
  require_if_match_client.post(
    '/api/posts/create/hello-world', json=VALID_PAYLOAD
  )
  etag = require_if_match_client.get('/api/posts/hello-world/raw').headers[
    'etag'
  ]
  response = require_if_match_client.put(
    '/api/posts/update/hello-world',
    json={**VALID_PAYLOAD, 'content': 'New'},
    headers={'If-Match': etag},
  )
  assert response.status_code == 200


# --- on_create / read_only via the REST API (TODO 4.5) ----------------------

ID_SCHEMA = FrontmatterSchema(
  fields=(
    FieldSpec('title', required=True, role='title'),
    FieldSpec(
      'doc_id', alias='@id', type='str', on_create='uuid', read_only=True
    ),
  ),
  extra='allow',
)


@pytest.fixture
def id_client(app_dir):
  app = FastAPI()
  app = add_blog_to_fastapi(app, prefix='blog')
  app = add_editor_to_app(
    app, ui=False, require_auth=False, frontmatter_schema=ID_SCHEMA
  )
  return TestClient(app)


def test_on_create_fills_unset_field_on_create(id_client):
  response = id_client.post(
    '/api/posts/create/with-id',
    json={'frontmatter': {'title': 'Hi'}, 'content': 'Body'},
  )
  assert response.status_code == 201

  raw = id_client.get('/api/posts/with-id/raw').json()
  assert raw['frontmatter']['@id']


def test_read_only_field_is_stable_across_updates(id_client):
  create = id_client.post(
    '/api/posts/create/with-id',
    json={'frontmatter': {'title': 'Hi'}, 'content': 'Body'},
  )
  doc_id = id_client.get('/api/posts/with-id/raw').json()['frontmatter']['@id']

  # Sending back the same id (a full-replace payload naturally would) works.
  ok = id_client.put(
    '/api/posts/update/with-id',
    json={
      'frontmatter': {'title': 'Hi 2', '@id': doc_id},
      'content': 'Body 2',
    },
  )
  assert ok.status_code == 200
  assert (
    id_client.get('/api/posts/with-id/raw').json()['frontmatter']['@id']
    == doc_id
  )

  # Trying to change it is rejected.
  rejected = id_client.put(
    '/api/posts/update/with-id',
    json={
      'frontmatter': {'title': 'Hi 3', '@id': 'something-else'},
      'content': 'Body 3',
    },
  )
  assert rejected.status_code == 400
  assert 'read-only' in rejected.json()['detail']
  assert (
    id_client.get('/api/posts/with-id/raw').json()['frontmatter']['@id']
    == doc_id
  )
  assert create.status_code == 201  # sanity: the fixture create did succeed


def test_api_on_change_receives_successful_events_and_authenticated_actor(
  app_dir,
):
  events = []
  spec = CollectionSpec(
    name='posts', dir=app_dir / 'posts', on_change=events.append
  )

  async def authenticate():
    return {'username': 'api-editor'}

  app = FastAPI()
  app = add_editor_to_app(
    app,
    ui=False,
    require_auth=True,
    auth_dependency=authenticate,
    collection_spec=spec,
  )
  client = TestClient(app)

  created = client.post('/api/posts/create/event-post', json=VALID_PAYLOAD)
  assert created.status_code == 201
  updated = client.put(
    '/api/posts/update/event-post',
    json={
      **VALID_PAYLOAD,
      'frontmatter': {**VALID_PAYLOAD['frontmatter'], 'title': 'Changed'},
    },
  )
  assert updated.status_code == 200
  deleted = client.delete('/api/posts/delete/event-post')
  assert deleted.status_code == 204

  assert [event.kind for event in events] == ['created', 'updated', 'deleted']
  assert all(event.slug == 'event-post' for event in events)
  assert all(event.collection == 'posts' for event in events)
  assert events[0].etag == created.headers['etag']
  assert events[1].etag == updated.headers['etag']
  assert events[2].etag is None
  assert all(event.user == 'api-editor' for event in events)


def test_rollback_removes_created_file_when_deletes_are_disabled(app_dir):
  """A blocking validator must roll back even on a delete: false collection."""
  spec = CollectionSpec(
    name='posts',
    dir=app_dir / 'posts',
    delete=False,
    slug_template=parse_template(
      '{seq|pad(4)}-{title_slug}',
      SLUG_TAGS_DEFAULT,
      {'title', 'date', 'published', 'tags', 'description'},
    ),
    validators=(
      Validator.from_dict(
        {
          'name': 'reject',
          'argv': [sys.executable, '-c', 'import sys; sys.exit(1)'],
          'blocking': ['error'],
        }
      ),
    ),
  )
  app = FastAPI()
  app = add_editor_to_app(
    app, ui=False, require_auth=False, collection_spec=spec
  )
  client = TestClient(app)

  response = client.post(
    '/api/posts/create',
    json={
      'frontmatter': {
        'title': 'Rejected Generated',
        'date': '2026-10-31',
        'published': True,
        'tags': [],
        'description': '',
      },
      'content': 'Body',
    },
  )

  assert response.status_code == 422
  assert not (app_dir / 'posts' / '0001-rejected-generated.md').exists()


def test_create_and_delete_respect_collection_flags(app_dir):
  """create: false and delete: false refuse the operation with HTTP 403."""
  create_spec = CollectionSpec(
    name='posts', dir=app_dir / 'posts', create=False
  )
  app = FastAPI()
  app = add_editor_to_app(
    app, ui=False, require_auth=False, collection_spec=create_spec
  )
  client = TestClient(app)

  response = client.post(
    '/api/posts/save',
    json={
      'slug': 'nope',
      'frontmatter': {
        'title': 'Nope',
        'date': '2026-10-31',
        'published': True,
        'tags': [],
        'description': '',
      },
      'content': 'Body',
    },
  )
  assert response.status_code == 403
  assert not list((app_dir / 'posts').iterdir())

  delete_spec = CollectionSpec(
    name='posts', dir=app_dir / 'posts', delete=False
  )
  app2 = FastAPI()
  app2 = add_editor_to_app(
    app2, ui=False, require_auth=False, collection_spec=delete_spec
  )
  client2 = TestClient(app2)
  response = client2.post(
    '/api/posts/save',
    json={
      'slug': 'keep-me',
      'frontmatter': {
        'title': 'Keep Me',
        'date': '2026-10-31',
        'published': True,
        'tags': [],
        'description': '',
      },
      'content': 'Body',
    },
  )
  assert response.status_code == 201
  response = client2.delete('/api/posts/delete/keep-me')
  assert response.status_code == 403
  assert (app_dir / 'posts' / 'keep-me.md').exists()


def test_localized_rest_get_put_and_fallback(app_dir):
  schema = FrontmatterSchema(
    fields=(FieldSpec('title', required=True, role='title', i18n='translate'),)
  )
  spec = CollectionSpec(
    name='posts',
    dir=app_dir / 'posts',
    schema=schema,
    i18n=I18nConfig(('en', 'ru'), 'en', translate_body=True),
  )
  app = FastAPI()
  app = add_editor_to_app(
    app, ui=False, require_auth=False, collection_spec=spec
  )
  client = TestClient(app)

  created = client.put(
    '/api/posts/hello',
    json={'frontmatter': {'title': 'Hello'}, 'content': 'English body'},
  )
  assert created.status_code == 201, created.text
  assert created.json()['locales_present'] == ['en']
  assert created.json()['entry_etag']

  fallback = client.get('/api/posts/hello?locale=ru')
  assert fallback.status_code == 200
  assert fallback.json()['locale'] == 'en'
  assert fallback.json()['fallback_used'] is True
  assert fallback.json()['locales_present'] == ['en']

  translated = client.put(
    '/api/posts/hello?locale=ru',
    json={'frontmatter': {}, 'content': 'Russian body'},
  )
  assert translated.status_code == 200, translated.text
  assert translated.json()['locales_present'] == ['en', 'ru']

  russian = client.get('/api/posts/hello?locale=ru&fallback=false')
  assert russian.status_code == 200
  assert russian.json()['locale'] == 'ru'
  assert russian.json()['fallback_used'] is False
  assert russian.json()['content'] == 'Russian body'


def test_localized_create_requires_create_permission(app_dir):
  schema = FrontmatterSchema(fields=(FieldSpec('title', required=True),))
  spec = CollectionSpec(
    name='posts',
    dir=app_dir / 'posts',
    schema=schema,
    i18n=I18nConfig(('en', 'ru'), 'en'),
  )
  app = add_editor_to_app(
    FastAPI(),
    ui=False,
    require_auth=False,
    collection_spec=spec,
    authorize=lambda request, resource, action: action == 'update',
  )
  response = TestClient(app).put(
    '/api/posts/new',
    json={'frontmatter': {'title': 'Title'}, 'content': 'Body'},
  )
  assert response.status_code == 403
  assert not (app_dir / 'posts' / 'new.md').exists()


def test_localized_rest_multi_locale_put_uses_entry_etag(app_dir):
  schema = FrontmatterSchema(
    fields=(FieldSpec('title', required=True, role='title', i18n='translate'),)
  )
  spec = CollectionSpec(
    name='posts',
    dir=app_dir / 'posts',
    schema=schema,
    i18n=I18nConfig(('en', 'ru'), 'en', translate_body=True),
  )
  app = FastAPI()
  app = add_editor_to_app(
    app, ui=False, require_auth=False, collection_spec=spec
  )
  client = TestClient(app)
  created = client.put(
    '/api/posts/hello',
    json={
      'locales': {
        'en': {'frontmatter': {'title': 'Hello'}, 'content': 'English'},
        'ru': {'frontmatter': {}, 'content': 'Русский'},
      }
    },
  )
  assert created.status_code == 201, created.text
  entry_etag = created.json()['entry_etag']
  changed = client.put(
    '/api/posts/hello',
    headers={'If-Match': entry_etag},
    json={
      'locales': {
        'en': {'frontmatter': {'title': 'Hello 2'}, 'content': 'English 2'},
        'ru': {'frontmatter': {}, 'content': 'Русский 2'},
      }
    },
  )
  assert changed.status_code == 200, changed.text
  stale = client.put(
    '/api/posts/hello',
    headers={'If-Match': entry_etag},
    json={
      'locales': {
        'en': {'frontmatter': {'title': 'Stale'}, 'content': 'Stale'},
      }
    },
  )
  assert stale.status_code == 412


def test_localized_rest_duplicate_and_nontranslated_fields(app_dir):
  schema = FrontmatterSchema(
    fields=(
      FieldSpec('title', required=True, role='title', i18n='translate'),
      FieldSpec('status', i18n='duplicate'),
      FieldSpec('visibility', i18n='none'),
    )
  )
  spec = CollectionSpec(
    name='posts',
    dir=app_dir / 'posts',
    schema=schema,
    i18n=I18nConfig(('en', 'ru'), 'en', translate_body=True),
  )
  app = FastAPI()
  app = add_editor_to_app(
    app, ui=False, require_auth=False, collection_spec=spec
  )
  client = TestClient(app)
  saved = client.put(
    '/api/posts/entry',
    json={
      'locales': {
        'en': {
          'frontmatter': {
            'title': 'Original',
            'status': 'accepted',
            'visibility': 'public',
          },
          'content': 'English',
        },
        'ru': {
          'frontmatter': {
            'title': 'Перевод',
            'status': 'proposed',
            'visibility': 'private',
          },
          'content': 'Русский',
        },
      }
    },
  )
  assert saved.status_code == 201, saved.text
  assert [issue['code'] for issue in saved.json()['issues']] == [
    'translation.duplicate_mismatch'
  ]
  stored = (app_dir / 'posts' / 'entry.ru.md').read_text(encoding='utf-8')
  assert 'status:' not in stored
  assert 'visibility:' not in stored
  russian = client.get('/api/posts/entry?locale=ru')
  assert russian.json()['frontmatter'] == {
    'title': 'Перевод',
    'status': 'accepted',
    'visibility': 'public',
  }


def test_localized_rest_can_write_duplicate_mirrors(app_dir):
  schema = FrontmatterSchema(
    fields=(
      FieldSpec('title', required=True, role='title', i18n='translate'),
      FieldSpec('status', i18n='duplicate'),
    )
  )
  spec = CollectionSpec(
    name='posts',
    dir=app_dir / 'posts',
    schema=schema,
    i18n=I18nConfig(('en', 'ru'), 'en', write_duplicates=True),
  )
  app = FastAPI()
  app = add_editor_to_app(
    app, ui=False, require_auth=False, collection_spec=spec
  )
  client = TestClient(app)
  saved = client.put(
    '/api/posts/entry',
    json={
      'locales': {
        'en': {
          'frontmatter': {'title': 'Original', 'status': 'accepted'},
          'content': 'English',
        },
        'ru': {
          'frontmatter': {'title': 'Перевод', 'status': 'proposed'},
          'content': 'Russian',
        },
      }
    },
  )
  assert saved.status_code == 201, saved.text
  stored = (app_dir / 'posts' / 'entry.ru.md').read_text(encoding='utf-8')
  assert 'status: accepted' in stored
  assert [issue['code'] for issue in saved.json()['issues']] == [
    'translation.duplicate_mismatch'
  ]


def test_translation_cannot_bypass_canonical_status_transition(app_dir):
  actions = []

  def policy(user, action, collection, slug, locale, before, after):
    actions.append((action, locale))
    return action != 'publish'

  schema = FrontmatterSchema(
    fields=(
      FieldSpec('title', required=True, role='title', i18n='translate'),
      FieldSpec(
        'status',
        i18n='duplicate',
        transitions={
          'initial': ['draft'],
          'allowed': [
            {'from': 'draft', 'to': 'published', 'permission': 'publish'}
          ],
        },
      ),
    )
  )
  spec = CollectionSpec(
    'posts',
    app_dir / 'posts',
    schema=schema,
    i18n=I18nConfig(('en', 'ru'), 'en'),
    document_authorize=policy,
  )
  app = add_editor_to_app(
    FastAPI(), ui=False, require_auth=False, collection_spec=spec
  )
  client = TestClient(app)
  created = client.put(
    '/api/posts/entry',
    json={
      'frontmatter': {'title': 'Entry', 'status': 'draft'},
      'content': 'Body',
    },
  )
  assert created.status_code == 201
  actions.clear()

  translated = client.put(
    '/api/posts/entry?locale=ru',
    json={
      'frontmatter': {'title': 'Перевод', 'status': 'published'},
      'content': 'Текст',
    },
  )
  assert translated.status_code == 200
  assert ('publish', 'ru') not in actions
  russian = client.get('/api/posts/entry?locale=ru')
  assert russian.json()['frontmatter']['status'] == 'draft'
  assert (app_dir / 'posts' / 'entry.md').read_text().count(
    'status: draft'
  ) == 1


def test_localized_rest_blocking_validator_rolls_back_every_locale(app_dir):
  schema = FrontmatterSchema(
    fields=(FieldSpec('title', required=True, role='title', i18n='translate'),)
  )
  spec = CollectionSpec(
    name='posts',
    dir=app_dir / 'posts',
    schema=schema,
    i18n=I18nConfig(('en', 'ru'), 'en', translate_body=True),
    validators=(
      Validator.from_dict(
        {
          'name': 'reject-ru',
          'argv': [sys.executable, '-c', 'import sys; sys.exit(1)'],
          'blocking': ['error'],
        }
      ),
    ),
  )
  app = FastAPI()
  app = add_editor_to_app(
    app, ui=False, require_auth=False, collection_spec=spec
  )
  client = TestClient(app)
  rejected = client.put(
    '/api/posts/hello',
    json={
      'locales': {
        'en': {'frontmatter': {'title': 'Hello'}, 'content': 'English'},
        'ru': {'frontmatter': {}, 'content': 'Russian'},
      }
    },
  )
  assert rejected.status_code == 422
  assert not (app_dir / 'posts' / 'hello.md').exists()
  assert not (app_dir / 'posts' / 'hello.ru.md').exists()


def test_request_collection_roots_are_isolated_per_api_request(tmp_path):
  roots = {'one': tmp_path / 'one', 'two': tmp_path / 'two'}
  resolver_calls = []

  def resolve_root(request):
    resolver_calls.append(request.headers['x-root'])
    return roots[request.headers['x-root']]

  schema = FrontmatterSchema(
    fields=(FieldSpec('title', required=True, role='title'),)
  )
  spec = CollectionSpec(name='notes', dir=resolve_root, schema=schema)
  app = FastAPI()
  app.include_router(
    get_api_router(require_auth=False, collection_spec=spec),
    prefix='/api/notes',
  )
  client = TestClient(app)

  for root_name, title in (('one', 'First root'), ('two', 'Second root')):
    response = client.post(
      '/api/notes/create/shared',
      headers={'x-root': root_name},
      json={'frontmatter': {'title': title}, 'content': 'Body'},
    )
    assert response.status_code == 201

  first = client.get('/api/notes/shared/raw', headers={'x-root': 'one'})
  second = client.get('/api/notes/shared/raw', headers={'x-root': 'two'})
  assert first.json()['frontmatter']['title'] == 'First root'
  assert second.json()['frontmatter']['title'] == 'Second root'
  assert resolver_calls == ['one', 'two', 'one', 'two']

  updated = client.put(
    '/api/notes/update/shared',
    headers={'x-root': 'one'},
    json={'frontmatter': {'title': 'Updated first'}, 'content': 'Changed'},
  )
  assert updated.status_code == 200
  first_after = client.get('/api/notes/shared/raw', headers={'x-root': 'one'})
  second_after = client.get('/api/notes/shared/raw', headers={'x-root': 'two'})
  assert first_after.json()['frontmatter']['title'] == 'Updated first'
  assert second_after.json()['frontmatter']['title'] == 'Second root'

  deleted = client.request(
    'DELETE', '/api/notes/delete/shared', headers={'x-root': 'one'}
  )
  assert deleted.status_code == 204
  assert (
    client.get('/api/notes/shared/raw', headers={'x-root': 'one'}).status_code
    == 404
  )
  assert (
    client.get('/api/notes/shared/raw', headers={'x-root': 'two'}).status_code
    == 200
  )


def test_invalid_request_collection_root_fails_without_static_fallback(
  tmp_path,
):
  static_root = tmp_path / 'static'
  static_root.mkdir()
  (static_root / 'shared.md').write_text(
    '---\ntitle: Static fallback\n---\nBody\n', encoding='utf-8'
  )
  spec = CollectionSpec(
    name='notes',
    dir=lambda _request: pathlib.Path('relative-root'),
    schema=FrontmatterSchema(fields=(FieldSpec('title', required=True),)),
  )
  app = FastAPI()
  app.include_router(
    get_api_router(
      posts_dirname=str(static_root),
      require_auth=False,
      collection_spec=spec,
    ),
    prefix='/api/notes',
  )

  response = TestClient(app).get('/api/notes/shared/raw')

  assert response.status_code == 500
  assert 'relative-root' not in response.text
  assert 'Static fallback' not in response.text


def test_request_resolved_validator_receives_its_collection_path(
  tmp_path, monkeypatch
):
  import fastapi_blog.service as document_service

  roots = {'one': tmp_path / 'one', 'two': tmp_path / 'two'}
  validated_paths = []

  def capture_validator_path(_validators, **kwargs):
    validated_paths.append(kwargs['path'])
    return []

  monkeypatch.setattr(document_service, 'run_blocking', capture_validator_path)
  spec = CollectionSpec(
    name='notes',
    dir=lambda request: roots[request.headers['x-root']],
    schema=FrontmatterSchema(fields=(FieldSpec('title', required=True),)),
    validators=(Validator(name='capture', argv=('noop',), run='write'),),
  )
  app = FastAPI()
  app.include_router(
    get_api_router(require_auth=False, collection_spec=spec),
    prefix='/api/notes',
  )
  client = TestClient(app)

  for root_name in ('one', 'two'):
    response = client.post(
      '/api/notes/create/shared',
      headers={'x-root': root_name},
      json={'frontmatter': {'title': f'Root {root_name}'}, 'content': 'Body'},
    )
    assert response.status_code == 201

  assert validated_paths == [
    (roots['one'] / 'shared.md').resolve(),
    (roots['two'] / 'shared.md').resolve(),
  ]


def test_concurrent_writes_to_distinct_request_roots_do_not_cross_contaminate(
  tmp_path,
):
  roots = {'one': tmp_path / 'one', 'two': tmp_path / 'two'}
  spec = CollectionSpec(
    name='notes',
    dir=lambda request: roots[request.headers['x-root']],
    schema=FrontmatterSchema(fields=(FieldSpec('title', required=True),)),
  )
  app = FastAPI()
  app.include_router(
    get_api_router(require_auth=False, collection_spec=spec),
    prefix='/api/notes',
  )
  client = TestClient(app)

  def create(root_name):
    return client.post(
      '/api/notes/create/shared',
      headers={'x-root': root_name},
      json={
        'frontmatter': {'title': f'Root {root_name}'},
        'content': f'Body {root_name}',
      },
    )

  with ThreadPoolExecutor(max_workers=2) as executor:
    responses = list(executor.map(create, ('one', 'two')))

  assert [response.status_code for response in responses] == [201, 201]
  assert (
    'Root one'
    in client.get('/api/notes/shared/raw', headers={'x-root': 'one'}).text
  )
  assert (
    'Root two'
    in client.get('/api/notes/shared/raw', headers={'x-root': 'two'}).text
  )
