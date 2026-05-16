"""Authentication provider for starlette-admin."""

from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette_admin.auth import AdminUser, AuthProvider
from starlette_admin.exceptions import LoginFailed


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
    ):
        """Initialize auth provider with credentials and redirect URL."""
        super().__init__()
        self.username = username
        self.password = password
        self.redirect_after_login = redirect_after_login

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
