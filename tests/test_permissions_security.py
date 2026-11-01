"""Shared role policy and cookie-origin protection (phase E)."""

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

import fastapi_blog
from fastapi_blog.permissions import ADMIN, EDITOR, VIEWER, role_has_permission
from fastapi_blog.security import OriginCheckMiddleware


def test_default_role_permissions_are_explicit_and_fail_closed():
  assert role_has_permission(ADMIN, 'posts', 'delete') is True
  assert role_has_permission(EDITOR, 'posts', 'create') is True
  assert role_has_permission(EDITOR, 'posts', 'delete') is False
  assert role_has_permission(VIEWER, 'posts', 'read') is True
  assert role_has_permission(VIEWER, 'posts', 'update') is False
  assert role_has_permission(None, 'posts', 'read') is False
  assert role_has_permission('unknown', 'posts', 'read') is False
  assert role_has_permission(ADMIN, 'unknown', 'read') is False


def _scope(method, path, headers):
  return {
    'type': 'http',
    'scheme': 'https',
    'method': method,
    'path': path,
    'headers': [
      (key.lower().encode(), value.encode()) for key, value in headers.items()
    ],
  }


def test_origin_check_rejects_cross_site_cookie_writes_and_missing_origin():
  middleware = OriginCheckMiddleware(lambda *_: None, prefixes=('/api',))
  assert (
    middleware._rejected(
      _scope(
        'POST',
        '/api/posts/save',
        {
          'cookie': 'session=abc',
          'host': 'example.org',
          'origin': 'https://attacker.example',
        },
      )
    )
    is True
  )
  assert (
    middleware._rejected(
      _scope(
        'POST',
        '/api/posts/save',
        {
          'cookie': 'session=abc',
          'host': 'example.org',
        },
      )
    )
    is True
  )


def test_origin_check_allows_same_origin_and_non_cookie_requests():
  middleware = OriginCheckMiddleware(lambda *_: None, prefixes=('/api',))
  assert (
    middleware._rejected(
      _scope(
        'POST',
        '/api/posts/save',
        {
          'cookie': 'session=abc',
          'host': 'example.org',
          'origin': 'https://example.org',
        },
      )
    )
    is False
  )
  assert (
    middleware._rejected(
      _scope(
        'POST',
        '/api/posts/save',
        {
          'authorization': 'Basic dTpw',
          'host': 'example.org',
        },
      )
    )
    is False
  )
  assert (
    middleware._rejected(
      _scope(
        'GET',
        '/api/posts/save',
        {
          'cookie': 'session=abc',
          'host': 'example.org',
        },
      )
    )
    is False
  )
  assert (
    middleware._rejected(
      _scope(
        'POST',
        '/outside',
        {
          'cookie': 'session=abc',
          'host': 'example.org',
          'origin': 'https://attacker.example',
        },
      )
    )
    is False
  )


def test_origin_check_rejects_wrong_scheme_and_ambiguous_headers():
  middleware = OriginCheckMiddleware(lambda *_: None, prefixes=('/api',))
  wrong_scheme = _scope(
    'POST',
    '/api/posts/save',
    {
      'cookie': 'session=abc',
      'host': 'example.org',
      'origin': 'http://example.org',
    },
  )
  assert middleware._rejected(wrong_scheme) is True

  duplicate = _scope(
    'POST',
    '/api/posts/save',
    {
      'cookie': 'session=abc',
      'host': 'example.org',
      'origin': 'https://example.org',
    },
  )
  duplicate['headers'].append((b'origin', b'https://attacker.example'))
  assert middleware._rejected(duplicate) is True


def test_root_prefix_matches_all_unsafe_paths():
  middleware = OriginCheckMiddleware(lambda *_: None)
  assert (
    middleware._rejected(
      _scope(
        'POST',
        '/anything',
        {
          'cookie': 'session=abc',
          'host': 'example.org',
          'origin': 'https://attacker.example',
        },
      )
    )
    is True
  )


def test_viewer_and_editor_permissions_are_enforced_by_the_rest_api(tmp_path):
  app = FastAPI()
  app.add_middleware(SessionMiddleware, secret_key='v' * 64, same_site='lax')

  @app.get('/test-session/{role}')
  async def set_session(role: str, request: Request):
    request.session.update({'user': role, 'role': role})
    return {'role': role}

  fastapi_blog.add_blog_to_fastapi(
    app,
    posts_dirname=str(tmp_path),
    include_api=True,
    admin_username='admin',
    admin_password='admin-password',
  )
  headers = {'Origin': 'http://testserver'}
  payload = {
    'frontmatter': {
      'title': 'Role protected',
      'date': '2026-10-31',
      'published': True,
      'tags': [],
      'description': '',
    },
    'content': 'Body',
  }

  with TestClient(app) as client:
    client.get('/test-session/viewer')
    denied = client.post(
      '/api/posts/create/viewer-post', json=payload, headers=headers
    )
    assert denied.status_code == 403

    client.get('/test-session/editor')
    created = client.post(
      '/api/posts/create/editor-post', json=payload, headers=headers
    )
    assert created.status_code == 201
    deleted = client.delete('/api/posts/delete/editor-post', headers=headers)
    assert deleted.status_code == 403


def test_legacy_editor_api_also_checks_cookie_origin_and_roles(tmp_path):
  from fastapi_blog import add_editor_to_app

  app = FastAPI()
  app.add_middleware(SessionMiddleware, secret_key='e' * 64, same_site='lax')

  @app.get('/test-session/{role}')
  async def set_session(role: str, request: Request):
    request.session.update({'user': role, 'role': role})
    return {'role': role}

  add_editor_to_app(
    app,
    prefix='/legacy-api',
    posts_dirname=str(tmp_path),
    ui=False,
  )
  payload = {
    'frontmatter': {
      'title': 'Legacy API role protected',
      'date': '2026-10-31',
      'published': True,
      'tags': [],
      'description': '',
    },
    'content': 'Body',
  }

  with TestClient(app) as client:
    client.get('/test-session/editor')
    without_origin = client.post('/legacy-api/create/editor-post', json=payload)
    assert without_origin.status_code == 403

    created = client.post(
      '/legacy-api/create/editor-post',
      json=payload,
      headers={'Origin': 'http://testserver'},
    )
    assert created.status_code == 201

    client.get('/test-session/viewer')
    denied = client.post(
      '/legacy-api/create/viewer-post',
      json=payload,
      headers={'Origin': 'http://testserver'},
    )
    assert denied.status_code == 403
