import os
import re
from collections.abc import Callable
from datetime import date, datetime
from typing import Any
from urllib.parse import quote, unquote
from xml.etree.ElementTree import Element, SubElement, tostring

import jinja2
from fastapi import FastAPI, HTTPException
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse, Response

from . import helpers
from .auth import ConfigurationError, add_startup_check, check_api_auth_config
from .models import FrontmatterSchema, SeoConfig
from .router import get_blog_router
from .seo import build_head, resolve_seo_config
from .validators import Validator


# The sitemap protocol allows at most this many URLs in one file.
SITEMAP_URL_LIMIT = 50_000
_SITEMAP_NS = 'http://www.sitemaps.org/schemas/sitemap/0.9'
# W3C Datetime as used by `<lastmod>`: a date, or a date and time with a zone.
_W3C_DATETIME = re.compile(
  r'\d{4}-\d{2}-\d{2}'
  r'(T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2}))?'
)


def add_blog_to_fastapi(
  app: FastAPI,
  prefix: str | None = 'blog',
  jinja2_loader: jinja2.BaseLoader = jinja2.PackageLoader(
    'fastapi_blog', 'templates'
  ),
  jinja2_extensions: set[str] = {
    'jinja2_time.TimeExtension',
    'jinja2.ext.debug',
  },
  favorite_post_ids: set[str] = set(),
  mount_statics: bool = True,
  strict_frontmatter: bool = True,
  sanitize_html: bool = True,
  posts_dirname: str = 'posts',
  pages_dirname: str = 'pages',
  include_api: bool | None = None,
  api_prefix: str = '/api/posts',
  api_require_auth: bool = True,
  locales: list[str] = ['en'],
  default_locale: str = 'en',
  admin_username: str | None = None,
  admin_password: str | None = None,
  frontmatter_schema: FrontmatterSchema | None = None,
  seo: SeoConfig | None = None,
  api_auth_dependency: Callable[..., Any] | None = None,
  jsonld_routes: bool = False,
  seo_routes: bool = False,
  require_if_match: bool = False,
  validators: tuple[Validator, ...] = (),
) -> FastAPI:
  """Add blog to FastAPI application.

  Args:
      app: FastAPI application instance
      prefix: URL prefix for blog routes (default: 'blog', None for root)
      jinja2_loader: Jinja2 template loader
      jinja2_extensions: Set of Jinja2 extensions to enable
      favorite_post_ids: Set of post slugs to feature on homepage
      mount_statics: Whether to mount static files (deprecated)
      strict_frontmatter: Use strict frontmatter validation. Ignored when
                          `frontmatter_schema` is given (set `extra` on the schema).
      sanitize_html: Sanitize HTML in markdown content
      posts_dirname: Directory containing blog posts
      pages_dirname: Directory containing pages
      include_api: Include REST API for post management.
                   Default: from FASTAPI_BLOG_INCLUDE_API env var, or False.
                   When True, adds REST endpoints visible in /docs.
                   Note: Admin panel (/admin) is separate - it's a web UI, not REST API.
      api_prefix: URL prefix for REST API (default: '/api/posts')
      api_require_auth: Require authentication for API (default: True).
                        The API then needs credentials (`admin_username` and
                        `admin_password`), `api_auth_dependency` or a
                        `SessionMiddleware`; otherwise the app fails at startup
                        with `ConfigurationError`.
      locales: List of supported locales for blog UI (default: ['en'])
      default_locale: Default locale when Accept-Language not matched (default: 'en')
      admin_username: Admin username for REST API auth (optional)
      admin_password: Admin password for REST API auth (optional)
      api_auth_dependency: Custom FastAPI dependency that authenticates REST API
                           requests (optional). It must raise `HTTPException`
                           when access is denied.
      jsonld_routes: Add `GET {prefix}/{slug}.jsonld` and
                     `GET {prefix}/index.jsonld` (default: False). Only
                     published posts are served; see `fastapi_blog.jsonld`.
      seo_routes: Add `GET /sitemap.xml`, `GET /robots.txt` and permanent
                  redirects for the `redirect_from` role (TODO 5.9.5;
                  default: False). Needs `seo.site_url`: without it the app
                  fails at startup with `ConfigurationError`.
      validators: External validators run on every write through the REST
                  API (TODO 6.2/6.3); blocking outcomes roll the write back
                  with HTTP 422.
      require_if_match: Require the `If-Match` header on update/delete
                  (TODO 4.7); see `get_api_router()`. Default: `False`.
      frontmatter_schema: Custom schema of the post frontmatter. Its roles
                          (title, date, published, tags, description) tell the
                          blog which field is which. Default: the built-in fields.
                          Also used by the REST API when `include_api=True`.
                          The admin panel (extra `admin`) uses it only if you
                          pass the same schema to `add_admin_to_app()`;
                          `setup_fastapi_blog()` does that for you.
      seo: Site-wide SEO settings (TODO 5.9.2); stronger than the schema's
                          own `seo` section. `None` (default) uses the
                          schema's section.

  Returns:
      FastAPI application with blog routes added

  Example:
      ```python
      from fastapi import (
        FastAPI,
      )
      from fastapi_blog import (
        add_blog_to_fastapi,
      )

      app = FastAPI()

      # Basic blog
      add_blog_to_fastapi(
        app
      )

      # With REST API enabled
      add_blog_to_fastapi(
        app,
        include_api=True,
      )
      ```

  """
  # Handle environment variable for include_api
  if include_api is None:
    env_value = os.getenv('FASTAPI_BLOG_INCLUDE_API', 'false').lower()
    include_api = env_value in ('true', '1', 'yes')

  # Prep the templates
  env = jinja2.Environment(
    loader=jinja2_loader,
    extensions=list(jinja2_extensions),
    autoescape=jinja2.select_autoescape(['html', 'xml']),
  )
  templates = Jinja2Templates(env=env)

  # Add redirects
  # Only add root redirect when prefix is set
  # When prefix=None, the blog router itself handles /
  if prefix is not None:

    @app.get('/', include_in_schema=False)
    async def root_redirect():
      return RedirectResponse(url=f'/{prefix}/', status_code=302)

    # Add redirect from /{prefix} to /{prefix}/
    @app.get(f'/{prefix}', include_in_schema=False)
    async def blog_prefix_redirect():
      return RedirectResponse(url=f'/{prefix}/', status_code=302)

  # Router controls:
  # 1. Main router without locale prefix (uses default_locale)
  # 2. Routers for non-default locales with /{locale} prefix
  # 3. Redirect from /{default_locale} to clean URLs

  # Registered before the blog routers: with `prefix=None` the router's
  # `/{page_id}` catch-all would otherwise answer `/robots.txt` first.
  if seo_routes:
    _mount_seo_routes(
      app,
      seo=seo,
      frontmatter_schema=frontmatter_schema,
      prefix=prefix,
      posts_dirname=posts_dirname,
      strict=strict_frontmatter,
      default_locale=default_locale,
    )

  # Create main router for default locale (no locale in URL)
  main_router = get_blog_router(
    templates=templates,
    favorite_post_ids=favorite_post_ids,
    strict=strict_frontmatter,
    frontmatter_schema=frontmatter_schema,
    seo=seo,
    sanitize_html=sanitize_html,
    posts_dirname=posts_dirname,
    pages_dirname=pages_dirname,
    locales=locales,
    default_locale=default_locale,
    locale=default_locale,
    prefix=prefix,
    jsonld_routes=jsonld_routes,
  )

  # Mount main router without locale prefix
  if prefix is not None:
    app.include_router(main_router, prefix=f'/{prefix}', tags=['blog'])
  else:
    app.include_router(main_router, tags=['blog'])

  # Create routers for non-default locales
  for locale in locales:
    if locale == default_locale:
      continue  # Skip default locale - it's already mounted

    router = get_blog_router(
      templates=templates,
      favorite_post_ids=favorite_post_ids,
      strict=strict_frontmatter,
      frontmatter_schema=frontmatter_schema,
      seo=seo,
      sanitize_html=sanitize_html,
      posts_dirname=posts_dirname,
      pages_dirname=pages_dirname,
      locales=locales,
      default_locale=default_locale,
      locale=locale,
      prefix=prefix,
      jsonld_routes=jsonld_routes,
    )

    # Mount with locale prefix
    if prefix is not None:
      app.include_router(router, prefix=f'/{locale}/{prefix}', tags=['blog'])
    else:
      app.include_router(router, prefix=f'/{locale}', tags=['blog'])

  # Add middleware to redirect URLs with default locale to clean URLs
  from starlette.requests import Request as StarletteRequest

  class DefaultLocaleRedirectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
      path = request.url.path

      # Check if path starts with /{default_locale}
      if prefix is not None:
        # Check for /{default_locale}/blog/...
        locale_prefix = f'/{default_locale}/{prefix}'
        if path.startswith(locale_prefix):
          # Redirect to /blog/...
          new_path = path[len(f'/{default_locale}') :]
          # Preserve query string if present
          if request.url.query:
            new_path = f'{new_path}?{request.url.query}'
          return RedirectResponse(url=new_path, status_code=302)
      else:
        # Check for /{default_locale}/...
        locale_prefix = f'/{default_locale}/'
        if path.startswith(locale_prefix):
          # Redirect to /...
          new_path = path[len(f'/{default_locale}') :]
          # Preserve query string if present
          if request.url.query:
            new_path = f'{new_path}?{request.url.query}'
          return RedirectResponse(url=new_path, status_code=302)

      return await call_next(request)

  app.add_middleware(DefaultLocaleRedirectMiddleware)

  # Add canonical Link header middleware
  class CanonicalLinkHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: StarletteRequest, call_next):
      response = await call_next(request)

      # Only apply to HTML responses from public blog
      content_type = response.headers.get('content-type', '')
      if 'text/html' not in content_type:
        return response

      path = request.url.path

      # Don't apply to /admin
      if path.startswith('/admin') or any(
        path.startswith(f'/{loc}/admin') for loc in locales
      ):
        return response

      # Calculate canonical URL
      base = str(request.base_url).rstrip('/')
      canonical_path = path

      # Remove default locale prefix if present
      default_prefix = f'/{default_locale}'
      if prefix is not None:
        duplicate_pattern = f'/{default_locale}/{prefix}'
        if canonical_path.startswith(duplicate_pattern):
          canonical_path = canonical_path[len(default_prefix) :]
      else:
        if canonical_path.startswith(default_prefix + '/'):
          canonical_path = canonical_path[len(default_prefix) :]

      canonical_url = base + canonical_path
      response.headers['Link'] = f'<{canonical_url}>; rel="canonical"'

      return response

  app.add_middleware(CanonicalLinkHeaderMiddleware)

  # Optionally include REST API for post management
  if include_api:
    from .editor import get_api_router

    api_router = get_api_router(
      posts_dirname=posts_dirname,
      strict=strict_frontmatter,
      require_auth=api_require_auth,
      admin_username=admin_username,
      admin_password=admin_password,
      frontmatter_schema=frontmatter_schema,
      auth_dependency=api_auth_dependency,
      require_if_match=require_if_match,
      validators=validators,
    )
    app.include_router(api_router, prefix=api_prefix, tags=['api'])
    add_startup_check(
      app,
      lambda: check_api_auth_config(
        app,
        require_auth=api_require_auth,
        admin_username=admin_username,
        admin_password=admin_password,
        auth_dependency=api_auth_dependency,
      ),
    )

  return app


def _lastmod(post: dict[str, Any]) -> str | None:
  """Return the `updated`/`date` value as a W3C datetime, or `None`."""
  value = post.get('updated') or post.get('date')
  if isinstance(value, datetime):
    # A time without a zone isn't valid W3C Datetime: keep the date only.
    return value.isoformat() if value.tzinfo else value.date().isoformat()
  if isinstance(value, date):
    return value.isoformat()
  if isinstance(value, str) and _W3C_DATETIME.fullmatch(value):
    return value
  return None


def _mount_seo_routes(
  app: FastAPI,
  *,
  seo: SeoConfig | None,
  frontmatter_schema: FrontmatterSchema | None,
  prefix: str | None,
  posts_dirname: str,
  strict: bool,
  default_locale: str,
) -> None:
  """Add `sitemap.xml`, `robots.txt` and `redirect_from` redirects (5.9.5).

  Only published posts take part. The sitemap entries and the alias index
  are built once per state of the posts directory (`helpers.list_posts`
  returns the same tuple until a file changes), not once per request.
  """
  config = resolve_seo_config(seo, frontmatter_schema)
  if config is None or not config.site_url:

    def _require_site_url() -> None:
      raise ConfigurationError(
        '`seo_routes=True` requires seo.site_url to be configured.'
      )

    add_startup_check(app, _require_site_url)
    return

  site_url = config.site_url
  blog_path = f'/{prefix}' if prefix is not None else ''

  def absolute(path: str) -> str:
    return site_url + '/' + path.lstrip('/')

  def post_path(slug: Any) -> str:
    return f'{blog_path}/posts/{quote(str(slug), safe="")}'

  def build_snapshot(
    posts: tuple[dict, ...],
  ) -> tuple[list[tuple[str, str | None]], dict[str, str]]:
    entries: dict[str, str | None] = {
      absolute(f'{blog_path}/'): None,
      absolute(f'{blog_path}/posts'): None,
    }
    tags: set[str] = set()
    # Lookup keys use the decoded form: that is what `request.url.path` is.
    live = {f'{blog_path}/posts/{post["slug"]}' for post in posts}
    reserved = {
      '/',
      '/robots.txt',
      '/sitemap.xml',
      blog_path or '/',
      f'{blog_path}/',
      f'{blog_path}/posts',
      f'{blog_path}/tags',
    }
    aliases: dict[str, str] = {}
    for post in posts:
      own_path = f'{blog_path}/posts/{post["slug"]}'
      own_url = absolute(post_path(post['slug']))
      head = build_head(
        post,
        config=config,
        request_url=own_url,
        locale=default_locale,
        page_type='article',
      )
      target = head.get('canonical_url') or own_url
      robots = {str(item).lower() for item in head.get('robots') or []}
      # Excluded: `noindex` documents and documents canonical elsewhere.
      if 'noindex' not in robots and target.rstrip('/') == own_url:
        entries[target] = _lastmod(post)
        tags.update(str(tag) for tag in post.get('tags') or [])
      raw_aliases = post.get('redirect_from') or []
      if isinstance(raw_aliases, str):
        raw_aliases = [raw_aliases]
      for alias in raw_aliases:
        text = unquote(str(alias).strip()).strip('/')
        if not text:
          continue
        # A bare word is a slug of the current URL scheme; anything with a
        # `/` is a site path (it may include the blog prefix itself).
        path = f'/{text}' if '/' in text else f'{blog_path}/posts/{text}'
        # A live address or the document's own never redirects (no loops, no
        # hijacked pages); two documents claiming one alias: the first wins.
        if path in live or path in reserved or path == own_path:
          continue
        aliases.setdefault(path, target)
    if not config.noindex_tags:
      for tag in tags:
        entries[absolute(f'{blog_path}/tags/{quote(tag, safe="")}')] = None
    return sorted(entries.items()), aliases

  state: dict[str, Any] = {'posts': None, 'snapshot': ([], {})}

  def snapshot() -> tuple[list[tuple[str, str | None]], dict[str, str]]:
    posts = helpers.list_posts(
      posts_dirname=posts_dirname, strict=strict, schema=frontmatter_schema
    )
    if state['posts'] is not posts:
      state['snapshot'] = build_snapshot(posts)
      state['posts'] = posts
    return state['snapshot']

  def urlset(entries: list[tuple[str, str | None]]) -> bytes:
    root = Element('urlset', xmlns=_SITEMAP_NS)
    for loc, lastmod in entries:
      item = SubElement(root, 'url')
      SubElement(item, 'loc').text = loc
      if lastmod:
        SubElement(item, 'lastmod').text = lastmod
    return tostring(root, encoding='utf-8', xml_declaration=True)

  @app.get('/sitemap.xml', include_in_schema=False)
  async def seo_sitemap() -> Response:
    entries, _ = snapshot()
    if len(entries) <= SITEMAP_URL_LIMIT:
      return Response(urlset(entries), media_type='application/xml')
    root = Element('sitemapindex', xmlns=_SITEMAP_NS)
    parts = -(-len(entries) // SITEMAP_URL_LIMIT)
    for number in range(1, parts + 1):
      node = SubElement(root, 'sitemap')
      SubElement(node, 'loc').text = absolute(f'/sitemap-{number}.xml')
    return Response(
      tostring(root, encoding='utf-8', xml_declaration=True),
      media_type='application/xml',
    )

  @app.get('/sitemap-{number}.xml', include_in_schema=False)
  async def seo_sitemap_part(number: str) -> Response:
    entries, _ = snapshot()
    if (
      not (number.isascii() and number.isdigit())
      or int(number) < 1
      or len(entries) <= SITEMAP_URL_LIMIT
    ):
      raise HTTPException(status_code=404)
    start = (int(number) - 1) * SITEMAP_URL_LIMIT
    chunk = entries[start : start + SITEMAP_URL_LIMIT]
    if not chunk:
      raise HTTPException(status_code=404)
    return Response(urlset(chunk), media_type='application/xml')

  @app.get('/robots.txt', include_in_schema=False)
  async def seo_robots() -> PlainTextResponse:
    lines = ['User-agent: *']
    if config.disallow:
      lines.extend(f'Disallow: {path}' for path in config.disallow)
    else:
      lines.append('Allow: /')
    lines.extend(['', f'Sitemap: {absolute("/sitemap.xml")}'])
    return PlainTextResponse('\n'.join(lines) + '\n')

  class RedirectFromMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Any) -> Response:
      if request.method in ('GET', 'HEAD'):
        target = snapshot()[1].get(request.url.path.rstrip('/') or '/')
        if target is not None:
          return RedirectResponse(target, status_code=301)
      return await call_next(request)

  app.add_middleware(RedirectFromMiddleware)
