import importlib
import os
import pathlib
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI

from .auth import ConfigurationError
from .config import CollectionSpec, Project, find_project, load_project
from .editor import add_editor_to_app, get_api_router
from .main import add_blog_to_fastapi
from .models import DEFAULT_SCHEMA, FieldSpec, FrontmatterSchema, SeoConfig
from .permissions import Authorizer
from .router import get_blog_router


if TYPE_CHECKING:
  from .admin import Admin, AuthProvider, AuthProviderFactory, add_admin_to_app


__version__ = '0.10.0'

_ADMIN_EXTRA_HINT = (
  'The admin panel needs the `admin` extra: pip install "fastapi-blog[admin]"'
)

# Names loaded on first access, so that `import fastapi_blog` doesn't import
# anything from the admin panel (see `__getattr__`)
_LAZY_ADMIN_NAMES = ('Admin', 'AuthProviderFactory', 'add_admin_to_app')


def _import_admin() -> Any:
  """Import `fastapi_blog.admin`, explaining how to install it if it's missing.

  Returns:
      The `fastapi_blog.admin` module.

  Raises:
      ImportError: If the `admin` extra isn't installed.

  """
  try:
    return importlib.import_module('.admin', __name__)
  except ModuleNotFoundError as exc:
    # Only translate "a dependency is missing"; real bugs must stay visible
    missing = (exc.name or '').split('.')[0]
    if missing and missing != 'fastapi_blog':
      raise ImportError(_ADMIN_EXTRA_HINT) from exc
    raise


def __getattr__(name: str) -> Any:
  # PEP 562: load the admin panel only when someone asks for it
  if name in _LAZY_ADMIN_NAMES:
    return getattr(_import_admin(), name)
  raise AttributeError(f'module {__name__!r} has no attribute {name!r}')


def __dir__() -> list[str]:
  return sorted([*globals(), *_LAZY_ADMIN_NAMES])


def setup_fastapi_blog(
  app: FastAPI,
  *,
  posts_dirname: str = 'posts',
  include_api: bool = False,
  locales: list[str] = ['en'],
  default_locale: str = 'en',
  admin_username: str | None = None,
  admin_password: str | None = None,
  secret_key: str | None = None,
  enable_role_management: bool = False,
  frontmatter_schema: FrontmatterSchema | None = None,
  seo: SeoConfig | None = None,
  seo_routes: bool = False,
  health_routes: bool = True,
  sanitize_html: bool = True,
  admin: bool = True,
  collection_spec: CollectionSpec | None = None,
  authorize: Authorizer | None = None,
  insecure_dev: bool = False,
  https_only: bool = False,
  auth_users: dict[str, dict[str, str]] | None = None,
  translations_dir: str | pathlib.Path | None = None,
  configure_admin: Callable[[str, 'Admin'], None] | None = None,
  auth_provider: 'AuthProvider | AuthProviderFactory | None' = None,
  api_auth_dependency: Callable[..., Any] | None = None,
) -> dict[str, 'Admin']:
  """Configure the blog and (optionally) the admin panel for a FastAPI app.

  `frontmatter_schema` (optional) sets the post fields for the blog, the REST API
  and the admin panel at once. Without it the built-in fields are used.

  With `admin=False` only the blog (and the REST API, if `include_api=True`) is
  added. The `admin` extra isn't needed then, and no default credentials are
  made up: the REST API needs `admin_username` and `admin_password` (or the
  matching environment variables), or a `SessionMiddleware`.

  Args:
      app: FastAPI application instance.
      posts_dirname: Directory with the markdown posts.
      include_api: Include the REST API for post management.
      locales: Supported UI locales.
      default_locale: Default UI locale.
      admin_username: Admin username (default: `FASTAPI_BLOG_ADMIN_LOGIN`).
      admin_password: Admin password (default: `FASTAPI_BLOG_ADMIN_PASSWORD`).
      secret_key: Session secret key of the admin panel.
      authorize: Shared callback `(request, resource, action) -> bool`.
      insecure_dev: Explicitly allow the old development credentials (unsafe).
      https_only: Mark the session cookie Secure (HTTPS only).
      auth_users: Optional additional admin-panel accounts with password/role.
      auth_provider: Starlette Admin provider instance or locale-to-provider
          factory for the admin UI. The host application owns authentication.
      api_auth_dependency: Optional independent auth dependency for the REST API.
      enable_role_management: Add the role management views to the admin panel.
      frontmatter_schema: Custom schema of the post frontmatter.
      seo: Site-wide SEO settings (TODO 5.9.2); stronger than the schema's
          own `seo` section.
      seo_routes: Add `sitemap.xml`, `robots.txt` and `redirect_from`
          redirects (TODO 5.9.5); bare-slug aliases redirect under every
          mounted locale. Requires `seo.site_url`. Default: `False`.
      health_routes: Add the `/api/v1/health{,/live,/ready}` probes in the
          draft-inadarei-api-health-check-06 format. Default: `True`; pass
          `False` to disable.
      sanitize_html: Sanitize Markdown HTML in public pages and admin preview.
          Disable only when all Markdown authors are trusted. Default: `True`.
      admin: Add the admin panel (needs the `admin` extra). Default: `True`.
      collection_spec: Optional collection from `load_project()`. Its
          directory/schema are shared by the blog, REST API and admin; a
          configured `slug_template` enables generated slugs.
      translations_dir: Optional project directory containing UI translation
          YAML overlays; derived from `collection_spec` when omitted.
      configure_admin: Optional synchronous callback invoked with `(locale,
          admin)` immediately before each localized admin instance is mounted.

  Returns:
      Admin instances by locale, or an empty dict when `admin=False`.

  Raises:
      ImportError: If `admin=True` and the `admin` extra isn't installed.

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

  # Fail early (before any route is added) if the admin panel is unavailable
  add_admin = _import_admin().add_admin_to_app if admin else None

  if auth_provider is not None and not admin:
    raise ConfigurationError('auth_provider requires admin=True.')
  if auth_provider is not None and (
    admin_username is not None
    or admin_password is not None
    or auth_users is not None
  ):
    raise ConfigurationError(
      'auth_provider cannot be combined with admin_username, admin_password, '
      'or auth_users; configure authentication in the provider only.'
    )

  if auth_provider is not None and add_admin is not None:
    provider_locales = list(locales)
    if not provider_locales or len(set(provider_locales)) != len(
      provider_locales
    ):
      raise ValueError('locales must contain at least one unique locale.')
    if default_locale not in provider_locales:
      raise ValueError(
        f"default_locale '{default_locale}' must be in locales list "
        f'{provider_locales}'
      )
    admin_module = _import_admin()
    providers = admin_module._resolve_auth_providers(
      auth_provider,
      provider_locales,
      default_locale=default_locale,
      admin_username='admin',
      admin_password='',
      auth_users=None,
      translations_dir=translations_dir,
    )

    def resolved_auth_provider(locale: str) -> Any:
      return providers[locale]

    auth_provider = resolved_auth_provider

  # Resolve credentials once for the legacy admin and API authentication path.
  if auth_provider is None:
    if admin_username is None:
      admin_username = os.getenv('FASTAPI_BLOG_ADMIN_LOGIN')
    if admin_password is None:
      admin_password = os.getenv('FASTAPI_BLOG_ADMIN_PASSWORD')

    if add_admin is not None and not insecure_dev:
      from .security import resolve_admin_credentials

      admin_username, admin_password, secret_key = resolve_admin_credentials(
        admin_username, admin_password, secret_key
      )
  elif admin:
    from .security import resolve_session_secret

    secret_key = resolve_session_secret(secret_key)

  add_blog_to_fastapi(
    app,
    posts_dirname=posts_dirname,
    include_api=include_api,
    api_auth_dependency=api_auth_dependency,
    locales=locales,
    default_locale=default_locale,
    admin_username=admin_username,
    admin_password=admin_password,
    frontmatter_schema=frontmatter_schema,
    seo=seo,
    seo_routes=seo_routes,
    health_routes=health_routes,
    sanitize_html=sanitize_html,
    collection_spec=collection_spec,
    authorize=authorize,
    translations_dir=translations_dir,
  )
  if add_admin is None:
    return {}
  return add_admin(
    app,
    locales=locales,
    default_locale=default_locale,
    admin_username=admin_username,
    admin_password=admin_password,
    secret_key=secret_key,
    enable_role_management=enable_role_management,
    frontmatter_schema=frontmatter_schema,
    posts_dirname=posts_dirname,
    collection_spec=collection_spec,
    authorize=authorize,
    insecure_dev=insecure_dev,
    https_only=https_only,
    auth_users=auth_users,
    sanitize_html=sanitize_html,
    translations_dir=translations_dir,
    configure_admin=configure_admin,
    auth_provider=auth_provider,
  )
