"""External Starlette Admin authentication provider integration tests."""

import asyncio
import re
import secrets
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx2 import ASGITransport, AsyncClient
from starlette.requests import Request
from starlette.responses import Response
from starlette_admin import CustomView
from starlette_admin.auth import AdminUser, AuthProvider
from starlette_admin.exceptions import LoginFailed
from starlette_admin.routing import route

import fastapi_blog
from fastapi_blog.auth import ConfigurationError


class FakeHostAuthProvider(AuthProvider):
  def __init__(self, locale: str):
    """Create a host provider with locale-specific identity state."""
    super().__init__()
    self.locale = locale
    self.authenticate_calls = 0
    self.logout_calls = 0

  async def login(
    self,
    username: str,
    password: str,
    remember_me: bool,
    request: Request,
  ) -> Response | None:
    if not (
      secrets.compare_digest(username, 'host-user')
      and secrets.compare_digest(password, 'host-password')
    ):
      raise LoginFailed('Invalid username or password')
    request.session['host_user'] = username
    return None

  async def authenticate(self, request: Request) -> AdminUser | None:
    self.authenticate_calls += 1
    username = request.session.get('host_user')
    if username is None:
      return None
    request.state.blog_user = {'username': username, 'locale': self.locale}
    return AdminUser(username=username)

  async def logout(self, request: Request) -> Response | None:
    self.logout_calls += 1
    request.session.clear()
    return None


class IncompleteAuthProvider(AuthProvider):
  """Provider stub used to check construction-time interface validation."""


class InvalidSignatureAuthProvider(AuthProvider):
  """Provider with an incompatible login signature."""

  async def login(self, request: Request) -> Response | None:
    return None

  async def authenticate(self, request: Request) -> AdminUser | None:
    return None

  async def logout(self, request: Request) -> Response | None:
    return None


class IdentityView(CustomView):
  def __init__(self, locale: str):
    """Create a test view that exposes the host user identity."""
    super().__init__(menu_label='Identity', path='/identity')
    self.locale = locale

  @route('')
  async def index(self, request: Request) -> Response:
    user = request.state.blog_user
    return Response(f'{self.locale}:{user["username"]}:{user["locale"]}')


def test_external_provider_authenticates_and_logs_out_each_locale():
  app = FastAPI()
  providers: dict[str, FakeHostAuthProvider] = {}

  def provider_factory(locale: str) -> FakeHostAuthProvider:
    provider = FakeHostAuthProvider(locale)
    providers[locale] = provider
    return provider

  def configure_admin(locale: str, admin) -> None:
    admin.add_view(IdentityView(locale))

  fastapi_blog.add_admin_to_app(
    app,
    auth_provider=provider_factory,
    secret_key='s' * 64,
    database_url='sqlite+aiosqlite:///:memory:',
    locales=['en', 'ru'],
    default_locale='en',
    configure_admin=configure_admin,
  )

  async def exercise_authentication():
    try:
      async with AsyncClient(
        transport=ASGITransport(app=app), base_url='http://test'
      ) as client:
        for locale, base in [('en', '/admin'), ('ru', '/ru/admin')]:
          login_page = await client.get(f'{base}/login')
          csrf_token = re.search(
            r'name="csrftoken" value="([^"]+)"', login_page.text
          ).group(1)
          login = await client.post(
            f'{base}/login',
            data={
              'username': 'host-user',
              'password': 'host-password',
              'csrftoken': csrf_token,
            },
          )
          assert login.status_code == 303

          identity = await client.get(f'{base}/identity')
          assert identity.status_code == 200
          assert identity.text == f'{locale}:host-user:{locale}'
          assert providers[locale].authenticate_calls > 0

          logout = await client.post(
            f'{base}/logout', data={'csrftoken': csrf_token}
          )
          assert logout.status_code == 303
          assert providers[locale].logout_calls == 1
          protected = await client.get(
            f'{base}/identity', follow_redirects=False
          )
          assert protected.status_code == 303
          assert '/login' in protected.headers['location']
    finally:
      await app.state.admin_engine.dispose()

  asyncio.run(exercise_authentication())


def test_setup_facade_accepts_external_provider_without_legacy_credentials(
  monkeypatch, tmp_path
):
  from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

  admin_module = fastapi_blog._import_admin()
  engine = create_async_engine('sqlite+aiosqlite:///:memory:')
  monkeypatch.setattr(
    admin_module,
    'create_engine_and_session',
    lambda database_url: (engine, async_sessionmaker(engine)),
  )
  app = FastAPI()
  providers: dict[str, FakeHostAuthProvider] = {}

  def provider_factory(locale: str) -> FakeHostAuthProvider:
    provider = FakeHostAuthProvider(locale)
    providers[locale] = provider
    return provider

  admins = fastapi_blog.setup_fastapi_blog(
    app,
    posts_dirname=str(tmp_path),
    auth_provider=provider_factory,
    secret_key='s' * 64,
    locales=['en', 'ru'],
    default_locale='en',
  )

  assert set(admins) == {'en', 'ru'}
  assert admins['en'].auth_provider is providers['en']
  assert admins['ru'].auth_provider is providers['ru']
  asyncio.run(engine.dispose())


def test_provider_conflicts_with_legacy_credentials_at_construction():
  app = FastAPI()
  with pytest.raises(ConfigurationError, match='cannot be combined'):
    fastapi_blog.add_admin_to_app(
      app,
      auth_provider=FakeHostAuthProvider('en'),
      admin_password='legacy-password',
      secret_key='s' * 64,
      locales=['en'],
      default_locale='en',
    )


def test_single_provider_instance_is_rejected_for_multiple_locales():
  app = FastAPI()
  with pytest.raises(ConfigurationError, match='only be used with one locale'):
    fastapi_blog.add_admin_to_app(
      app,
      auth_provider=FakeHostAuthProvider('en'),
      secret_key='s' * 64,
      locales=['en', 'ru'],
      default_locale='en',
    )


def test_provider_factory_must_return_distinct_instances():
  app = FastAPI()
  provider = FakeHostAuthProvider('en')
  with pytest.raises(ConfigurationError, match='fresh provider instance'):
    fastapi_blog.add_admin_to_app(
      app,
      auth_provider=lambda locale: provider,
      secret_key='s' * 64,
      locales=['en', 'ru'],
      default_locale='en',
    )


def test_provider_must_implement_auth_lifecycle_at_construction():
  app = FastAPI()
  with pytest.raises(ConfigurationError, match='must implement login'):
    fastapi_blog.add_admin_to_app(
      app,
      auth_provider=IncompleteAuthProvider(),
      secret_key='s' * 64,
      locales=['en'],
      default_locale='en',
    )


def test_provider_signature_is_validated_at_construction():
  app = FastAPI()
  with pytest.raises(
    ConfigurationError, match=r'incompatible login\(\) signature'
  ):
    fastapi_blog.add_admin_to_app(
      app,
      auth_provider=InvalidSignatureAuthProvider(),
      secret_key='s' * 64,
      locales=['en'],
      default_locale='en',
    )


def test_demo_provider_rejects_non_ascii_credentials_without_server_error(
  monkeypatch,
):
  monkeypatch.syspath_prepend(str(Path(__file__).parent / 'examples'))
  from demo_auth import DemoRBACAuthProvider

  from fastapi_blog.admin.passwords import get_password_hasher

  provider = DemoRBACAuthProvider('en')
  user = SimpleNamespace(
    id=1,
    is_active=True,
    hashed_password=get_password_hasher().hash('Admin123!'),
  )

  async def get_user(request, *, email=None, user_id=None):
    return user

  provider._get_user = get_user
  request = SimpleNamespace(session={})

  with pytest.raises(LoginFailed):
    asyncio.run(provider.login('админ', 'пароль', False, request))
