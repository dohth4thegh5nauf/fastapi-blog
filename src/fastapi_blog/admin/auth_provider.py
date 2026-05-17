# ruff: noqa: F821
"""Authentication provider for starlette-admin."""

from typing import TYPE_CHECKING

from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette.status import (
    HTTP_303_SEE_OTHER,
    HTTP_400_BAD_REQUEST,
    HTTP_422_UNPROCESSABLE_ENTITY,
)
from starlette_admin.auth import AdminUser, AuthProvider
from starlette_admin.exceptions import FormValidationError, LoginFailed

from .i18n import load_translations


if TYPE_CHECKING:
    from starlette_admin.base import BaseAdmin


class SimpleAuthProvider(AuthProvider):
    """Simple authentication provider for admin panel.

    Uses hardcoded credentials for initial setup.
    In production, integrate with JWT auth or database users.
    """

    def __init__(
        self,
        username: str = "admin",
        password: str = "Admin123!",  # nosec B107 - default dev password, override in production
        redirect_after_login: str = "/dashboard/user/list",
        locale: str = "en",
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
        response: Response,
    ) -> Response:
        # Simple hardcoded check - replace with database lookup in production
        if username == self.username and password == self.password:
            request.session.update({"user": username, "is_admin": True})
            # Redirect to configured page after successful login
            return RedirectResponse(url=self.redirect_after_login, status_code=303)

        raise LoginFailed("Invalid username or password")

    async def is_authenticated(self, request: Request) -> bool:
        user = request.session.get("user")
        return user is not None

    def get_admin_user(self, request: Request) -> AdminUser | None:
        user = request.session.get("user")
        if user:
            return AdminUser(username=user)
        return None

    async def logout(self, request: Request, response: Response) -> Response:
        request.session.clear()
        # Use relative path to avoid route name conflicts with multi-locale admin instances
        # Each locale has its own route_name (e.g., admin_en, admin_ru)
        login_url = str(request.url).rsplit("/", 1)[0] + "/login"
        return Response(status_code=302, headers={"Location": login_url})

    async def render_login(self, request: Request, admin: "BaseAdmin") -> Response:
        """Render login page with YAML translations.

        Overrides the default starlette-admin login to use our YAML translations
        instead of gettext .po/.mo files.
        """
        # Load translations for this locale
        translations = load_translations(self.locale)
        auth_translations = translations.get("auth", {})

        # Create translation function that uses YAML
        def _(key: str) -> str:
            # Map gettext keys to YAML keys
            key_mapping = {
                "Login to your account": auth_translations.get(
                    "login_to_account", "Login to your account"
                ),
                "Username": auth_translations.get("username", "Username"),
                "Password": auth_translations.get("password", "Password"),
                "Remember me": auth_translations.get("remember_me", "Remember me"),
                "Sign in": auth_translations.get("sign_in", "Sign in"),
            }
            return key_mapping.get(key, key)

        # Handle GET request - show login form
        if request.method == "GET":
            context = {
                "request": request,
                "admin": admin,
                "_": _,
                "_is_login_path": True,
                "login_logo_url": admin.login_logo_url
                if hasattr(admin, "login_logo_url")
                else None,
                "logo_url": admin.logo_url if hasattr(admin, "logo_url") else None,
            }
            return admin.templates.TemplateResponse(request, "login.html", context)

        # Handle POST request - process login
        form = await request.form()
        try:
            return await self.login(
                form.get("username"),  # type: ignore
                form.get("password"),  # type: ignore
                form.get("remember_me") == "on",
                request,
                RedirectResponse(
                    request.query_params.get("next")
                    or request.url_for(admin.route_name + ":index"),
                    status_code=HTTP_303_SEE_OTHER,
                ),
            )
        except FormValidationError as errors:
            context = {
                "request": request,
                "admin": admin,
                "_": _,
                "form_errors": errors,
                "_is_login_path": True,
                "login_logo_url": admin.login_logo_url
                if hasattr(admin, "login_logo_url")
                else None,
                "logo_url": admin.logo_url if hasattr(admin, "logo_url") else None,
            }
            return admin.templates.TemplateResponse(
                request,
                "login.html",
                context,
                status_code=HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except LoginFailed as error:
            context = {
                "request": request,
                "admin": admin,
                "_": _,
                "error": error.msg,
                "_is_login_path": True,
                "login_logo_url": admin.login_logo_url
                if hasattr(admin, "login_logo_url")
                else None,
                "logo_url": admin.logo_url if hasattr(admin, "logo_url") else None,
            }
            return admin.templates.TemplateResponse(
                request, "login.html", context, status_code=HTTP_400_BAD_REQUEST
            )
