"""Authentication helpers for admin integration tests."""

from starlette.requests import Request
from starlette.responses import Response
from starlette_admin.auth import AdminUser, AuthProvider
from starlette_admin.exceptions import LoginFailed


class DemoTestAuthProvider(AuthProvider):
  """Small host-owned provider that accepts non-empty test credentials."""

  async def login(
    self,
    username: str,
    password: str,
    remember_me: bool,
    request: Request,
  ) -> Response | None:
    if not username or not password:
      raise LoginFailed('Invalid username or password')
    request.session['test_user'] = username
    return None

  async def authenticate(self, request: Request) -> AdminUser | None:
    username = request.session.get('test_user')
    if username is None:
      return None
    request.state.blog_user = {
      'username': username,
      'role': 'admin',
      'is_admin': True,
    }
    return AdminUser(username=username)

  async def logout(self, request: Request) -> Response | None:
    request.session.clear()
    return None
