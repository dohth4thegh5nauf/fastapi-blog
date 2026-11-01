"""Authentication provider for starlette-admin."""

import secrets
from collections.abc import Callable, Mapping

from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.status import HTTP_303_SEE_OTHER, HTTP_400_BAD_REQUEST
from starlette.templating import Jinja2Templates
from starlette_admin.auth import AdminUser, AuthProvider
from starlette_admin.exceptions import FormValidationError, LoginFailed
from starlette_admin.helpers import HTTP_422, index_url, safe_redirect_url

from ..i18n import load_translations
from ..permissions import ADMIN


def _yaml_translator(locale: str) -> Callable[[str], str]:
  """Build a `_(key)` function that maps gettext keys to our YAML strings.

  The built-in login template calls `_("Login to your account")` etc. via
  gettext; this lets it use `fastapi_blog/translations/*.yaml` instead.
  """
  auth_translations = load_translations(locale).get('auth', {})
  key_mapping = {
    'Login to your account': auth_translations.get(
      'login_to_account', 'Login to your account'
    ),
    'Username': auth_translations.get('username', 'Username'),
    'Password': auth_translations.get('password', 'Password'),
    'Remember me': auth_translations.get('remember_me', 'Remember me'),
    'Sign in': auth_translations.get('sign_in', 'Sign in'),
  }

  def _(key: str) -> str:
    return key_mapping.get(key, key)

  return _


class SimpleAuthProvider(AuthProvider):
  """Simple authentication provider for admin panel.

  Uses explicitly configured credentials and assigns a role to each session.
  """

  def __init__(
    self,
    username: str,
    password: str,
    redirect_after_login: str = '/dashboard/user/list',
    locale: str = 'en',
    users: Mapping[str, Mapping[str, str]] | None = None,
  ):
    """Initialize auth provider with credentials and redirect URL."""
    super().__init__()
    self.username = username
    self.password = password
    self.redirect_after_login = redirect_after_login
    self.locale = locale
    self.users = dict(users or {})

  async def login(
    self,
    username: str,
    password: str,
    remember_me: bool,
    request: Request,
  ) -> Response | None:
    role = None
    username_ok = secrets.compare_digest(
      username.encode(), self.username.encode()
    )
    password_ok = secrets.compare_digest(
      password.encode(), self.password.encode()
    )
    if username_ok and password_ok:
      role = ADMIN
    else:
      account = self.users.get(username)
      if account is not None:
        expected_password = account.get('password', '')
        expected_role = account.get('role', '')
        password_ok = secrets.compare_digest(
          password.encode(), expected_password.encode()
        )
        if password_ok and expected_role in ('admin', 'editor', 'viewer'):
          role = expected_role

    if role is None:
      raise LoginFailed('Invalid username or password')

    request.session.update(
      {
        'user': username,
        'is_admin': role == ADMIN,
        'role': role,
      }
    )
    request.state.blog_user = {
      'username': username,
      'role': role,
      'is_admin': role == ADMIN,
    }
    return RedirectResponse(url=self.redirect_after_login, status_code=303)

  async def authenticate(self, request: Request) -> AdminUser | None:
    user = request.session.get('user')
    if not user:
      return None
    role = request.session.get('role')
    if role is None and request.session.get('is_admin'):
      role = ADMIN
    request.state.blog_user = {
      'username': user,
      'role': role,
      'is_admin': role == ADMIN,
    }
    return AdminUser(username=user)

  async def logout(self, request: Request) -> Response | None:
    request.session.clear()
    return None

  async def render_login(
    self, request: Request, templates: Jinja2Templates
  ) -> Response:
    """Render login page with YAML translations.

    Mirrors `AuthProvider.render_login`, but passes our own `_` translation
    function (YAML files, not gettext .po/.mo) in the template context.
    """
    fallback = index_url(request)
    next_url = safe_redirect_url(
      request.query_params.get('next') or fallback, request, fallback
    )
    if getattr(request.state, 'admin_user', None) is not None:
      return RedirectResponse(next_url, status_code=HTTP_303_SEE_OTHER)

    _ = _yaml_translator(self.locale)
    if request.method == 'GET':
      return templates.TemplateResponse(
        request=request, name='login.html', context={'_': _}
      )

    form = await request.form()
    try:
      result = await self.login(
        str(form.get('username') or ''),
        str(form.get('password') or ''),
        form.get('remember_me') == 'on',
        request,
      )
      return result or RedirectResponse(
        next_url, status_code=HTTP_303_SEE_OTHER
      )
    except FormValidationError as errors:
      return templates.TemplateResponse(
        request=request,
        name='login.html',
        context={'_': _, 'form_errors': errors},
        status_code=HTTP_422,
      )
    except LoginFailed as error:
      return templates.TemplateResponse(
        request=request,
        name='login.html',
        context={'_': _, 'error': error.msg},
        status_code=HTTP_400_BAD_REQUEST,
      )
