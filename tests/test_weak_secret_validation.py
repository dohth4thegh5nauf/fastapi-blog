"""Fail-closed validation for external admin authentication configuration."""

import pytest
from fastapi import FastAPI

import fastapi_blog
from fastapi_blog import ConfigurationError

from tests.auth_helpers import DemoTestAuthProvider


@pytest.mark.parametrize(
  'secret',
  [
    'short',
    'test-secret-key',
    'change-me-in-production-please-use-strong-secret',
  ],
)
def test_weak_secret_is_rejected(secret):
  with pytest.raises(ConfigurationError, match='session secret is weak'):
    fastapi_blog.add_admin_to_app(
      FastAPI(), auth_provider=lambda locale: DemoTestAuthProvider(), secret_key=secret
    )


def test_empty_secret_is_rejected():
  with pytest.raises(ConfigurationError, match='No session secret'):
    fastapi_blog.add_admin_to_app(
      FastAPI(), auth_provider=lambda locale: DemoTestAuthProvider(), secret_key=''
    )


def test_admin_setup_requires_external_provider():
  app = FastAPI()
  with pytest.raises(ConfigurationError, match='requires a host-supplied auth_provider'):
    fastapi_blog.setup_fastapi_blog(app, secret_key='s' * 64)
  assert len(app.routes) == 4


def test_setup_rejects_missing_provider_before_adding_routes(monkeypatch):
  from types import SimpleNamespace

  monkeypatch.setattr(
    fastapi_blog,
    '_import_admin',
    lambda: SimpleNamespace(add_admin_to_app=lambda *_args, **_kwargs: {}),
  )
  app = FastAPI()
  route_count = len(app.routes)
  with pytest.raises(ConfigurationError, match='requires a host-supplied auth_provider'):
    fastapi_blog.setup_fastapi_blog(app)
  assert len(app.routes) == route_count
