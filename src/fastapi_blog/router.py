import collections
import pathlib
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from . import helpers, jsonld, store
from .i18n import Translator
from .models import SLUG_RE, FrontmatterSchema, SeoConfig
from .seo import build_head, resolve_seo_config


def get_blog_router(
  templates: Jinja2Templates,
  favorite_post_ids: set[str] = set(),
  strict: bool = True,
  sanitize_html: bool = True,
  posts_dirname: str = 'posts',
  pages_dirname: str = 'pages',
  locales: list[str] = ['en'],
  default_locale: str = 'en',
  locale: str | None = None,  # If set, creates routes for this specific locale
  prefix: str | None = 'blog',  # URL prefix (e.g., 'blog')
  frontmatter_schema: FrontmatterSchema | None = None,
  seo: SeoConfig | None = None,
  jsonld_routes: bool = False,
) -> APIRouter:
  router = APIRouter()

  def _get_canonical_url(request: Request) -> str:
    """Get canonical URL for current page.

    Rules:
    - If current locale is default: canonical = current URL without query string
    - If current locale is non-default: canonical = current URL without query string
    - If URL contains default locale prefix (e.g., /en/blog/...): canonical = URL without /en prefix
    """
    base = str(request.base_url).rstrip('/')
    path = request.url.path

    # Remove default locale prefix if present (these are duplicates)
    default_prefix = f'/{default_locale}'
    if prefix is not None:
      duplicate_pattern = f'/{default_locale}/{prefix}'
      if path.startswith(duplicate_pattern):
        path = path[len(default_prefix) :]  # Remove /en from /en/blog/...
    else:
      if path.startswith(default_prefix + '/'):
        path = path[len(default_prefix) :]  # Remove /en from /en/...

    return base + path

  def _get_alternate_urls(request: Request) -> dict[str, str]:
    """Get alternate URLs for all locales.

    Returns dict mapping locale codes to absolute URLs.
    """
    base = str(request.base_url).rstrip('/')
    path = request.url.path

    # Normalize path: remove any locale prefix to get the "clean" path
    clean_path = path
    for loc in locales:
      loc_prefix = f'/{loc}'
      if prefix is not None:
        pattern = f'/{loc}/{prefix}'
        if path.startswith(pattern):
          clean_path = path[len(loc_prefix) :]  # Remove /ru from /ru/blog/...
          break
      else:
        if path.startswith(loc_prefix + '/'):
          clean_path = path[len(loc_prefix) :]  # Remove /ru from /ru/...
          break

    # Build URLs for each locale
    result = {}
    for loc in locales:
      if loc == default_locale:
        result[loc] = base + clean_path  # No prefix for default
      else:
        result[loc] = base + f'/{loc}' + clean_path  # Prefix for non-default

    return result

  def _get_locale(request: Request) -> str:
    """Determine locale from Accept-Language header when locale is not specified in URL."""
    # If locale is specified for this router, always use it
    if locale is not None:
      return locale

    # 2. Check Accept-Language header
    accept_language = request.headers.get('accept-language', '')
    if accept_language:
      # Parse Accept-Language header (e.g., "en-US,en;q=0.9,ru;q=0.8")
      for lang_spec in accept_language.split(','):
        lang = lang_spec.split(';')[0].strip().split('-')[0]
        if lang in locales:
          return lang

    # 3. Default locale
    return default_locale

  def _make_locale_url_for(request: Request, current_locale: str):
    """Create a locale-aware url_for function.

    Returns a function that generates URLs with correct locale prefix.
    All routes are registered with _{locale} suffix, even for default locale.
    For default locale: /blog/tags (from route blog_tags_en)
    For non-default locale: /ru/blog/tags (from route blog_tags_ru)
    """

    def locale_url_for(name: str, **path_params) -> str:
      # All routes have _{locale} suffix, including default locale
      route_name = f'{name}_{current_locale}'

      # Use FastAPI's url_for to build the URL, then extract the path
      url = request.url_for(route_name, **path_params)
      return url.path

    return locale_url_for

  def _add_i18n_context(request: Request, context: dict) -> dict:
    """Add i18n translator and site-wide SEO context to the template context."""
    # The `seo=` argument is stronger than the schema's `seo` section
    # (TODO 5.9.2); without either there is no `site_name` (5.9.6 behavior).
    effective_seo = resolve_seo_config(seo, frontmatter_schema)
    if effective_seo is not None and effective_seo.site_name:
      context['site_name'] = effective_seo.site_name

    current_locale = _get_locale(request)
    context['t'] = Translator(current_locale)
    context['locale'] = current_locale
    context['available_locales'] = locales
    context['default_locale'] = default_locale

    # Add locale-aware url_for function
    context['locale_url_for'] = _make_locale_url_for(request, current_locale)

    # Add canonical URL and alternate URLs for SEO
    canonical_url = _get_canonical_url(request)
    context['canonical_url'] = canonical_url
    context['alternate_urls'] = _get_alternate_urls(request)

    # Check if current page is canonical (not a duplicate)
    current_url = str(request.url).split('?')[0]  # Remove query string
    context['is_canonical'] = canonical_url == current_url

    if effective_seo is not None:
      page = context.get('page') or {}
      post = context.get('post') or {}
      metadata = page.get('metadata', {}) if isinstance(page, dict) else {}
      document = {**metadata, **post} if isinstance(metadata, dict) else post
      page_type = (
        'article'
        if post
        else 'page'
        if page
        else 'tag'
        if 'tag_id' in context
        else 'tags'
        if 'tags' in context
        else 'list'
        if 'posts' in context
        else 'index'
      )
      body = ''
      if page:
        body = page.get('markdown', '')
      elif post:
        body = post.get('markdown', '') or post.get('content', '')
      request_url = (
        effective_seo.site_url or str(request.base_url).rstrip('/')
      ) + request.url.path
      head = build_head(
        document,
        config=effective_seo,
        request_url=request_url,
        locale=current_locale,
        page_type=page_type,
        body=body,
      )
      context['seo_head'] = head
      context['lang'] = head.get('lang', current_locale)
      if head.get('title'):
        context['title'] = head['title']
      if head.get('description'):
        context['description'] = head['description']
      if head.get('canonical_url'):
        context['canonical_url'] = head['canonical_url']
        # A page whose own `canonical` points elsewhere is a duplicate, and
        # duplicates get no hreflang alternates (TODO 5.9.4).
        if head['canonical_url'].rstrip('/') != request_url.rstrip('/'):
          context['is_canonical'] = False

    return context

  def _list_posts() -> tuple[dict, ...]:
    return helpers.list_posts(
      posts_dirname=posts_dirname, strict=strict, schema=frontmatter_schema
    )

  # Create routes - same paths whether locale is specified or not
  # If locale is specified, these will be mounted at /{locale}/blog
  # If locale is None (legacy), these will be mounted at /blog

  # Add suffix to route names based on locale to avoid conflicts
  name_suffix = f'_{locale}' if locale else ''

  @router.get('/', name=f'blog_index{name_suffix}')
  async def blog_index(request: Request, response_class=HTMLResponse):
    posts = _list_posts()
    recent_3 = posts[:3]

    favorite_posts: list[dict[Any, Any]] = list(
      filter(lambda x: x['slug'] in favorite_post_ids, posts)
    )

    context = _add_i18n_context(
      request, {'recent_3': recent_3, 'favorite_posts': favorite_posts}
    )
    context['title'] = context['t'].blog.recent_writings
    return templates.TemplateResponse(
      request=request, name='index.html', context=context
    )

  @router.get('/posts/{post_id}', name=f'blog_post{name_suffix}')
  async def blog_post(
    post_id: str, request: Request, response_class=HTMLResponse
  ):
    matches = [x for x in _list_posts() if x['slug'] == post_id]
    if not matches:
      raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Post '{post_id}' not found",
      )
    post = dict(matches[0])
    try:
      post_path = store.safe_document_path(
        pathlib.Path(posts_dirname), post_id, pattern=SLUG_RE
      )
    except ValueError as exc:
      raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Post '{post_id}' not found",
      ) from exc
    _, body = store.read_document(post_path)
    post['content'] = helpers.markdown(body, sanitize=sanitize_html)

    context = {
      'post': post,
      'title': post.get('title'),
      'description': post.get('description'),
    }
    return templates.TemplateResponse(
      request=request,
      name='post.html',
      context=_add_i18n_context(request, context),
    )

  @router.get('/posts', name=f'blog_posts{name_suffix}')
  async def blog_posts(request: Request, response_class=HTMLResponse):
    posts = _list_posts()

    context = _add_i18n_context(request, {'posts': posts})
    context['title'] = context['t'].blog.articles
    return templates.TemplateResponse(
      request=request, name='posts.html', context=context
    )

  @router.get('/tags', name=f'blog_tags{name_suffix}')
  async def blog_tags(request: Request, response_class=HTMLResponse):
    posts = _list_posts()

    unsorted_tags: dict = {}
    for post in posts:
      page_tags = post.get('tags', []) or []
      for tag in page_tags:
        if tag in unsorted_tags:
          unsorted_tags[tag] += 1
        else:
          unsorted_tags[tag] = 1

    # Sort by value (number of articles per tag)
    tags: dict = collections.OrderedDict(
      sorted(unsorted_tags.items(), key=lambda x: x[1], reverse=True)
    )

    context = _add_i18n_context(request, {'tags': tags})
    context['title'] = context['t'].blog.tags
    return templates.TemplateResponse(
      request=request, name='tags.html', context=context
    )

  @router.get('/tags/{tag_id}', name=f'blog_tag{name_suffix}')
  async def blog_tag(
    tag_id: str, request: Request, response_class=HTMLResponse
  ):
    posts = [x for x in _list_posts() if tag_id in (x.get('tags') or [])]

    context = _add_i18n_context(request, {'tag_id': tag_id, 'posts': posts})
    context['title'] = f'{context["t"].blog.tags_prefix} {tag_id}'
    return templates.TemplateResponse(
      request=request, name='tag.html', context=context
    )

  if jsonld_routes:
    jsonld_schema = helpers.resolve_schema(strict, frontmatter_schema)
    jsonld_store = store.DocumentStore(
      store.blog_collections(posts_dirname)['posts']
    )

    def _jsonld_context() -> Any:
      """Resolve the schema's context; an unloadable one is a 503, not "ok"."""
      try:
        return jsonld.resolve_context(jsonld_schema)
      except jsonld.JsonLdError as exc:
        raise HTTPException(
          status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    def _jsonld_node(slug: str) -> dict[str, Any] | None:
      try:
        record = jsonld_store.read(slug)
      except (ValueError, FileNotFoundError):
        return None
      return jsonld.document_to_jsonld(
        record.frontmatter,
        schema=jsonld_schema,
        slug=slug,
        collection='posts',
        content=record.body.strip(),
        context=_jsonld_context(),
      )

    # Registered before `/{slug}.jsonld`: Starlette matches routes in
    # registration order, and `index.jsonld` would otherwise also match
    # `/{slug}.jsonld` with `slug='index'` first.
    @router.get('/index.jsonld', name=f'blog_index_jsonld{name_suffix}')
    async def blog_index_jsonld():
      documents = []
      for post in _list_posts():
        record = jsonld_store.read(post['slug'])
        documents.append(
          (post['slug'], record.frontmatter, record.body.strip())
        )
      try:
        graph = jsonld.collection_to_jsonld(
          documents,
          schema=jsonld_schema,
          collection='posts',
          context=_jsonld_context(),
        )
      except jsonld.JsonLdError as exc:
        raise HTTPException(
          status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
      return JSONResponse(content=graph, media_type='application/ld+json')

    @router.get('/{slug}.jsonld', name=f'blog_post_jsonld{name_suffix}')
    async def blog_post_jsonld(slug: str):
      # Only published posts are public (TODO 5.4): `_list_posts()` already
      # filters to published (its `published` default is `True`).
      published_slugs = {post['slug'] for post in _list_posts()}
      if slug not in published_slugs:
        raise HTTPException(
          status_code=status.HTTP_404_NOT_FOUND,
          detail=f"Post '{slug}' not found",
        )
      node = _jsonld_node(slug)
      if node is None:
        raise HTTPException(
          status_code=status.HTTP_404_NOT_FOUND,
          detail=f"Post '{slug}' not found",
        )
      return JSONResponse(content=node, media_type='application/ld+json')

  @router.get('/{page_id}', name=f'blog_page{name_suffix}')
  async def blog_page(
    page_id: str, request: Request, response_class=HTMLResponse
  ):
    def _not_found() -> Any:
      context = _add_i18n_context(request, {})
      context['title'] = context['t'].blog.not_found
      return templates.TemplateResponse(
        request=request,
        name='404.html',
        status_code=404,
        context=context,
      )

    # The same path safety as for posts (TODO 4.1): the slug is validated
    # before it ever becomes a path, a bad one is a 404 like a missing page.
    try:
      path = store.safe_document_path(
        pathlib.Path(pages_dirname), page_id, pattern=SLUG_RE
      )
    except ValueError:
      return _not_found()
    try:
      page: dict[str, str | dict] = helpers.load_content_from_markdown_file(
        path, sanitize=sanitize_html
      )
    except FileNotFoundError:
      return _not_found()
    page['slug'] = page_id
    metadata = page.get('metadata')
    page_title = metadata.get('title') if isinstance(metadata, dict) else None
    page_description = (
      metadata.get('description') if isinstance(metadata, dict) else None
    )

    context = {
      'page': page,
      'title': page_title,
      'description': page_description,
    }
    return templates.TemplateResponse(
      request=request,
      name='page.html',
      context=_add_i18n_context(request, context),
    )

  return router
