"""Fail-closed admin credential and session-secret validation."""

import pytest
from fastapi import FastAPI

import fastapi_blog
from fastapi_blog import ConfigurationError


def test_admin_setup_requires_password_and_secret():
  with pytest.raises(ConfigurationError, match='no admin password'):
    fastapi_blog.add_admin_to_app(FastAPI())


@pytest.mark.parametrize(
  'secret',
  ['short', 'test-secret-key', 'change-me-in-production-please-use-strong-secret'],
)
def test_weak_secret_is_rejected(secret):
  with pytest.raises(ConfigurationError, match='session secret is weak'):
    fastapi_blog.add_admin_to_app(
      FastAPI(), admin_password='safe-test-password', secret_key=secret
    )


def test_empty_secret_is_rejected():
  with pytest.raises(ConfigurationError, match='no session secret'):
    fastapi_blog.add_admin_to_app(
      FastAPI(), admin_password='safe-test-password', secret_key=''
    )


def test_insecure_dev_explicitly_enables_development_credentials():
  with pytest.warns(UserWarning, match='insecure_dev=True'):
    fastapi_blog.add_admin_to_app(
      FastAPI(), insecure_dev=True, init_database=False
    )


def test_insecure_dev_with_supplied_values_still_warns():
  with pytest.warns(UserWarning, match='insecure_dev=True'):
    fastapi_blog.add_admin_to_app(
      FastAPI(), admin_username='test-admin',
      admin_password='safe-test-password', secret_key='a' * 64,
      insecure_dev=True, init_database=False,
    )


def test_strong_secret_and_password_are_accepted_without_warning():
  import warnings

  with warnings.catch_warnings():
    warnings.simplefilter('error')
    fastapi_blog.add_admin_to_app(
      FastAPI(), admin_username='test-admin',
      admin_password='safe-test-password', secret_key='a' * 64,
      init_database=False,
    )


def test_setup_rejects_missing_credentials_before_adding_routes(monkeypatch):
  monkeypatch.delenv('FASTAPI_BLOG_ADMIN_LOGIN', raising=False)
  monkeypatch.delenv('FASTAPI_BLOG_ADMIN_PASSWORD', raising=False)
  monkeypatch.delenv('SECRET_KEY', raising=False)
  from types import SimpleNamespace

  monkeypatch.setattr(
    fastapi_blog,
    '_import_admin',
    lambda: SimpleNamespace(add_admin_to_app=lambda *_args, **_kwargs: {}),
  )
  app = FastAPI()
  route_count = len(app.routes)
  with pytest.raises(ConfigurationError, match='no admin password'):
    fastapi_blog.setup_fastapi_blog(app)
  assert len(app.routes) == route_count
