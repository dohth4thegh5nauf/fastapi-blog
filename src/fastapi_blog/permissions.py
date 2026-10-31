"""Shared authorization policy for the REST API and the admin panel.

The default policy denies unknown users, resources, roles and actions. Supply
an ``authorize(request, resource, action)`` callable to replace it.
"""

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import HTTPException, Request, status


ADMIN = 'admin'
EDITOR = 'editor'
VIEWER = 'viewer'

ROLE_PERMISSIONS: dict[str, dict[str, tuple[str, ...]]] = {
  ADMIN: {
    'posts': ('create', 'read', 'update', 'delete', 'publish'),
    'users': ('create', 'read', 'update', 'delete'),
    'settings': ('read', 'update'),
    'role': ('create', 'read', 'update', 'delete'),
    'user_with_roles': ('create', 'read', 'update', 'delete'),
  },
  EDITOR: {
    'posts': ('create', 'read', 'update', 'publish'),
    'users': ('read',),
    'settings': ('read',),
  },
  VIEWER: {'posts': ('read',), 'users': (), 'settings': ()},
}

Authorizer = Callable[[Request, str, str], bool | Awaitable[bool]]


def role_has_permission(role: str | None, resource: str, action: str) -> bool:
  """Return whether a known role grants the requested action."""
  if role not in ROLE_PERMISSIONS:
    return False
  return action in ROLE_PERMISSIONS[role].get(resource, ())


def current_user(request: Request) -> dict[str, Any] | None:
  """Return the principal attached to the current request."""
  return getattr(request.state, 'blog_user', None)


def user_from_session(request: Request) -> dict[str, Any] | None:
  """Normalize a session user; legacy admin sessions retain admin access."""
  if 'session' not in request.scope:
    return None
  username = request.session.get('user')
  if not username:
    return None
  role = request.session.get('role')
  if role is None and request.session.get('is_admin'):
    role = ADMIN
  return {'username': username, 'role': role, 'is_admin': role == ADMIN}


def default_authorize(request: Request, resource: str, action: str) -> bool:
  """Default role policy. Missing and unrecognized roles are denied."""
  user = current_user(request)
  return bool(user) and role_has_permission(user.get('role'), resource, action)


async def ensure_allowed(
  authorize: Authorizer, request: Request, resource: str, action: str
) -> None:
  """Raise HTTP 403 unless the configured authorizer allows the operation."""
  result = authorize(request, resource, action)
  if inspect.isawaitable(result):
    result = await result
  if not result:
    raise HTTPException(
      status_code=status.HTTP_403_FORBIDDEN,
      detail=f'Not allowed: {action} {resource}',
    )
