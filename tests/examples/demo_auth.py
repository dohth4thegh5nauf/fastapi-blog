"""Demo-only Starlette Admin authentication provider."""

import secrets

from starlette.requests import Request
from starlette.responses import Response
from starlette_admin.auth import AdminUser, AuthProvider
from starlette_admin.exceptions import LoginFailed


class DemoAuthProvider(AuthProvider):
  """Authenticate the fixed demo account; replace this in host applications."""

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
    """Validate the demo credentials and establish a signed session."""
    valid_username = secrets.compare_digest(username, 'admin')
    valid_password = secrets.compare_digest(password, 'Admin123!')
    if not (valid_username and valid_password):
      raise LoginFailed('Invalid username or password')

    request.session['demo_username'] = username
    return None

  async def authenticate(self, request: Request) -> AdminUser | None:
    """Resolve the demo session and expose its identity to authorization."""
    username = request.session.get('demo_username')
    if username is None:
      return None
    request.state.blog_user = {
      'username': username,
      'role': 'admin',
      'is_admin': True,
    }
    return AdminUser(username=username)

  async def logout(self, request: Request) -> Response | None:
    """Clear the demo session."""
    request.session.clear()
    return None


def create_demo_auth_provider(locale: str = 'en') -> DemoAuthProvider:
  """Create a fresh provider for one localized demo admin."""
  return DemoAuthProvider(locale)
