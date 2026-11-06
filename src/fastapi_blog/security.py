"""Session-secret validation and cookie-authenticated write protection."""

import os
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlsplit

from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .auth import ConfigurationError


MIN_SECRET_LENGTH = 32
WEAK_SECRETS = frozenset(
  {
    '',
    'change-me-in-production-please-use-strong-secret',
    'changeme',
    'change-me',
    'secret',
    'test-secret-key',
    'password',
    'development',
  }
)
_GENERATE_HINT = "python -c 'import secrets; print(secrets.token_hex(32))'"


def is_weak_secret(secret: str) -> bool:
  """Return whether a session secret is a known placeholder or too short."""
  return secret in WEAK_SECRETS or len(secret) < MIN_SECRET_LENGTH


def resolve_session_secret(secret_key: str | None) -> str:
  """Resolve and validate the session secret without requiring login credentials."""
  secret_key = secret_key or os.getenv('SECRET_KEY')
  if not secret_key:
    raise ConfigurationError(
      'No session secret (pass secret_key or set SECRET_KEY; generate one '
      f'with {_GENERATE_HINT})'
    )
  if is_weak_secret(secret_key):
    raise ConfigurationError(
      f'The session secret is weak (minimum {MIN_SECRET_LENGTH} characters; '
      f'generate one with {_GENERATE_HINT})'
    )
  return secret_key


_UNSAFE_METHODS = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})


def install_origin_check_middleware(app: Any, prefixes: Sequence[str]) -> None:
  """Install one Origin guard and merge prefixes on repeated setup calls."""
  requested = tuple(dict.fromkeys(prefixes))
  for middleware in app.user_middleware:
    if middleware.cls is OriginCheckMiddleware:
      options = getattr(middleware, 'kwargs', None)
      if options is None:
        options = {}
        middleware.kwargs = options
      current = tuple(options.get('prefixes', ('/',)))
      options['prefixes'] = tuple(dict.fromkeys((*current, *requested)))
      return
  app.add_middleware(OriginCheckMiddleware, prefixes=requested)


class OriginCheckMiddleware:
  """Reject cross-origin writes carrying a session cookie.

  Starlette-admin protects its own forms with CSRF tokens. This middleware
  additionally protects cookie-authenticated REST endpoints. Requests using
  Basic auth or non-browser clients without cookies are not affected.
  """

  def __init__(self, app: ASGIApp, prefixes: Sequence[str] = ('/',)) -> None:
    """Store the wrapped app and the path prefixes to protect."""
    self.app = app
    self.prefixes = tuple(prefixes)

  async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
    if scope['type'] == 'http' and self._rejected(scope):
      await PlainTextResponse('Cross-origin request rejected', 403)(
        scope, receive, send
      )
      return
    await self.app(scope, receive, send)

  def _rejected(self, scope: Scope) -> bool:
    if scope['method'].upper() not in _UNSAFE_METHODS:
      return False
    if not any(
      self._matches_prefix(scope['path'], prefix) for prefix in self.prefixes
    ):
      return False

    header_values: dict[str, list[str]] = {}
    for key, value in scope['headers']:
      name = key.decode('latin-1').lower()
      header_values.setdefault(name, []).append(value.decode('latin-1'))
    if 'cookie' not in header_values:
      return False

    origins = header_values.get('origin', [])
    hosts = header_values.get('host', [])
    if len(origins) != 1 or len(hosts) != 1:
      return True
    try:
      parsed = urlsplit(origins[0])
      if (
        parsed.scheme not in ('http', 'https')
        or not parsed.netloc
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
      ):
        return True
      return (
        parsed.scheme.lower() != str(scope.get('scheme', '')).lower()
        or parsed.netloc.lower() != hosts[0].lower()
      )
    except ValueError:
      return True

  @staticmethod
  def _matches_prefix(path: str, prefix: str) -> bool:
    """Match a path prefix on a route boundary; `/` means every path."""
    normalized = prefix.rstrip('/') or '/'
    return (
      normalized == '/'
      or path == normalized
      or path.startswith(normalized + '/')
    )
