"""Enhanced authentication provider with Role-Based Access Control (RBAC).

This module provides a database-integrated auth provider with role management.
"""

from typing import Any

from sqlalchemy import select
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response
from starlette_admin.auth import AdminUser, AuthProvider
from starlette_admin.exceptions import FormValidationError, LoginFailed

from .models import User
from .views import get_pwd_context


MIN_PASSWORD_LENGTH = 8


class Role:
    """Role definitions with permissions."""

    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"

    PERMISSIONS = {
        ADMIN: {
            "posts": ["create", "read", "update", "delete", "publish"],
            "users": ["create", "read", "update", "delete"],
            "settings": ["read", "update"],
            "role": ["create", "read", "update", "delete"],
            "user_with_roles": ["create", "read", "update", "delete"],
        },
        EDITOR: {
            "posts": ["create", "read", "update", "publish"],
            "users": ["read"],
            "settings": ["read"],
        },
        VIEWER: {
            "posts": ["read"],
            "users": [],
            "settings": [],
        },
    }

    @classmethod
    def get_permissions(cls, role: str) -> dict[str, list[str]]:
        """Get permissions for a role."""
        return cls.PERMISSIONS.get(role, cls.PERMISSIONS[cls.VIEWER])

    @classmethod
    def has_permission(cls, role: str, resource: str, action: str) -> bool:
        """Check if role has permission for resource action."""
        permissions = cls.get_permissions(role)
        return action in permissions.get(resource, [])


class RBACAuthProvider(AuthProvider):
    """Enhanced authentication provider with RBAC.

    Features:
    - Database-backed user authentication
    - Password hashing with bcrypt
    - Role-based access control (admin/editor/viewer)
    - Session management
    - Form validation
    """

    def __init__(
        self,
        session_factory: Any,
        redirect_after_login: str = "/admin/post/list",
        default_role: str = Role.VIEWER,
    ):
        """Initialize RBAC auth provider.

        Args:
            session_factory: SQLAlchemy async session factory
            redirect_after_login: URL to redirect after successful login
            default_role: Default role for new users

        """
        super().__init__()
        self.session_factory = session_factory
        self.redirect_after_login = redirect_after_login
        self.default_role = default_role
        self._pwd_context = None

    @property
    def pwd_context(self):
        """Get password context (lazy initialization)."""
        if self._pwd_context is None:
            self._pwd_context = get_pwd_context()
        return self._pwd_context

    async def _get_user_by_email(self, email: str) -> User | None:
        """Get user from database by email."""
        async with self.session_factory() as session:
            result = await session.execute(select(User).where(User.email == email))
            return result.scalar_one_or_none()

    async def login(
        self,
        username: str,
        password: str,
        remember_me: bool,
        request: Request,
        response: Response,
    ) -> Response:
        """Authenticate user with database credentials.

        Args:
            username: User email
            password: Plain text password
            remember_me: Whether to extend session
            request: Starlette request
            response: Starlette response

        Returns:
            Redirect response on success

        Raises:
            FormValidationError: If form data is invalid
            LoginFailed: If credentials are incorrect

        """
        # Validate form data
        if len(username) < 3:
            raise FormValidationError(
                {"username": "Email must be at least 3 characters"}
            )

        if len(password) < MIN_PASSWORD_LENGTH:
            raise FormValidationError(
                {
                    "password": f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
                }
            )

        # Get user from database
        user = await self._get_user_by_email(username)

        if user is None:
            raise LoginFailed("Invalid email or password")

        # Verify password
        if not self.pwd_context.verify(password, user.hashed_password):
            raise LoginFailed("Invalid email or password")

        # Determine role
        role = Role.ADMIN if user.is_admin else self.default_role

        # Save session
        request.session.update(
            {
                "user": user.email,
                "user_id": user.id,
                "is_admin": user.is_admin,
                "role": role,
            }
        )

        # Redirect to admin panel
        return RedirectResponse(url=self.redirect_after_login, status_code=303)

    async def is_authenticated(self, request: Request) -> bool:
        """Check if request is authenticated.

        Sets request.state.user with user info and permissions.

        Args:
            request: Starlette request

        Returns:
            True if authenticated, False otherwise

        """
        user_email = request.session.get("user")

        if user_email is None:
            return False

        # Load user info from database
        user = await self._get_user_by_email(user_email)

        if user is None:
            # User deleted from database - clear session
            request.session.clear()
            return False

        # Store user info in request state for later use
        role = request.session.get("role", self.default_role)
        request.state.user = {
            "email": user.email,
            "id": user.id,
            "is_admin": user.is_admin,
            "role": role,
            "permissions": Role.get_permissions(role),
        }

        return True

    def get_admin_user(self, request: Request) -> AdminUser | None:
        """Get admin user from request state.

        Args:
            request: Starlette request

        Returns:
            AdminUser object or None

        """
        if not hasattr(request.state, "user"):
            return None

        user_info = request.state.user
        return AdminUser(
            username=user_info["email"],
            photo_url=None,  # Can add avatar support later
        )

    async def logout(self, request: Request, response: Response) -> Response:
        """Logout user by clearing session.

        Args:
            request: Starlette request
            response: Starlette response

        Returns:
            Redirect response to login page

        """
        request.session.clear()
        # Use relative path to avoid route name conflicts with multi-locale admin instances
        # Each locale has its own route_name (e.g., admin_en, admin_ru)
        login_url = str(request.url).rsplit("/", 1)[0] + "/login"
        return Response(status_code=302, headers={"Location": login_url})


def has_permission(request: Request, resource: str, action: str) -> bool:
    """Check if current user has permission for resource action.

    Args:
        request: Starlette request (must have request.state.user)
        resource: Resource name (e.g., "posts", "users")
        action: Action name (e.g., "create", "read", "update", "delete")

    Returns:
        True if user has permission, False otherwise

    """
    if not hasattr(request.state, "user"):
        return False

    user_info = request.state.user
    role = user_info.get("role", Role.VIEWER)

    return Role.has_permission(role, resource, action)
