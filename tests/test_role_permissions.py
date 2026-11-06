"""Tests for editable role grants and existing database upgrades."""

import asyncio

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from starlette.requests import Request

from fastapi_blog.admin.database import init_db
from fastapi_blog.admin.models import Role
from fastapi_blog.admin.views_role import RoleModelView
from fastapi_blog.permissions import (
  ADMIN,
  default_authorize,
  default_role_permissions,
  normalize_role_permissions,
)


def test_explicit_grants_override_static_role_defaults():
  request = Request(
    {
      'type': 'http',
      'method': 'GET',
      'path': '/',
      'headers': [],
      'state': {
        'blog_user': {
          'role': ADMIN,
          'permissions': {'posts': ['read']},
        }
      },
    }
  )

  assert default_authorize(request, 'posts', 'read') is True
  assert default_authorize(request, 'posts', 'delete') is False


def test_role_permission_map_rejects_unknown_resources_and_actions():
  with pytest.raises(ValueError, match='Unknown permission resource'):
    normalize_role_permissions({'secrets': ['read']})
  with pytest.raises(ValueError, match='Unknown action'):
    normalize_role_permissions({'posts': ['execute']})
  assert normalize_role_permissions({'posts': ['read', 'read']}) == {
    'posts': ['read']
  }


def test_role_view_validates_grants_before_saving():
  view = RoleModelView(Role)

  async def validate():
    valid_data = {'permissions': {'posts': ['read']}}
    await view.before_create(None, valid_data, None)
    assert valid_data['permissions'] == {'posts': ['read']}

    with pytest.raises(ValueError, match='Unknown action'):
      await view.before_create(
        None, {'permissions': {'posts': ['execute']}}, None
      )

  asyncio.run(validate())


def test_role_permissions_field_is_localized_per_admin_instance():
  english = RoleModelView(Role, locale='en')
  russian = RoleModelView(Role, locale='ru')

  english_field = next(
    field for field in english.fields if field.name == 'permissions'
  )
  russian_field = next(
    field for field in russian.fields if field.name == 'permissions'
  )
  assert english_field.label == 'Permissions'
  assert russian_field.label == 'Разрешения'


def test_init_db_migrates_existing_role_table_and_preserves_default_grants():
  engine = create_async_engine('sqlite+aiosqlite:///:memory:')

  async def migrate():
    async with engine.begin() as connection:
      await connection.execute(
        text(
          """CREATE TABLE roles (
            id INTEGER PRIMARY KEY,
            name VARCHAR(50) NOT NULL UNIQUE,
            description VARCHAR(500),
            is_active BOOLEAN NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME
          )"""
        )
      )
      await connection.execute(
        text(
          'INSERT INTO roles (id, name, is_active, created_at) '
          "VALUES (1, 'editor', 1, CURRENT_TIMESTAMP)"
        )
      )

    await init_db(engine)
    async with AsyncSession(engine) as session:
      result = await session.execute(select(Role).where(Role.name == 'editor'))
      role = result.scalar_one()
      assert role.permissions == default_role_permissions('editor')
      assert role.is_active is True
    await engine.dispose()

  asyncio.run(migrate())
