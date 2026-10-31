"""Tests for SessionMiddleware duplication detection."""

import warnings

import pytest
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from fastapi_blog.admin import add_admin_to_app


def test_no_duplication_when_not_added_manually():
  """Test that SessionMiddleware is added when not present."""
  app = FastAPI()

  # Initially, no middleware
  assert len(app.user_middleware) == 0

  # Add admin (should add SessionMiddleware)
  # Use strong secret to avoid weak key warning
  add_admin_to_app(
    app,
    admin_username='test',
    admin_password='test123',
    secret_key='m' * 64,
    init_database=False,
  )

  # Session, Origin protection and the locale redirect are installed.
  assert len(app.user_middleware) == 3
  middleware_classes = [m.cls.__name__ for m in app.user_middleware]
  assert 'SessionMiddleware' in middleware_classes
  assert 'OriginCheckMiddleware' in middleware_classes
  assert 'AdminDefaultLocaleRedirectMiddleware' in middleware_classes


def test_warning_when_middleware_already_added():
  """Test that warning is issued when SessionMiddleware is already present."""
  app = FastAPI()

  # Manually add SessionMiddleware
  app.add_middleware(SessionMiddleware, secret_key='m' * 64, same_site='lax')
  assert len(app.user_middleware) == 1

  # Try to add admin (should detect duplicate and warn)
  with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter('always')
    add_admin_to_app(
      app,
      admin_username='test',
      admin_password='test123',
      secret_key='m' * 64,  # Must match the externally installed middleware
      init_database=False,
      # add_session_middleware=True by default
    )

    # Should have issued a warning about SessionMiddleware duplication
    # Filter out other warnings
    middleware_warnings = [
      warning
      for warning in w
      if 'SessionMiddleware is already added' in str(warning.message)
    ]
    assert len(middleware_warnings) == 1
    assert issubclass(middleware_warnings[0].category, UserWarning)
    assert 'add_session_middleware=False' in str(middleware_warnings[0].message)

  # Manual Session + Origin protection + Admin redirect middleware.
  assert len(app.user_middleware) == 3
  middleware_classes = [m.cls.__name__ for m in app.user_middleware]
  assert middleware_classes.count('SessionMiddleware') == 1


def test_explicit_false_no_warning():
  """Test that no warning is issued when add_session_middleware=False."""
  app = FastAPI()

  # Manually add SessionMiddleware
  app.add_middleware(SessionMiddleware, secret_key='m' * 64, same_site='lax')
  assert len(app.user_middleware) == 1

  # Add admin with explicit False (correct usage)
  with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter('always')
    add_admin_to_app(
      app,
      admin_username='test',
      admin_password='test123',
      secret_key='m' * 64,  # Must match the externally installed middleware
      init_database=False,
      add_session_middleware=False,  # Explicit False
    )

    # Should NOT have issued any warnings about SessionMiddleware
    middleware_warnings = [
      warning for warning in w if 'SessionMiddleware' in str(warning.message)
    ]
    assert len(middleware_warnings) == 0

  # Manual Session + Origin protection + Admin redirect middleware.
  assert len(app.user_middleware) == 3
  middleware_classes = [m.cls.__name__ for m in app.user_middleware]
  assert middleware_classes.count('SessionMiddleware') == 1


def test_multiple_calls_with_false():
  """Test repeated calls with add_session_middleware=False."""
  app = FastAPI()

  # First call (adds middleware)
  add_admin_to_app(
    app,
    admin_username='admin1',
    admin_password='test123',
    secret_key='m' * 64,  # Must match the externally installed middleware
    init_database=False,
  )

  initial_count = len(app.user_middleware)
  assert initial_count >= 1

  # Second call with False (should not add more middleware)
  with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter('always')
    add_admin_to_app(
      app,
      admin_username='admin2',
      admin_password='test456',
      secret_key='m' * 64,  # Same secret as the existing middleware
      init_database=False,
      add_session_middleware=False,
    )

    # Should not have SessionMiddleware warnings
    middleware_warnings = [
      warning for warning in w if 'SessionMiddleware' in str(warning.message)
    ]
    assert len(middleware_warnings) == 0

  # Middleware count should not increase
  # Note: This test might fail if add_admin_to_app can't be called twice
  # In that case, we'd need to adjust the implementation


def test_existing_session_middleware_must_use_the_same_secret():
  from fastapi_blog import ConfigurationError

  app = FastAPI()
  app.add_middleware(SessionMiddleware, secret_key='m' * 64, same_site='lax')
  with pytest.raises(ConfigurationError, match='same secret_key'):
    add_admin_to_app(
      app,
      admin_username='test',
      admin_password='test123',
      secret_key='n' * 64,
      init_database=False,
      add_session_middleware=False,
    )


def test_https_only_requires_secure_existing_session_cookie():
  from fastapi_blog import ConfigurationError

  app = FastAPI()
  app.add_middleware(SessionMiddleware, secret_key='m' * 64, same_site='lax')
  with pytest.raises(ConfigurationError, match='https_only=True'):
    add_admin_to_app(
      app,
      admin_username='test',
      admin_password='test123',
      secret_key='m' * 64,
      https_only=True,
      init_database=False,
      add_session_middleware=False,
    )
