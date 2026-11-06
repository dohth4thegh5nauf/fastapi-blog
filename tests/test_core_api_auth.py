"""REST API authentication without the admin extra (phase A, 3.3)."""

import base64

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

import fastapi_blog
from fastapi_blog import ConfigurationError, helpers


PAYLOAD = {
  'frontmatter': {'title': 'Hello', 'date': '2026-04-18', 'published': True},
  'content': 'Body',
}


@pytest.fixture(autouse=True)
def workdir(tmp_path, monkeypatch):
  (tmp_path / 'posts').mkdir()
  monkeypatch.chdir(tmp_path)
  helpers.list_posts.cache_clear()
  yield tmp_path
  helpers.list_posts.cache_clear()


def _basic(user: str, password: str) -> dict[str, str]:
  token = base64.b64encode(f'{user}:{password}'.encode()).decode()
  return {'Authorization': f'Basic {token}'}


def test_basic_auth_works_without_session_middleware():
  app = FastAPI()
  fastapi_blog.add_blog_to_fastapi(
    app, include_api=True, admin_username='u', admin_password='p'
  )
  with TestClient(app) as client:
    assert client.get('/api/posts/x/raw').status_code == 401
    bad = client.get('/api/posts/x/raw', headers=_basic('u', 'nope'))
    assert bad.status_code == 401
    ok = client.post(
      '/api/posts/create/hello', json=PAYLOAD, headers=_basic('u', 'p')
    )
    assert ok.status_code == 201


def test_custom_dependency_replaces_the_builtin_checks():
  def allow(request: Request) -> dict:
    if request.headers.get('X-Token') != 'secret':
      raise HTTPException(status_code=403, detail='Forbidden')
    return {'username': 'service'}

  app = FastAPI()
  fastapi_blog.add_blog_to_fastapi(
    app, include_api=True, api_auth_dependency=allow
  )
  with TestClient(app) as client:
    assert client.get('/api/posts/x/raw').status_code == 403
    headers = {'X-Token': 'secret'}
    ok = client.post('/api/posts/create/hello', json=PAYLOAD, headers=headers)
    assert ok.status_code == 201


def test_api_without_any_auth_fails_at_startup():
  app = FastAPI()
  fastapi_blog.add_blog_to_fastapi(app, include_api=True)
  with (
    pytest.raises(ConfigurationError, match='requires authentication'),
    TestClient(app),
  ):
    pass


def test_editor_without_any_auth_fails_at_startup():
  app = FastAPI()
  fastapi_blog.add_editor_to_app(app)
  with pytest.raises(ConfigurationError), TestClient(app):
    pass


def test_startup_check_keeps_the_user_lifespan():
  events: list[str] = []
  from contextlib import asynccontextmanager

  @asynccontextmanager
  async def lifespan(app):
    events.append('start')
    yield
    events.append('stop')

  app = FastAPI(lifespan=lifespan)
  fastapi_blog.add_blog_to_fastapi(
    app, include_api=True, admin_username='u', admin_password='p'
  )
  with TestClient(app):
    assert events == ['start']
  assert events == ['start', 'stop']


@pytest.mark.parametrize(
  'options',
  [
    {'api_require_auth': False},
    {'admin_username': 'u', 'admin_password': 'p'},
    {'api_auth_dependency': lambda: None},
  ],
)
def test_configured_api_starts(options):
  app = FastAPI()
  fastapi_blog.add_blog_to_fastapi(app, include_api=True, **options)
  with TestClient(app):
    pass


def test_setup_without_admin_does_not_require_admin_authentication():
  app = FastAPI()
  assert (
    fastapi_blog.setup_fastapi_blog(app, admin=False, include_api=True) == {}
  )
  with pytest.raises(ConfigurationError), TestClient(app):
    pass


def test_setup_without_admin_accepts_credentials():
  app = FastAPI()
  fastapi_blog.setup_fastapi_blog(
    app,
    admin=False,
    include_api=True,
    admin_username='u',
    admin_password='p',
  )
  with TestClient(app) as client:
    assert (
      client.get('/api/posts/x/raw', headers=_basic('u', 'p')).status_code
      == 404
    )
