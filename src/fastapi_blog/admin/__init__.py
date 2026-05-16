"""Admin panel integration for FastAPI Blog.

Provides starlette-admin based administration interface with:
- User management
- Post management with WYSIWYG editor
- Simple authentication provider
"""

import logging
import os
import pathlib
import warnings

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from starlette_admin.contrib.sqla import Admin
from starlette_admin.i18n import I18nConfig

from .auth_provider import SimpleAuthProvider
from .database import create_engine_and_session, init_db
from .fields import MarkdownField, SlugField, TagsField
from .models import Post, Role, User, UserWithRoles
from .views_role import RoleModelView, UserWithRolesModelView


try:
    from starlette_admin.i18n import lazy_gettext as _
except ImportError:
    # Fallback if i18n is not available
    def _(message: str) -> str:
        return message


# Import i18n utilities
from .i18n import get_all_locale_names, load_translations

# NOTE: Custom translation loading removed - now we create separate admin instances
# for each locale instead of dynamically switching translations
# Import views after translations are loaded and locale is set
from .views import HomeView, PostModelView, UserModelView  # noqa: E402


# Set up logger
logger = logging.getLogger("fastapi_blog.admin")

# File-based views removed - using CustomView instead

__all__ = [
    "add_admin_to_app",
    "User",
    "Post",
    "Role",
    "UserWithRoles",
    "SimpleAuthProvider",
    "UserModelView",
    "PostModelView",
    "HomeView",
    "RoleModelView",
    "UserWithRolesModelView",
    "MarkdownField",
    "TagsField",
    "SlugField",
]


def _has_session_middleware(app: FastAPI) -> bool:
    """Check if SessionMiddleware is already added to the app.

    Args:
      app: FastAPI application instance

    Returns:
      True if SessionMiddleware is already added, False otherwise

    """
    for middleware in app.user_middleware:
        if middleware.cls == SessionMiddleware:
            return True
    return False


def _create_admin_for_locale(
    locale: str,
    *,
    engine,
    title: str,
    base_url: str,
    auth_provider,
    templates_dir: str,
    available_locales: list[str],
    default_locale: str,
    enable_role_management: bool = False,
    admin_username: str = "admin",
) -> Admin:
    """Create an Admin instance for a specific locale.

    Args:
        locale: Language code (e.g. 'en', 'ru')
        engine: SQLAlchemy engine
        title: Admin panel title
        base_url: Base URL for this admin instance
        auth_provider: Authentication provider instance
        templates_dir: Path to custom templates directory
        available_locales: List of all available locales for language switcher
        default_locale: Default locale for the application
        enable_role_management: Whether to automatically add role management views
        admin_username: Root admin username for role management access control

    Returns:
        Configured Admin instance

    """
    # Configure i18n without built-in language switcher
    # We'll use custom language switcher with URL redirects
    # Each admin instance uses its own locale via I18nConfig
    i18n_config = I18nConfig(
        default_locale=locale,
        language_switcher=None,  # Disabled - we use custom switcher
    )

    # Load translations from YAML files
    translations = load_translations(locale)
    home_label = translations["nav"]["home"]
    user_label = translations["nav"]["users"]
    user_name_for_button = translations["user"]["singular"]
    posts_label = translations["nav"]["posts"]

    # Create admin instance
    # Use a unique route_name for each locale to ensure url_for generates correct URLs.
    admin = Admin(
        engine,
        title=title,
        base_url=base_url,
        route_name=f"admin_{locale}",  # Unique route name for each locale
        auth_provider=auth_provider,
        templates_dir=templates_dir,
        i18n_config=i18n_config,
        debug=os.getenv("DEBUG", "false").lower() == "true",
        index_view=HomeView(label=home_label, icon="fa fa-home", locale=locale),
    )

    # Add locale data to template context
    locale_names = get_all_locale_names()
    admin.templates.env.globals["available_locales"] = available_locales
    admin.templates.env.globals["locale_names"] = locale_names
    admin.templates.env.globals["current_locale"] = locale
    admin.templates.env.globals["default_locale"] = default_locale
    # This is needed for templates that don't use url_for (e.g., logo, logout)
    admin.templates.env.globals["admin_base_url"] = base_url

    # Add User view with translated labels
    user_view = UserModelView(User, icon="fa fa-users")
    user_view.label = user_label
    user_view.name = user_name_for_button
    admin.add_view(user_view)

    # Add role management views if enabled
    if enable_role_management:
        from starlette_admin import DropDown

        from .models_role import Role, UserWithRoles
        from .views_role import RoleModelView, UserWithRolesModelView

        # Get category label from translations
        role_category = translations["role"]["section_label"]

        # Create role management views with admin_username for access control
        role_view = RoleModelView(
            Role, locale=locale, admin_username=admin_username, icon="fa fa-shield"
        )
        user_roles_view = UserWithRolesModelView(
            UserWithRoles,
            locale=locale,
            admin_username=admin_username,
            icon="fa fa-users-cog",
        )

        # Add as dropdown menu group
        # DropDown automatically hides when all nested views are inaccessible
        admin.add_view(
            DropDown(
                label=role_category,
                icon="fa fa-shield",
                views=[role_view, user_roles_view],
            )
        )

    # Add markdown CRUD views
    from .markdown_crud import (
        MarkdownCreateView,
        MarkdownEditView,
        MarkdownListView,
        get_posts_directory,
    )

    posts_dir = get_posts_directory()

    # Add list view (shows in menu)
    posts_list_view = MarkdownListView(posts_dir=posts_dir, locale=locale)
    posts_list_view.label = posts_label
    admin.add_view(posts_list_view)

    # Add edit and create views (don't show in menu)
    admin.add_view(MarkdownEditView(posts_dir=posts_dir, locale=locale))
    admin.add_view(MarkdownCreateView(posts_dir=posts_dir, locale=locale))

    return admin


def add_admin_to_app(
    app: FastAPI,
    *,
    title: str = "Admin Panel",
    database_url: str | None = None,
    admin_username: str | None = None,
    admin_password: str | None = None,
    secret_key: str | None = None,
    add_session_middleware: bool = True,
    init_database: bool = True,
    locales: list[str] | None = None,
    default_locale: str | None = None,
    enable_role_management: bool = False,
) -> dict[str, Admin]:
    """Add starlette-admin panel to FastAPI application.

    Creates separate admin instances for each locale at /admin/{locale}.
    /admin redirects to /admin/{default_locale}.

    Args:
      app: FastAPI application instance
      title: Admin panel title
      database_url: Database URL (default: from DATABASE_URL env or SQLite)
      admin_username: Admin username (default: from FASTAPI_BLOG_ADMIN_LOGIN env or 'admin')
      admin_password: Admin password (default: from FASTAPI_BLOG_ADMIN_PASSWORD env or 'Admin123!')
      secret_key: Secret key for sessions (default: from SECRET_KEY env)
      add_session_middleware: Whether to add SessionMiddleware (default: True)
      init_database: Whether to initialize database on startup (default: True)
      locales: List of available locales (default: ['en', 'ru'])
      default_locale: Default locale for /admin redirect (default: 'en')
      enable_role_management: Enable role management views (default: False)

    Returns:
      Dictionary mapping locale codes to Admin instances
      e.g. {'en': admin_en, 'ru': admin_ru}

    Example:
      ```python
      from fastapi import (
          FastAPI,
      )
      from fastapi_blog.admin import (
          add_admin_to_app,
      )

      app = FastAPI()

      # English and Russian with EN as default
      admins = add_admin_to_app(
          app,
          title="My Blog Admin",
          admin_password="SuperSecret123!",
          locales=[
              "en",
              "ru",
          ],
          default_locale="en",  # /admin → /admin/en
      )

      # Russian by default
      admins = add_admin_to_app(
          app,
          title="Админ-панель блога",
          locales=[
              "en",
              "ru",
          ],
          default_locale="ru",  # /admin → /admin/ru
      )
      ```

    """
    # Handle environment variables for admin credentials
    if admin_username is None:
        admin_username = os.getenv("FASTAPI_BLOG_ADMIN_LOGIN", "admin")
    if admin_password is None:
        admin_password = os.getenv("FASTAPI_BLOG_ADMIN_PASSWORD", "Admin123!")

    # Set default locales if not provided
    if locales is None:
        locales = ["en", "ru"]

    if default_locale is None:
        default_locale = "en"  # Default to English

    # Validate default_locale is in locales
    if default_locale not in locales:
        raise ValueError(
            f"default_locale '{default_locale}' must be in locales list {locales}"
        )

    # Get secret key
    if secret_key is None:
        secret_key = os.getenv(
            "SECRET_KEY", "change-me-in-production-please-use-strong-secret"
        )

    # Validate secret_key strength
    WEAK_SECRETS = {
        "change-me-in-production-please-use-strong-secret",
        "changeme",
        "secret",
        "test-secret-key",
        "",
    }
    if secret_key in WEAK_SECRETS or len(secret_key) < 32:
        warnings.warn(
            f"secret_key is weak (length: {len(secret_key)}). "
            "Use secrets.token_hex(32) for production. "
            "Example: python -c 'import secrets; print(secrets.token_hex(32))'",
            UserWarning,
            stacklevel=2,
        )

    # Add session middleware if needed (must be added AFTER CORS)
    if add_session_middleware:
        if _has_session_middleware(app):
            warnings.warn(
                "SessionMiddleware is already added to the application. "
                "Set add_session_middleware=False to avoid duplication. "
                "Skipping duplicate middleware addition.",
                UserWarning,
                stacklevel=2,
            )
        else:
            app.add_middleware(SessionMiddleware, secret_key=secret_key)

    # Create engine and session
    engine, session_factory = create_engine_and_session(database_url)

    # Initialize database if requested
    if init_database:
        # Store engine for later access
        app.state.admin_engine = engine

        # Use lifespan event for async initialization (modern approach)
        from contextlib import asynccontextmanager

        # Check if app already has a lifespan
        original_lifespan = getattr(app.router, "lifespan_context", None)

        @asynccontextmanager
        async def admin_lifespan(app):
            # Startup: initialize database
            await init_db(engine)
            logger.info("Admin database initialized")

            # Call original lifespan if exists
            if original_lifespan:
                async with original_lifespan(app):
                    yield
            else:
                yield

            # Shutdown: cleanup if needed

        # Replace app's lifespan
        app.router.lifespan_context = admin_lifespan

    # Note: admin_username is passed directly to role management views
    # to avoid app.state identity issues with uvicorn --reload

    # Get templates directory for custom templates
    from pathlib import Path

    import fastapi_blog

    pkg_path = Path(fastapi_blog.__file__).parent
    templates_dir = str(pkg_path / "admin" / "templates")

    # Create admin instances:
    # - Default locale at /admin (no locale prefix)
    # - Other locales at /{locale}/admin
    admins = {}

    # Create main admin for default locale (no locale in URL)
    default_auth_provider = SimpleAuthProvider(
        username=admin_username,
        password=admin_password,
        redirect_after_login="/admin/user/list",
    )

    default_admin = _create_admin_for_locale(
        locale=default_locale,
        engine=engine,
        title=title,
        base_url="/admin",
        auth_provider=default_auth_provider,
        templates_dir=templates_dir,
        available_locales=locales,
        default_locale=default_locale,
        enable_role_management=enable_role_management,
        admin_username=admin_username,
    )

    default_admin.mount_to(app)
    admins[default_locale] = default_admin
    logger.info("Admin panel (%s) mounted at /admin", default_locale)

    # Create admin instances for non-default locales
    for locale in locales:
        if locale == default_locale:
            continue  # Skip default - already mounted

        auth_provider = SimpleAuthProvider(
            username=admin_username,
            password=admin_password,
            redirect_after_login=f"/{locale}/admin/user/list",
        )

        admin = _create_admin_for_locale(
            locale=locale,
            engine=engine,
            title=title,
            base_url=f"/{locale}/admin",
            auth_provider=auth_provider,
            templates_dir=templates_dir,
            available_locales=locales,
            default_locale=default_locale,
            enable_role_management=enable_role_management,
            admin_username=admin_username,
        )

        admin.mount_to(app)
        admins[locale] = admin
        logger.info("Admin panel (%s) mounted at /%s/admin", locale, locale)

    # Add middleware to redirect URLs with default locale to clean URLs
    # e.g. /en/admin -> /admin
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request as StarletteRequest
    from starlette.responses import RedirectResponse

    class AdminDefaultLocaleRedirectMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: StarletteRequest, call_next):
            path = request.url.path

            # Check for /{default_locale}/admin/... and redirect to /admin/...
            locale_prefix = f"/{default_locale}/admin"
            if path.startswith(locale_prefix):
                # Redirect to /admin/...
                new_path = path[len(f"/{default_locale}") :]
                # Preserve query string if present
                if request.url.query:
                    new_path = f"{new_path}?{request.url.query}"
                return RedirectResponse(url=new_path, status_code=302)

            return await call_next(request)

    app.add_middleware(AdminDefaultLocaleRedirectMiddleware)

    logger.info("Markdown CRUD API available at /api/posts (authenticated)")

    if init_database:
        logger.info("Database initialized")
    else:
        logger.warning(
            "Database initialization disabled. Call init_db(engine) manually."
        )

    logger.debug("Admin credentials: username=%s", admin_username)
    logger.info("Available locales: %s", ", ".join(locales))
    logger.info("Access at: http://localhost:8000/admin")

    return admins
