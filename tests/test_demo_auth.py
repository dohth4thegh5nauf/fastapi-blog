"""Integration coverage for the database-backed demo authentication provider."""

import asyncio
import re
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.responses import Response
from starlette_admin import CustomView
from starlette_admin.routing import route

import fastapi_blog
from fastapi_blog.admin.models import UserWithRoles
from fastapi_blog.admin.passwords import get_password_hasher
from fastapi_blog.admin.views_role import UserWithRolesModelView


class DemoIdentityView(CustomView):
  def __init__(self):
    """Expose the authenticated demo principal for the test."""
    super().__init__(menu_label='Identity', path='/identity')

  @route('')
  async def index(self, request: Request) -> Response:
    user = request.state.blog_user
    return Response(f'{user["username"]}:{user["role"]}:{user["is_admin"]}')


def test_demo_provider_authenticates_the_seeded_database_user(
  monkeypatch,
):
  examples_dir = Path(__file__).parent / 'examples'
  monkeypatch.syspath_prepend(str(examples_dir))
  from demo_auth import (
    DEMO_DATABASE_URL,
    create_demo_auth_provider,
    install_demo_auth,
  )

  app = FastAPI()
  fastapi_blog.add_admin_to_app(
    app,
    database_url=DEMO_DATABASE_URL,
    auth_provider=lambda locale: create_demo_auth_provider(locale),
    secret_key='s' * 64,
    configure_admin=lambda locale, admin: admin.add_view(DemoIdentityView()),
  )
  install_demo_auth(app)

  async def exercise_authentication():
    async with app.router.lifespan_context(app):
      async with AsyncSession(app.state.admin_engine) as session:
        result = await session.execute(
          select(UserWithRoles).where(UserWithRoles.email == 'admin')
        )
        seeded_user = result.scalar_one()
        assert seeded_user.is_active
        assert get_password_hasher().verify(
          'Admin123!', seeded_user.hashed_password
        )

      async with AsyncClient(
        transport=ASGITransport(app=app), base_url='http://test'
      ) as client:
        login_page = await client.get('/admin/login')
        csrf_token = re.search(
          r'name="csrftoken" value="([^"]+)"', login_page.text
        ).group(1)
        login = await client.post(
          '/admin/login',
          data={
            'username': 'admin',
            'password': 'Admin123!',
            'csrftoken': csrf_token,
          },
        )
        assert login.status_code == 303

        identity = await client.get('/admin/identity')
        assert identity.status_code == 200
        assert identity.text == 'admin:admin:True'

        logout = await client.post(
          '/admin/logout', data={'csrftoken': csrf_token}
        )
        assert logout.status_code == 303
        protected = await client.get('/admin/identity', follow_redirects=False)
        assert protected.status_code == 303

  asyncio.run(exercise_authentication())


def test_role_user_view_hashes_passwords_and_preserves_blank_edits():
  view = UserWithRolesModelView(UserWithRoles)
  hasher = get_password_hasher()

  async def exercise_password_hooks():
    create_data = {'hashed_password': 'NewPassword123!'}
    await view.before_create(None, create_data, None)
    assert create_data['hashed_password'] != 'NewPassword123!'
    assert hasher.verify('NewPassword123!', create_data['hashed_password'])

    stored_hash = create_data['hashed_password']
    edit_data = {'hashed_password': ''}
    await view.before_edit(
      None, edit_data, type('User', (), {'hashed_password': stored_hash})()
    )
    assert 'hashed_password' not in edit_data

  asyncio.run(exercise_password_hooks())


def test_demo_permissions_union_active_roles(monkeypatch):
  monkeypatch.syspath_prepend(str(Path(__file__).parent / 'examples'))
  from demo_auth import DemoRBACAuthProvider

  roles = [
    SimpleNamespace(is_active=True, permissions={'posts': ['read']}),
    SimpleNamespace(is_active=True, permissions={'posts': ['update']}),
    SimpleNamespace(is_active=False, permissions={'posts': ['delete']}),
  ]

  assert DemoRBACAuthProvider._permissions_for(roles) == {
    'posts': ['read', 'update']
  }
