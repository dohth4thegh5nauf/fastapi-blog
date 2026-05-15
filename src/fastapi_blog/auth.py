"""Unified authentication for FastAPI Blog.

Provides a single dependency that supports both:
- Session-based auth (admin panel cookie)
- HTTP Basic Auth (REST API)
"""

import base64

from fastapi import HTTPException, Request, status


async def get_current_user(
    request: Request,
    *,
    admin_username: str | None = None,
    admin_password: str | None = None,
) -> str | None:
    """Get current authenticated user from session or Authorization header.

    Checks authentication in this order:
    1. Session cookie (set by admin panel)
    2. Authorization: Basic header

    Args:
        request: FastAPI request object
        admin_username: Expected username for Basic auth (optional)
        admin_password: Expected password for Basic auth (optional)

    Returns:
        Username if authenticated, None otherwise

    Example:
        ```python
        from fastapi import (
            Depends,
            FastAPI,
        )
        from fastapi_blog.auth import (
            get_current_user,
        )

        app = FastAPI()


        @app.get(
            "/protected"
        )
        async def protected(
            user: str
            | None = Depends(
                get_current_user
            ),
        ):
            if not user:
                raise HTTPException(
                    401,
                    "Authentication required",
                )
            return {
                "user": user
            }
        ```

    """
    # First, check session cookie (admin panel)
    user = request.session.get("user")
    if user:
        return user

    # Second, check Authorization: Basic header (REST API)
    if admin_username and admin_password:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Basic "):
            try:
                # Decode Basic auth
                credentials = base64.b64decode(auth_header[6:]).decode("utf-8")
                username, password = credentials.split(":", 1)

                # Verify credentials
                if username == admin_username and password == admin_password:
                    return username
            except (ValueError, UnicodeDecodeError):
                # Invalid Basic auth format
                pass

    return None


async def require_current_user(
    request: Request,
    *,
    admin_username: str | None = None,
    admin_password: str | None = None,
) -> str:
    """Require authentication via session or Basic auth.

    Same as get_current_user() but raises 401 if not authenticated.

    Args:
        request: FastAPI request object
        admin_username: Expected username for Basic auth (optional)
        admin_password: Expected password for Basic auth (optional)

    Returns:
        Username of authenticated user

    Raises:
        HTTPException: 401 if not authenticated

    """
    user = await get_current_user(
        request, admin_username=admin_username, admin_password=admin_password
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )
    return user
