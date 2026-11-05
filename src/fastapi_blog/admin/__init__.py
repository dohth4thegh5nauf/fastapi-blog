"""Admin panel integration for FastAPI Blog.

Provides starlette-admin based administration interface with:
- User management
- Post management with WYSIWYG editor
- Starlette Admin authentication provider integration
"""

import logging
import os
import pathlib
import warnings
from collections.abc import Callable, Mapping

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from starlette_admin.auth import AuthProvider
from starlette_admin.contrib.sqla import Admin
from starlette_admin.i18n import I18nConfig

from ..config import CollectionSpec
from ..models import FrontmatterSchema
from ..permissions import Authorizer
from ..security import resolve_admin_credentials, resolve_session_secret
from ._legacy_auth_provider import _LegacyAuthProvider
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
from ..i18n import get_all_locale_names, load_translations

# NOTE: Custom translation loading removed - now we create separate admin instances
# for each locale instead of dynamically switching translations
# Import views after translations are loaded and locale is set
from .views import HomeView, PostModelView, UserModelView  # noqa: E402


# Set up logger
logger = logging.getLogger('fastapi_blog.admin')

# File-based views removed - using CustomView instead

__all__ = [
  'add_admin_to_app',
  'AuthProviderFactory',
  'User',
  'Post',
  'Role',
  'UserWithRoles',
  'UserModelView',
  'PostModelView',
  'HomeView',
  'RoleModelView',
  'UserWithRolesModelView',
  'MarkdownField',
  'TagsField',
  'SlugField',
]

AuthProviderFactory = Callable[[str], AuthProvider]


def _resolve_auth_providers(
  auth_provider: AuthProvider | AuthProviderFactory | None,
  locales: list[str],
  *,
  default_locale: str,
  admin_username: str,
  admin_password: str,
  auth_users: Mapping[str, Mapping[str, str]] | None,
  translations_dir: str | pathlib.Path | None,
) -> dict[str, AuthProvider]:
  """Build and validate one independent provider for each admin locale."""

  def validate_provider(provider: object, locale: str) -> AuthProvider:
    from ..auth import ConfigurationError

    if not isinstance(provider, AuthProvider):
      raise ConfigurationError(
        f'The auth_provider factory returned an invalid provider for '
        f'locale {locale!r}; expected starlette_admin.auth.AuthProvider.'
      )
    missing_methods = [
      method_name
      for method_name in ('login', 'authenticate', 'logout')
      if getattr(type(provider), method_name)
      is getattr(AuthProvider, method_name)
    ]
    if missing_methods:
      raise ConfigurationError(
        f'The auth provider for locale {locale!r} must implement '
        f'{", ".join(missing_methods)}().'
      )
    return provider

  if auth_provider is None:
    return {
      locale: _LegacyAuthProvider(
        username=admin_username,
        password=admin_password,
        redirect_after_login=(
          '/admin/user/list'
          if locale == default_locale
          else f'/{locale}/admin/user/list'
        ),
        locale=locale,
        users=auth_users,
        translations_dir=(str(translations_dir) if translations_dir else None),
      )
      for locale in locales
    }

  if isinstance(auth_provider, AuthProvider):
    if len(locales) != 1:
      from ..auth import ConfigurationError

      raise ConfigurationError(
        'A single auth_provider instance can only be used with one locale. '
        'Pass a locale-to-provider factory for localized admin panels.'
      )
    return {locales[0]: validate_provider(auth_provider, locales[0])}

  if not callable(auth_provider):
    from ..auth import ConfigurationError

    raise ConfigurationError(
      'auth_provider must be a Starlette Admin AuthProvider instance or a '
      'factory accepting a locale.'
    )

  providers: dict[str, AuthProvider] = {}
  identities: set[int] = set()
  for locale in locales:
    provider = validate_provider(auth_provider(locale), locale)
    if id(provider) in identities:
      from ..auth import ConfigurationError

      raise ConfigurationError(
        'The auth_provider factory must return a fresh provider instance '
        'for every locale.'
      )
    identities.add(id(provider))
    providers[locale] = provider
  return providers


def _session_middleware_options(app: FastAPI) -> dict | None:
  """Return the options of an already-installed SessionMiddleware."""
  for middleware in app.user_middleware:
    if middleware.cls == SessionMiddleware:
      return dict(getattr(middleware, 'kwargs', {}) or {})
  return None


def _validate_existing_session_middleware(
  app: FastAPI, secret_key: str, https_only: bool
) -> bool:
  """Ensure an externally installed session middleware matches our policy."""
  options = _session_middleware_options(app)
  if options is None:
    return False

  configured_secret = options.get('secret_key')
  if isinstance(configured_secret, bytes):
    configured_secret = configured_secret.decode('utf-8')
  if configured_secret != secret_key:
    from ..auth import ConfigurationError

    raise ConfigurationError(
      'The existing SessionMiddleware must use the same secret_key as '
      'FastAPI Blog.'
    )

  same_site = str(options.get('same_site', 'lax')).lower()
  if same_site not in {'lax', 'strict'}:
    from ..auth import ConfigurationError

    raise ConfigurationError(
      "The existing SessionMiddleware must use same_site='lax' or 'strict'."
    )
  if https_only and not options.get('https_only', False):
    from ..auth import ConfigurationError

    raise ConfigurationError(
      'https_only=True requires the existing SessionMiddleware to set '
      'https_only=True.'
    )
  return True


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
  secret_key: str,
  enable_role_management: bool = False,
  admin_username: str = 'admin',
  frontmatter_schema: FrontmatterSchema | None = None,
  posts_dirname: str | None = None,
  collection_spec: CollectionSpec | None = None,
  collection_specs: Mapping[str, CollectionSpec] | None = None,
  authorize: Authorizer | None = None,
  sanitize_html: bool = True,
  translations_dir: str | pathlib.Path | None = None,
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
      secret_key: Signs starlette-admin's own CSRF/flash cookies
      enable_role_management: Whether to automatically add role management views
      admin_username: Root admin username for role management access control
      frontmatter_schema: Custom frontmatter schema for the markdown posts
      posts_dirname: Directory with the markdown posts (same one passed to
          `setup_fastapi_blog`/`add_blog_to_fastapi`); falls back to
          `POSTS_DIR`/a cwd-based guess when not given (see
          `markdown_crud.get_posts_directory`)
      collection_spec: Project-file collection spec; takes precedence over
          `posts_dirname`/`frontmatter_schema` for the managed collection
      authorize: Shared `(request, resource, action) -> bool` permission
          callback; the default authorizer is used when not given
      collection_specs: All collections of the project, keyed by name; used
          to resolve `link` fields that point at another collection
      sanitize_html: Sanitize the admin Markdown preview like public pages
      translations_dir: Project YAML files that extend bundled UI translations

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
  translations = load_translations(locale, translations_dir)
  home_label = translations['nav']['home']
  user_label = translations['nav']['users']
  user_name_for_button = translations['user']['singular']
  posts_label = translations['nav']['posts']

  # Create admin instance
  # Use a unique route_name for each locale to ensure url_for generates correct URLs.
  admin = Admin(
    engine,
    title=title,
    base_url=base_url,
    route_name=f'admin_{locale}',  # Unique route name for each locale
    auth_provider=auth_provider,
    secret_key=secret_key,  # Signs starlette-admin's own CSRF/flash cookies
    templates_dir=templates_dir,
    i18n_config=i18n_config,
    debug=os.getenv('DEBUG', 'false').lower() == 'true',
    index_view=HomeView(
      label=home_label,
      icon='fa fa-home',
      locale=locale,
      schema=frontmatter_schema,
      posts_dirname=posts_dirname,
      authorize=authorize,
      translations_dir=str(translations_dir) if translations_dir else None,
      collection_spec=collection_spec,
    ),
  )

  # Add locale data to template context
  locale_names = get_all_locale_names(translations_dir, available_locales)
  admin.templates.env.globals['available_locales'] = available_locales
  admin.templates.env.globals['locale_names'] = locale_names
  admin.templates.env.globals['current_locale'] = locale
  admin.templates.env.globals['default_locale'] = default_locale
  # This is needed for templates that don't use url_for (e.g., logo, logout)
  admin.templates.env.globals['admin_base_url'] = base_url

  # Add User view with translated labels
  user_view = UserModelView(User, icon='fa fa-users')
  user_view.authorize = authorize
  user_view.menu_label = user_label
  user_view.display_name = user_name_for_button
  admin.add_view(user_view)

  # Add role management views if enabled
  if enable_role_management:
    from starlette_admin import DropDown

    from .models import Role, UserWithRoles
    from .views_role import RoleModelView, UserWithRolesModelView

    # Get category label from translations
    role_category = translations['role']['section_label']

    # Create role management views with admin_username for access control
    role_view = RoleModelView(
      Role,
      locale=locale,
      admin_username=admin_username,
      icon='fa fa-shield',
      authorize=authorize,
      translations_dir=str(translations_dir) if translations_dir else None,
    )
    user_roles_view = UserWithRolesModelView(
      UserWithRoles,
      locale=locale,
      admin_username=admin_username,
      icon='fa fa-users-cog',
      authorize=authorize,
      translations_dir=str(translations_dir) if translations_dir else None,
    )

    # Add as dropdown menu group
    # DropDown automatically hides when all nested views are inaccessible
    admin.add_view(
      DropDown(
        menu_label=role_category,
        icon='fa fa-shield',
        views=[role_view, user_roles_view],
      )
    )

  # Add markdown CRUD views
  from .markdown_crud import (
    MarkdownCreateView,
    MarkdownEditView,
    MarkdownFileManager,
    MarkdownListView,
    MarkdownSaveView,
    get_posts_directory,
  )

  posts_dir = (
    (
      str(collection_spec.dir)
      if not callable(collection_spec.dir)
      else str(pathlib.Path.cwd())
    )
    if collection_spec is not None
    else get_posts_directory(posts_dirname)
  )

  # Add list view (shows in menu)
  posts_list_view = MarkdownListView(
    posts_dir=posts_dir,
    locale=locale,
    schema=frontmatter_schema,
    collection_spec=collection_spec,
    authorize=authorize,
    collection_specs=collection_specs,
    translations_dir=str(translations_dir) if translations_dir else None,
  )
  localized_label = (
    collection_spec.label_for(locale) if collection_spec else None
  )
  posts_list_view.menu_label = localized_label or posts_label
  admin.add_view(posts_list_view)

  # Add edit and create views (don't show in menu)
  admin.add_view(
    MarkdownEditView(
      posts_dir=posts_dir,
      locale=locale,
      schema=frontmatter_schema,
      collection_spec=collection_spec,
      authorize=authorize,
      collection_specs=collection_specs,
      translations_dir=str(translations_dir) if translations_dir else None,
    )
  )
  admin.add_view(
    MarkdownCreateView(
      posts_dir=posts_dir,
      locale=locale,
      schema=frontmatter_schema,
      collection_spec=collection_spec,
      authorize=authorize,
      collection_specs=collection_specs,
      translations_dir=str(translations_dir) if translations_dir else None,
    )
  )
  admin.add_view(
    MarkdownSaveView(
      MarkdownFileManager(
        posts_dir,
        frontmatter_schema
        or (collection_spec.schema if collection_spec else None),
        collection_spec,
        collection_specs=collection_specs,
      ),
      authorize=authorize,
      sanitize_html=sanitize_html,
    )
  )

  return admin


def add_admin_to_app(
  app: FastAPI,
  *,
  title: str = 'Admin Panel',
  database_url: str | None = None,
  admin_username: str | None = None,
  admin_password: str | None = None,
  secret_key: str | None = None,
  add_session_middleware: bool = True,
  init_database: bool = True,
  locales: list[str] | None = None,
  default_locale: str | None = None,
  enable_role_management: bool = False,
  frontmatter_schema: FrontmatterSchema | None = None,
  posts_dirname: str | None = None,
  collection_spec: CollectionSpec | None = None,
  collection_specs: Mapping[str, CollectionSpec] | None = None,
  insecure_dev: bool = False,
  https_only: bool = False,
  authorize: Authorizer | None = None,
  auth_users: Mapping[str, Mapping[str, str]] | None = None,
  sanitize_html: bool = True,
  translations_dir: str | pathlib.Path | None = None,
  configure_admin: Callable[[str, Admin], None] | None = None,
  auth_provider: AuthProvider | AuthProviderFactory | None = None,
) -> dict[str, Admin]:
  """Add starlette-admin panel to FastAPI application.

  Creates separate admin instances for each locale at /admin/{locale}.
  /admin redirects to /admin/{default_locale}.

  Args:
    app: FastAPI application instance
    title: Admin panel title
    database_url: Database URL (default: from DATABASE_URL env or SQLite)
    admin_username: Admin username (default: from FASTAPI_BLOG_ADMIN_LOGIN env or 'admin')
    admin_password: Required admin password, or FASTAPI_BLOG_ADMIN_PASSWORD.
    secret_key: Required session secret, or SECRET_KEY (32+ chars).
    insecure_dev: Enable old development credentials explicitly (unsafe).
    https_only: Set the session cookie Secure flag.
    sanitize_html: Sanitize the admin Markdown preview like public pages.
                  Set False only for trusted content that intentionally uses raw HTML.
    translations_dir: Optional directory containing UI translation overlays.
    configure_admin: Optional callback invoked with `(locale, admin)` after
      built-in views are registered and immediately before each admin is
      mounted. Use it to add supported Starlette Admin views.
    authorize: Shared `(request, resource, action) -> bool` permission callback.
    auth_users: Optional extra login accounts mapped to password and role.
    auth_provider: A Starlette Admin provider instance (one locale only) or
      factory called once per locale. The host application owns authentication.
    add_session_middleware: Whether to add SessionMiddleware (default: True)
    init_database: Whether to initialize database on startup (default: True)
    locales: List of available locales (default: ['en', 'ru'])
    default_locale: Default locale for /admin redirect (default: 'en')
    enable_role_management: Enable role management views (default: False)
    frontmatter_schema: Custom schema of the post frontmatter (default: the
      built-in fields). The post list, post form and dashboard are built from
      it. Saves use the internal document service and do not require the REST API.
    posts_dirname: Directory with the markdown posts. Pass the same value
      given to `setup_fastapi_blog`/`add_blog_to_fastapi` so the admin panel
      and the blog/REST API always agree on where posts live (default:
      `POSTS_DIR`, deprecated, or a cwd-based guess).
    collection_spec: Project-file collection spec for the managed collection
      (takes precedence over `posts_dirname`/`frontmatter_schema`).
    collection_specs: All collections of the project, keyed by name; used to
      resolve `link` fields that point at another collection.
    collection_spec: Project-file collection spec; takes precedence over
      `posts_dirname`/`frontmatter_schema` for the managed collection

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

    import os

    app = FastAPI()

    # English and Russian with EN as default
    admins = add_admin_to_app(
      app,
      title='My Blog Admin',
      admin_password=os.environ[
        'FASTAPI_BLOG_ADMIN_PASSWORD'
      ],
      secret_key=os.environ[
        'SECRET_KEY'
      ],
      locales=[
        'en',
        'ru',
      ],
      default_locale='en',  # /admin → /admin/en
    )

    # Russian by default
    admins = add_admin_to_app(
      app,
      title='Админ-панель блога',
      admin_password=os.environ[
        'FASTAPI_BLOG_ADMIN_PASSWORD'
      ],
      secret_key=os.environ[
        'SECRET_KEY'
      ],
      locales=[
        'en',
        'ru',
      ],
      default_locale='ru',  # /admin → /admin/ru
    )
    ```

  """
  if collection_spec is not None:
    posts_dirname = (
      str(collection_spec.dir)
      if not callable(collection_spec.dir)
      else str(pathlib.Path.cwd())
    )
    if translations_dir is None:
      translations_dir = collection_spec.translations_dir
    if frontmatter_schema is not None:
      collection_spec = collection_spec.with_schema(frontmatter_schema)
    else:
      frontmatter_schema = collection_spec.schema

  # Set default locales if not provided
  if locales is None:
    locales = ['en', 'ru']
  else:
    locales = list(locales)

  if not locales or len(set(locales)) != len(locales):
    raise ValueError('locales must contain at least one unique locale.')

  if default_locale is None:
    default_locale = 'en'  # Default to English

  # Validate default_locale is in locales
  if default_locale not in locales:
    raise ValueError(
      f"default_locale '{default_locale}' must be in locales list {locales}"
    )

  if auth_provider is not None:
    if (
      admin_username is not None
      or admin_password is not None
      or auth_users is not None
    ):
      from ..auth import ConfigurationError

      raise ConfigurationError(
        'auth_provider cannot be combined with admin_username, '
        'admin_password, or auth_users; configure authentication in the '
        'provider only.'
      )
    secret_key = resolve_session_secret(secret_key)
    resolved_admin_username = 'admin'
    resolved_admin_password = ''
  else:
    (
      resolved_admin_username,
      resolved_admin_password,
      secret_key,
    ) = resolve_admin_credentials(
      admin_username,
      admin_password,
      secret_key,
      insecure_dev=insecure_dev,
    )

  locale_auth_providers = _resolve_auth_providers(
    auth_provider,
    locales,
    default_locale=default_locale,
    admin_username=resolved_admin_username,
    admin_password=resolved_admin_password,
    auth_users=auth_users,
    translations_dir=translations_dir,
  )

  # Add session middleware if needed (must be added AFTER CORS).
  existing_session = _validate_existing_session_middleware(
    app, secret_key, https_only
  )
  if existing_session:
    if add_session_middleware:
      warnings.warn(
        'SessionMiddleware is already added to the application. '
        'Set add_session_middleware=False to avoid duplication. '
        'Skipping duplicate middleware addition.',
        UserWarning,
        stacklevel=2,
      )
  elif add_session_middleware:
    app.add_middleware(
      SessionMiddleware,
      secret_key=secret_key,
      same_site='lax',
      https_only=https_only,
    )
  else:
    from ..auth import ConfigurationError

    raise ConfigurationError(
      'add_session_middleware=False requires an existing SessionMiddleware.'
    )

  # Starlette Admin 1.0 protects its own forms with CSRF tokens (TODO 7.4:
  # don't duplicate them). The Origin guard is installed for the REST API
  # only (see `add_blog_to_fastapi`/`add_editor_to_app`).

  # Create engine and session
  engine, session_factory = create_engine_and_session(database_url)

  # Initialize database if requested
  if init_database:
    # Store engine for later access
    app.state.admin_engine = engine

  # Use lifespan events for database setup and cleanup.
  from contextlib import asynccontextmanager

  original_lifespan = getattr(app.router, 'lifespan_context', None)

  @asynccontextmanager
  async def admin_lifespan(app):
    try:
      if init_database:
        await init_db(engine)
        logger.info('Admin database initialized')

      if original_lifespan:
        async with original_lifespan(app):
          yield
      else:
        yield
    finally:
      await engine.dispose()

  app.router.lifespan_context = admin_lifespan

  # Note: admin_username is passed directly to role management views
  # to avoid app.state identity issues with uvicorn --reload

  # Get templates directory for custom templates
  from pathlib import Path

  import fastapi_blog

  pkg_path = Path(fastapi_blog.__file__).parent
  templates_dir = str(pkg_path / 'admin' / 'templates')

  # Create admin instances:
  # - Default locale at /admin (no locale prefix)
  # - Other locales at /{locale}/admin
  admins = {}

  # Create main admin for default locale (no locale in URL)
  default_admin = _create_admin_for_locale(
    locale=default_locale,
    engine=engine,
    title=title,
    base_url='/admin',
    auth_provider=locale_auth_providers[default_locale],
    templates_dir=templates_dir,
    available_locales=locales,
    default_locale=default_locale,
    secret_key=secret_key,
    enable_role_management=enable_role_management,
    admin_username=resolved_admin_username,
    frontmatter_schema=frontmatter_schema,
    posts_dirname=posts_dirname,
    collection_spec=collection_spec,
    collection_specs=collection_specs,
    authorize=authorize,
    sanitize_html=sanitize_html,
    translations_dir=translations_dir,
  )

  if configure_admin is not None:
    configure_admin(default_locale, default_admin)
  default_admin.mount_to(app)
  admins[default_locale] = default_admin
  logger.info('Admin panel (%s) mounted at /admin', default_locale)

  # Create admin instances for non-default locales
  for locale in locales:
    if locale == default_locale:
      continue  # Skip default - already mounted

    admin = _create_admin_for_locale(
      locale=locale,
      engine=engine,
      title=title,
      base_url=f'/{locale}/admin',
      auth_provider=locale_auth_providers[locale],
      templates_dir=templates_dir,
      available_locales=locales,
      default_locale=default_locale,
      secret_key=secret_key,
      enable_role_management=enable_role_management,
      admin_username=resolved_admin_username,
      frontmatter_schema=frontmatter_schema,
      posts_dirname=posts_dirname,
      collection_spec=collection_spec,
      collection_specs=collection_specs,
      authorize=authorize,
      sanitize_html=sanitize_html,
      translations_dir=translations_dir,
    )

    if configure_admin is not None:
      configure_admin(locale, admin)
    admin.mount_to(app)
    admins[locale] = admin
    logger.info('Admin panel (%s) mounted at /%s/admin', locale, locale)

  # Add middleware to redirect URLs with default locale to clean URLs
  # e.g. /en/admin -> /admin
  from starlette.middleware.base import BaseHTTPMiddleware
  from starlette.requests import Request as StarletteRequest
  from starlette.responses import RedirectResponse

  class AdminDefaultLocaleRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
      path = request.url.path

      # Check for /{default_locale}/admin/... and redirect to /admin/...
      locale_prefix = f'/{default_locale}/admin'
      if path.startswith(locale_prefix):
        # Redirect to /admin/...
        new_path = path[len(f'/{default_locale}') :]
        # Preserve query string if present
        if request.url.query:
          new_path = f'{new_path}?{request.url.query}'
        return RedirectResponse(url=new_path, status_code=302)

      return await call_next(request)

  app.add_middleware(AdminDefaultLocaleRedirectMiddleware)

  logger.info('Markdown CRUD API available at /api/posts (authenticated)')

  if init_database:
    logger.info('Database initialized')
  else:
    logger.warning(
      'Database initialization disabled. Call init_db(engine) manually.'
    )

  logger.debug('Admin credentials: username=%s', admin_username)
  logger.info('Available locales: %s', ', '.join(locales))
  logger.info('Access at: http://localhost:8000/admin')

  return admins
