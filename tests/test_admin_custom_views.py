"""Public extension hooks for localized Starlette Admin panels."""

import asyncio
import re

from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette_admin import CustomView
from starlette_admin.routing import route

import fastapi_blog
from fastapi_blog.config import CollectionSpec
from fastapi_blog.models import FieldSpec, FrontmatterSchema
from fastapi_blog.store import write_document


class DecisionsView(CustomView):
  def __init__(self, locale: str):
    """Create a route that identifies the localized admin instance."""
    super().__init__(
      menu_label='Decisions',
      path='/decisions',
      route_name=f'decisions_{locale}',
    )
    self.locale = locale

  @route('')
  async def index(self, request: Request) -> PlainTextResponse:
    return PlainTextResponse(f'Decisions ({self.locale})')


def test_configure_admin_adds_view_to_every_locale_before_mount():
  app = FastAPI()
  configured = []

  def configure_admin(locale: str, admin) -> None:
    configured.append(locale)
    admin.add_view(DecisionsView(locale))

  fastapi_blog.add_admin_to_app(
    app,
    admin_username='admin',
    admin_password='Secret123!',
    secret_key='s' * 64,
    database_url='sqlite+aiosqlite:///:memory:',
    locales=['en', 'ru'],
    default_locale='en',
    configure_admin=configure_admin,
  )

  assert configured == ['en', 'ru']

  async def assert_custom_views_are_reachable():
    try:
      async with AsyncClient(
        transport=ASGITransport(app=app), base_url='http://test'
      ) as client:
        login_page = await client.get('/admin/login')
        token = re.search(
          r'name="csrftoken" value="([^"]+)"', login_page.text
        ).group(1)
        login = await client.post(
          '/admin/login',
          data={
            'username': 'admin',
            'password': 'Secret123!',
            'csrftoken': token,
          },
        )

        assert login.status_code == 303
        english = await client.get('/admin/decisions')
        russian = await client.get('/ru/admin/decisions')

        assert english.status_code == 200
        assert english.text == 'Decisions (en)'
        assert russian.status_code == 200
        assert russian.text == 'Decisions (ru)'
    finally:
      await app.state.admin_engine.dispose()

  asyncio.run(assert_custom_views_are_reachable())


def test_admin_uses_request_resolved_collection_root(tmp_path):
  roots = {'one': tmp_path / 'one', 'two': tmp_path / 'two'}
  for root, title in (
    (roots['one'], 'First root'),
    (roots['two'], 'Second root'),
  ):
    root.mkdir()
    write_document(
      root / 'shared.md', {'title': title, 'published': True}, 'Body'
    )
  spec = CollectionSpec(
    name='posts',
    dir=lambda request: roots[request.headers['x-root']],
    schema=FrontmatterSchema(
      fields=(
        FieldSpec('title', required=True, role='title'),
        FieldSpec('published', type='bool', role='published'),
      )
    ),
  )
  app = FastAPI()
  fastapi_blog.add_admin_to_app(
    app,
    admin_username='admin',
    admin_password='Secret123!',
    secret_key='s' * 64,
    database_url='sqlite+aiosqlite:///:memory:',
    locales=['en'],
    default_locale='en',
    collection_spec=spec,
  )

  async def assert_roots_are_isolated():
    try:
      async with AsyncClient(
        transport=ASGITransport(app=app), base_url='http://test'
      ) as client:
        login_page = await client.get('/admin/login')
        token = re.search(
          r'name="csrftoken" value="([^"]+)"', login_page.text
        ).group(1)
        login = await client.post(
          '/admin/login',
          data={
            'username': 'admin',
            'password': 'Secret123!',
            'csrftoken': token,
          },
        )
        assert login.status_code == 303
        first = await client.get('/admin/posts', headers={'x-root': 'one'})
        second = await client.get('/admin/posts', headers={'x-root': 'two'})
        assert 'First root' in first.text
        assert 'Second root' not in first.text
        assert 'Second root' in second.text
        assert 'First root' not in second.text
        dashboard_one = await client.get('/admin/', headers={'x-root': 'one'})
        dashboard_two = await client.get('/admin/', headers={'x-root': 'two'})
        assert 'First root' in dashboard_one.text
        assert 'Second root' not in dashboard_one.text
        assert 'Second root' in dashboard_two.text
        assert 'First root' not in dashboard_two.text
    finally:
      await app.state.admin_engine.dispose()

  asyncio.run(assert_roots_are_isolated())
