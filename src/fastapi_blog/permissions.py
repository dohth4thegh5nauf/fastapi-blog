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

KNOWN_PERMISSIONS: dict[str, tuple[str, ...]] = {
  resource: tuple(
    sorted(
      {
        action
        for role_permissions in ROLE_PERMISSIONS.values()
        for action in role_permissions.get(resource, ())
      }
    )
  )
  for resource in {
    resource
    for roles in ROLE_PERMISSIONS.values()
    for resource, actions in roles.items()
  }
}


def default_role_permissions(role: str) -> dict[str, list[str]]:
  """Return a JSON-serializable copy of the built-in role grants."""
  return {
    resource: list(actions)
    for resource, actions in ROLE_PERMISSIONS.get(role, {}).items()
  }


def normalize_role_permissions(value: Any) -> dict[str, list[str]]:
  """Validate a role's permission map and return a normalized copy."""
  if not isinstance(value, dict):
    raise ValueError('Permissions must be a JSON object.')

  normalized: dict[str, list[str]] = {}
  for resource, actions in value.items():
    if resource not in KNOWN_PERMISSIONS:
      raise ValueError(f'Unknown permission resource: {resource!r}.')
    if not isinstance(actions, list) or any(
      not isinstance(action, str) for action in actions
    ):
      raise ValueError(
        f'Permissions for {resource!r} must be a list of actions.'
      )
    invalid_actions = set(actions) - set(KNOWN_PERMISSIONS[resource])
    if invalid_actions:
      invalid = ', '.join(sorted(invalid_actions))
      raise ValueError(f'Unknown action(s) for {resource!r}: {invalid}.')
    normalized[resource] = sorted(set(actions))
  return normalized


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
  """Return a recognized role-bearing session principal, if present."""
  if 'session' not in request.scope:
    return None
  username = request.session.get('user')
  if not username:
    return None
  role = request.session.get('role')
  if role not in ROLE_PERMISSIONS:
    return None
  return {'username': username, 'role': role, 'is_admin': role == ADMIN}


def default_authorize(request: Request, resource: str, action: str) -> bool:
  """Default role policy. Missing and unrecognized roles are denied."""
  user = current_user(request)
  if user is None:
    return False
  if 'permissions' in user:
    permissions = user['permissions']
    if not isinstance(permissions, dict):
      return False
    grants = permissions.get(resource, ())
    return (
      isinstance(grants, (list, tuple, set, frozenset)) and action in grants
    )
  return role_has_permission(user.get('role'), resource, action)


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
