"""Tests for the draft-inadarei-api-health-check-06 probes (see health.py)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

import fastapi_blog


def _client(tmp_path, monkeypatch) -> TestClient:
  monkeypatch.chdir(tmp_path)
  app = FastAPI()
  fastapi_blog.add_blog_to_fastapi(
    app,
    posts_dirname=str(tmp_path / 'posts'),
    pages_dirname=str(tmp_path / 'pages'),
  )
  return TestClient(app)


def test_all_three_probes_exist_and_pass(tmp_path, monkeypatch):
  client = _client(tmp_path, monkeypatch)

  for path in ('/api/v1/health', '/api/v1/health/live', '/api/v1/health/ready'):
    response = client.get(path)
    assert response.status_code == 200, path
    assert response.headers['content-type'].startswith(
      'application/health+json'
    )
    assert 'max-age=' in response.headers['cache-control']
    body = response.json()
    assert body['status'] in ('pass', 'warn')


def test_live_probe_is_minimal_and_touches_nothing(tmp_path, monkeypatch):
  client = _client(tmp_path, monkeypatch)

  response = client.get('/api/v1/health/live')

  assert response.status_code == 200
  assert response.json() == {'status': 'pass'}


def test_ready_probe_is_minimal(tmp_path, monkeypatch):
  client = _client(tmp_path, monkeypatch)

  response = client.get('/api/v1/health/ready')

  assert response.status_code == 200
  assert response.json() == {'status': 'pass'}


def test_base_probe_reports_version_and_uptime_check(tmp_path, monkeypatch):
  client = _client(tmp_path, monkeypatch)

  response = client.get('/api/v1/health')
  body = response.json()

  assert response.status_code == 200
  assert body['status'] == 'pass'
  assert body['version']
  # checks is an object of "component:measurement" -> [observations].
  uptime = body['checks']['uptime']
  assert isinstance(uptime, list) and len(uptime) == 1
  assert uptime[0]['componentType'] == 'system'
  assert uptime[0]['observedUnit'] == 's'
  assert uptime[0]['status'] == 'pass'
  assert 'time' in uptime[0]


def test_unreadable_content_directory_fails_ready_and_base(
  tmp_path, monkeypatch
):
  client = _client(tmp_path, monkeypatch)
  posts = tmp_path / 'posts'
  posts.mkdir()
  monkeypatch.setattr('fastapi_blog.health.os.access', lambda *a: False)

  ready = client.get('/api/v1/health/ready')
  assert ready.status_code == 503
  assert ready.json()['status'] == 'fail'

  base = client.get('/api/v1/health')
  assert base.status_code == 503
  assert base.json()['status'] == 'fail'
  assert base.json()['output']
  check = base.json()['checks']['content:readability'][0]
  assert check['status'] == 'fail'

  # Liveness must not be affected by a dependency failure.
  assert client.get('/api/v1/health/live').status_code == 200


def test_health_routes_are_enabled_by_default_and_documented(
  tmp_path, monkeypatch
):
  client = _client(tmp_path, monkeypatch)
  app = client.app
  schema = app.openapi()

  expected_paths = (
    '/api/v1/health',
    '/api/v1/health/live',
    '/api/v1/health/ready',
  )
  for path in expected_paths:
    assert path in schema['paths']
    operation = schema['paths'][path]['get']
    assert 'health' in operation['tags']
    success = operation['responses']['200']
    assert 'application/health+json' in success['content']
    assert 'application/json' not in success['content']

  assert '503' in schema['paths']['/api/v1/health']['get']['responses']
  assert '503' not in schema['paths']['/api/v1/health/live']['get']['responses']
  assert '503' in schema['paths']['/api/v1/health/ready']['get']['responses']

  docs = client.get('/docs')
  assert docs.status_code == 200
  assert '/openapi.json' in docs.text


def test_health_routes_can_be_disabled_explicitly(tmp_path, monkeypatch):
  monkeypatch.chdir(tmp_path)
  app = FastAPI()
  fastapi_blog.add_blog_to_fastapi(app, health_routes=False)

  client = TestClient(app)
  assert client.get('/api/v1/health').status_code == 404
  assert not any(
    path.startswith('/api/v1/health') for path in app.openapi()['paths']
  )


def test_setup_fastapi_blog_enables_health_routes_by_default(
  tmp_path, monkeypatch
):
  monkeypatch.chdir(tmp_path)
  app = FastAPI()
  fastapi_blog.setup_fastapi_blog(
    app,
    posts_dirname=str(tmp_path / 'posts'),
    admin=False,
  )

  response = TestClient(app).get('/api/v1/health/live')
  assert response.status_code == 200
  assert response.json() == {'status': 'pass'}
