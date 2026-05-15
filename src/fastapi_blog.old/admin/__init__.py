"""Admin panel integration for FastAPI Blog.

Provides starlette-admin based administration interface with:
- User management
- Post management with WYSIWYG editor
- Simple authentication provider
"""

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
from .models import Post, User


try:
    from starlette_admin.i18n import lazy_gettext as _
except ImportError:
    # Fallback if i18n is not available
    def _(message: str) -> str:
        return message


# NOTE: Custom translation loading removed - now we create separate admin instances
# for each locale instead of dynamically switching translations

# Import views after translations are loaded and locale is set
from .views import HomeView, PostModelView, UserModelView  # noqa: E402


# File-based views removed - using CustomView instead

__all__ = [
    "add_admin_to_app",
    "User",
    "Post",
    "SimpleAuthProvider",
    "UserModelView",
    "PostModelView",
    "HomeView",
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

    # Labels are hardcoded per locale (not using gettext to avoid global state)
    if locale == "ru":
        home_label = "Главная"
        user_label_singular = "Пользователь"
        user_label_plural = "Пользователи"
        user_name_for_button = "пользователя"  # Genitive case
        posts_label = "Посты"
    else:  # English
        home_label = "Home"
        user_label_singular = "User"
        user_label_plural = "Users"
        user_name_for_button = "User"
        posts_label = "Posts"

    # Create admin instance
    admin = Admin(
        engine,
        title=title,
        base_url=base_url,
        auth_provider=auth_provider,
        templates_dir=templates_dir,
        i18n_config=i18n_config,
        debug=os.getenv("DEBUG", "false").lower() == "true",
        index_view=HomeView(label=home_label, icon="fa fa-home"),
    )

    # Add User view with translated labels
    user_view = UserModelView(User, icon="fa fa-users")
    user_view.label = user_label_plural
    user_view.name = user_name_for_button
    user_view.label_plural = user_label_plural
    admin.add_view(user_view)

    # Add markdown CRUD views
    from .markdown_crud import (
        MarkdownCreateView,
        MarkdownEditView,
        MarkdownListView,
        get_posts_directory,
    )

    posts_dir = get_posts_directory()

    # Add list view (shows in menu)
    posts_list_view = MarkdownListView(posts_dir=posts_dir)
    posts_list_view.label = posts_label
    admin.add_view(posts_list_view)

    # Add edit and create views (don't show in menu)
    admin.add_view(MarkdownEditView(posts_dir=posts_dir))
    admin.add_view(MarkdownCreateView(posts_dir=posts_dir))

    return admin


def add_admin_to_app(
    app: FastAPI,
    *,
    title: str = "Admin Panel",
    database_url: str | None = None,
    admin_username: str = "admin",
    admin_password: str = "Admin123!",
    secret_key: str | None = None,
    add_session_middleware: bool = True,
    init_database: bool = True,
    # New API (preferred)
    locales: list[str] | None = None,
    default_locale: str | None = None,
    # Old API (deprecated, for backward compatibility)
    base_url: str | None = None,
    i18n_enabled: bool | None = None,
    i18n_default_locale: str | None = None,
    i18n_locales: list[str] | None = None,
) -> dict[str, Admin]:
    """Add starlette-admin panel to FastAPI application.

    Creates separate admin instances for each locale at /admin/{locale}.
    /admin redirects to /admin/{default_locale}.

    Args:
      app: FastAPI application instance
      title: Admin panel title
      database_url: Database URL (default: from DATABASE_URL env or SQLite)
      admin_username: Admin username for login (default: 'admin')
      admin_password: Admin password for login (default: 'Admin123!')
      secret_key: Secret key for sessions (default: from SECRET_KEY env)
      add_session_middleware: Whether to add SessionMiddleware (default: True)
      init_database: Whether to initialize database on startup (default: True)
      locales: List of available locales (default: ['en', 'ru'])
      default_locale: Default locale for /admin redirect (default: 'en')

      # Deprecated parameters (for backward compatibility):
      base_url: Deprecated. Ignored in new multi-locale architecture.
      i18n_enabled: Deprecated. Multi-locale is always enabled.
      i18n_default_locale: Deprecated. Use default_locale instead.
      i18n_locales: Deprecated. Use locales instead.

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
    # Handle backward compatibility with old parameters
    if locales is None:
        if i18n_locales is not None:
            warnings.warn(
                "i18n_locales is deprecated. Use 'locales' parameter instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            locales = i18n_locales
        else:
            locales = ["en", "ru"]

    if default_locale is None:
        if i18n_default_locale is not None:
            warnings.warn(
                "i18n_default_locale is deprecated. Use 'default_locale' parameter instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            default_locale = i18n_default_locale
        else:
            default_locale = "en"  # Default to English

    if base_url is not None:
        warnings.warn(
            "base_url parameter is deprecated and ignored. "
            "Admin panels are now mounted at /admin/{locale}.",
            DeprecationWarning,
            stacklevel=2,
        )

    if i18n_enabled is not None:
        warnings.warn(
            "i18n_enabled parameter is deprecated and ignored. "
            "Multi-locale support is always enabled.",
            DeprecationWarning,
            stacklevel=2,
        )

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
            print("✓ Admin database initialized")

            # Call original lifespan if exists
            if original_lifespan:
                async with original_lifespan(app):
                    yield
            else:
                yield

            # Shutdown: cleanup if needed

        # Replace app's lifespan
        app.router.lifespan_context = admin_lifespan

    # Get templates directory for custom templates
    from pathlib import Path

    import fastapi_blog

    pkg_path = Path(fastapi_blog.__file__).parent
    templates_dir = str(pkg_path / "admin" / "templates")

    # Create admin instances for each locale
    admins = {}

    for locale in locales:
        # Create auth provider for this locale
        # redirect_after_login will be set to /admin/{locale}/user/list
        auth_provider = SimpleAuthProvider(
            username=admin_username,
            password=admin_password,
            redirect_after_login=f"/admin/{locale}/user/list",
        )

        # Create admin instance for this locale
        admin = _create_admin_for_locale(
            locale=locale,
            engine=engine,
            title=title,
            base_url=f"/admin/{locale}",
            auth_provider=auth_provider,
            templates_dir=templates_dir,
            available_locales=locales,
        )

        # Mount to app
        admin.mount_to(app)
        admins[locale] = admin

        print(f"✓ Admin panel ({locale}) mounted at /admin/{locale}")

    # Add redirect from /admin to /admin/{default_locale}
    from starlette.responses import RedirectResponse

    @app.get("/admin")
    @app.get("/admin/")
    async def admin_redirect():
        return RedirectResponse(url=f"/admin/{default_locale}", status_code=307)

    print(f"✓ /admin redirects to /admin/{default_locale}")
    print("✓ Markdown CRUD API available at /api/posts (authenticated)")

    if init_database:
        print("✓ Database initialized")
    else:
        print("⚠ Database initialization disabled. Call init_db(engine) manually.")

    print(f"✓ Login: username='{admin_username}' password='{admin_password}'")
    print(f"✓ Available locales: {', '.join(locales)}")
    print(f"✓ Access at: http://localhost:8000/admin/{default_locale}")

    return admins
