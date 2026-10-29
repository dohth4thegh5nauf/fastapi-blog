"""Authentication provider for starlette-admin."""

from collections.abc import Callable

from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.status import HTTP_303_SEE_OTHER, HTTP_400_BAD_REQUEST
from starlette.templating import Jinja2Templates
from starlette_admin.auth import AdminUser, AuthProvider
from starlette_admin.exceptions import FormValidationError, LoginFailed
from starlette_admin.helpers import HTTP_422, index_url, safe_redirect_url

from ..i18n import load_translations


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

  Uses hardcoded credentials for initial setup.
  In production, integrate with database users.
  """

  def __init__(
    self,
    username: str = 'admin',
    password: str = 'Admin123!',  # nosec B107 - default dev password, override in production
    redirect_after_login: str = '/dashboard/user/list',
    locale: str = 'en',
  ):
    """Initialize auth provider with credentials and redirect URL."""
    super().__init__()
    self.username = username
    self.password = password
    self.redirect_after_login = redirect_after_login
    self.locale = locale

  async def login(
    self,
    username: str,
    password: str,
    remember_me: bool,
    request: Request,
  ) -> Response | None:
    # Simple hardcoded check - replace with database lookup in production
    if username == self.username and password == self.password:
      request.session.update({'user': username, 'is_admin': True})
      # Redirect to configured page after successful login
      return RedirectResponse(url=self.redirect_after_login, status_code=303)

    raise LoginFailed('Invalid username or password')

  async def authenticate(self, request: Request) -> AdminUser | None:
    user = request.session.get('user')
    return AdminUser(username=user) if user else None

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
    _ = _yaml_translator(self.locale)
    if request.method == 'GET':
      return templates.TemplateResponse(
        request=request, name='login.html', context={'_': _}
      )

    form = await request.form()
    fallback = index_url(request)
    next_url = safe_redirect_url(
      request.query_params.get('next') or fallback, request, fallback
    )
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
