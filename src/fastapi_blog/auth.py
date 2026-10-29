"""Unified authentication for FastAPI Blog.

Provides a single dependency that supports both:
- Session-based auth (admin panel cookie; needs a `SessionMiddleware`)
- HTTP Basic Auth (REST API)

Basic auth and custom dependencies work without any session support.
"""

import base64
import secrets
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status


class ConfigurationError(RuntimeError):
  """Raised at startup when the blog is configured in an unsafe way."""


def has_session_middleware(app: FastAPI) -> bool:
  """Tell whether `SessionMiddleware` is added to the app.

  The class is matched by name, so this works without importing the session
  support (it needs the `admin` extra).

  Args:
      app: FastAPI application instance.

  Returns:
      `True` if a `SessionMiddleware` is registered.

  """
  return any(
    getattr(m.cls, '__name__', '') == 'SessionMiddleware'
    for m in app.user_middleware
  )


def check_api_auth_config(
  app: FastAPI,
  *,
  require_auth: bool,
  admin_username: str | None,
  admin_password: str | None,
  auth_dependency: Callable[..., Any] | None,
) -> None:
  """Fail at startup if the REST API would have no way to authenticate.

  With `require_auth=True` the API needs credentials, a custom dependency or
  a `SessionMiddleware`. Otherwise every write would be rejected (fail closed),
  and that is almost certainly a mistake, so we report it when the app starts.

  Args:
      app: FastAPI application instance.
      require_auth: Whether the API requires authentication.
      admin_username: Basic auth username (optional).
      admin_password: Basic auth password (optional).
      auth_dependency: Custom authentication dependency (optional).

  Raises:
      ConfigurationError: If no authentication method is configured.

  """
  if not require_auth or auth_dependency is not None:
    return
  if admin_username and admin_password:
    return
  if has_session_middleware(app):
    return
  raise ConfigurationError(
    'The REST API requires authentication, but none is configured. '
    'Pass `admin_username` and `admin_password`, pass an auth dependency, '
    'add a `SessionMiddleware` (extra `admin`) or set `require_auth=False`.'
  )


def add_startup_check(app: FastAPI, check: Callable[[], None]) -> None:
  """Run `check` when the app starts, composing with the existing lifespan.

  Args:
      app: FastAPI application instance.
      check: Callable that raises an exception if the configuration is bad.

  """
  original_lifespan = app.router.lifespan_context

  @asynccontextmanager
  async def lifespan(app_: Any):
    check()
    async with original_lifespan(app_) as state:
      yield state

  app.router.lifespan_context = lifespan


async def get_current_user(
  request: Request,
  *,
  admin_username: str | None = None,
  admin_password: str | None = None,
) -> str | None:
  """Get current authenticated user from session or Authorization header.

  Checks authentication in this order:
  1. Session cookie (set by admin panel)
  2. Authorization: Basic header

  Args:
      request: FastAPI request object
      admin_username: Expected username for Basic auth (optional)
      admin_password: Expected password for Basic auth (optional)

  Returns:
      Username if authenticated, None otherwise

  Example:
      ```python
      from fastapi import (
          Depends,
          FastAPI,
      )
      from fastapi_blog.auth import (
          get_current_user,
      )

      app = FastAPI()


      @app.get(
          "/protected"
      )
      async def protected(
          user: str
          | None = Depends(
              get_current_user
          ),
      ):
          if not user:
              raise HTTPException(
                  401,
                  "Authentication required",
              )
          return {
              "user": user
          }
      ```

  """
  # First, check session cookie (admin panel), if sessions are available
  if 'session' in request.scope:
    user = request.session.get('user')
    if user:
      return user

  # Second, check Authorization: Basic header (REST API)
  if admin_username and admin_password:
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Basic '):
      try:
        # Decode Basic auth
        credentials = base64.b64decode(auth_header[6:]).decode('utf-8')
        username, password = credentials.split(':', 1)

        # Verify credentials
        # Compare both values in constant time (no early exit)
        user_ok = secrets.compare_digest(
          username.encode('utf-8'), admin_username.encode('utf-8')
        )
        password_ok = secrets.compare_digest(
          password.encode('utf-8'), admin_password.encode('utf-8')
        )
        if user_ok and password_ok:
          return username
      except (ValueError, UnicodeDecodeError):
        # Invalid Basic auth format
        pass

  return None


async def require_current_user(
  request: Request,
  *,
  admin_username: str | None = None,
  admin_password: str | None = None,
) -> str:
  """Require authentication via session or Basic auth.

  Same as get_current_user() but raises 401 if not authenticated.

  Args:
      request: FastAPI request object
      admin_username: Expected username for Basic auth (optional)
      admin_password: Expected password for Basic auth (optional)

  Returns:
      Username of authenticated user

  Raises:
      HTTPException: 401 if not authenticated

  """
  user = await get_current_user(
    request, admin_username=admin_username, admin_password=admin_password
  )
  if not user:
    raise HTTPException(
      status_code=status.HTTP_401_UNAUTHORIZED,
      detail='Authentication required',
      headers={'WWW-Authenticate': 'Basic'},
    )
  return user
