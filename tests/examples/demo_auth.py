"""Demo-only database-backed RBAC provider and account seeding."""

from collections.abc import Sequence
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.requests import Request
from starlette.responses import Response
from starlette_admin.auth import AdminUser, AuthProvider
from starlette_admin.exceptions import LoginFailed

from fastapi_blog.admin.models import Role, UserWithRoles
from fastapi_blog.admin.passwords import get_password_hasher
from fastapi_blog.permissions import (
  default_role_permissions,
  normalize_role_permissions,
)


DEMO_DATABASE_URL = 'sqlite+aiosqlite:///:memory:'
DEMO_ADMIN_USERNAME = 'admin'
DEMO_ADMIN_PASSWORD = 'Admin123!'
_ROLE_PRIORITY = ('admin', 'editor', 'viewer')


class DemoRBACAuthProvider(AuthProvider):
  """Authenticate demo users stored in the admin database's role tables."""

  def __init__(self, locale: str):
    """Create a provider dedicated to one localized Admin instance."""
    super().__init__()
    self.locale = locale

  async def login(
    self,
    username: str,
    password: str,
    remember_me: bool,
    request: Request,
  ) -> Response | None:
    """Verify a demo account and store its database ID in the session."""
    user = await self._get_user(request, email=username)
    if (
      user is None
      or not user.is_active
      or not get_password_hasher().verify(password, user.hashed_password)
    ):
      raise LoginFailed('Invalid username or password')

    request.session['demo_user_id'] = user.id
    return None

  async def authenticate(self, request: Request) -> AdminUser | None:
    """Load the account from the database and expose its assigned role."""
    user_id = request.session.get('demo_user_id')
    if type(user_id) is not int:
      return None
    user = await self._get_user(request, user_id=user_id)
    if user is None or not user.is_active:
      request.session.pop('demo_user_id', None)
      return None

    role = self._role_for(user.roles)
    request.state.blog_user = {
      'username': user.email,
      'role': role,
      'is_admin': role == 'admin',
      'permissions': self._permissions_for(user.roles),
    }
    return AdminUser(username=user.email)

  async def logout(self, request: Request) -> Response | None:
    """Clear the demo session."""
    request.session.pop('demo_user_id', None)
    return None

  async def _get_user(
    self,
    request: Request,
    *,
    email: str | None = None,
    user_id: int | None = None,
  ) -> UserWithRoles | None:
    engine = getattr(request.app.state, 'admin_engine', None)
    if engine is None:
      return None
    statement = select(UserWithRoles).options(selectinload(UserWithRoles.roles))
    if email is not None:
      statement = statement.where(UserWithRoles.email == email)
    else:
      statement = statement.where(UserWithRoles.id == user_id)
    async with AsyncSession(engine, expire_on_commit=False) as session:
      result = await session.execute(statement)
      return result.scalar_one_or_none()

  @staticmethod
  def _role_for(roles: Sequence[Role]) -> str | None:
    role_names = {role.name for role in roles if role.is_active}
    return next((role for role in _ROLE_PRIORITY if role in role_names), None)

  @staticmethod
  def _permissions_for(roles: Sequence[Role]) -> dict[str, list[str]]:
    grants: dict[str, set[str]] = {}
    for role in roles:
      if not role.is_active:
        continue
      try:
        role_grants = normalize_role_permissions(role.permissions)
      except ValueError:
        continue
      for resource, actions in role_grants.items():
        grants.setdefault(resource, set()).update(actions)
    return {resource: sorted(actions) for resource, actions in grants.items()}


async def seed_demo_admin(engine: Any) -> None:
  """Ensure the local demo database always contains admin / Admin123!."""
  async with AsyncSession(engine, expire_on_commit=False) as session:
    role_result = await session.execute(select(Role))
    roles = {role.name: role for role in role_result.scalars().all()}
    for role_name in _ROLE_PRIORITY:
      if role_name not in roles:
        role = Role(
          name=role_name,
          is_active=True,
          permissions=default_role_permissions(role_name),
        )
        session.add(role)
        roles[role_name] = role
    roles['admin'].is_active = True

    await session.flush()
    user_result = await session.execute(
      select(UserWithRoles)
      .options(selectinload(UserWithRoles.roles))
      .where(UserWithRoles.email == DEMO_ADMIN_USERNAME)
    )
    user = user_result.scalar_one_or_none()
    if user is None:
      user = UserWithRoles(email=DEMO_ADMIN_USERNAME)
      session.add(user)
    user.hashed_password = get_password_hasher().hash(DEMO_ADMIN_PASSWORD)
    user.is_active = True
    user.roles = [roles['admin']]
    await session.commit()


def install_demo_auth(app: Any) -> None:
  """Seed the demo account after the admin database tables are initialized."""
  engine = app.state.admin_engine
  for route in app.routes:
    mounted_app = getattr(route, 'app', None)
    if (
      mounted_app is not None
      and getattr(route, 'name', None)
      and str(route.name).startswith('admin_')
    ):
      mounted_app.state.admin_engine = engine

  original_lifespan = app.router.lifespan_context

  @asynccontextmanager
  async def demo_lifespan(application):
    async with original_lifespan(application):
      await seed_demo_admin(application.state.admin_engine)
      yield

  app.router.lifespan_context = demo_lifespan


def create_demo_auth_provider(locale: str = 'en') -> DemoRBACAuthProvider:
  """Create a fresh database-backed provider for one localized demo admin."""
  return DemoRBACAuthProvider(locale)
