"""Admin initialization must not emit authentication material in logs."""

import logging

from fastapi import FastAPI

import fastapi_blog

from tests.auth_helpers import DemoTestAuthProvider


def test_admin_setup_does_not_log_authentication_material(caplog):
  app = FastAPI()

  with caplog.at_level(logging.DEBUG, logger='fastapi_blog.admin'):
    fastapi_blog.add_admin_to_app(
      app,
      secret_key='t' * 64,
      database_url='sqlite+aiosqlite:///:memory:',
      locales=['en'],
      default_locale='en',
      auth_provider=lambda locale: DemoTestAuthProvider(),
    )

  assert 'password=' not in caplog.text.lower()
  assert 'secret_key=' not in caplog.text.lower()
  assert 't' * 64 not in caplog.text
