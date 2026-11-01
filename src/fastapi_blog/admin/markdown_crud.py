"""CRUD operations for markdown files using starlette-admin CustomView."""

import os
import warnings
from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette_admin.routing import route
from starlette_admin.views import CustomView

from .. import helpers, store
from ..config import CollectionSpec
from ..models import DEFAULT_SCHEMA, SLUG_RE, FrontmatterSchema
from ..permissions import (
  Authorizer,
  default_authorize,
  ensure_allowed,
  user_from_session,
)
from ..service import BlockingValidationError, DocumentService
from ..validators import Validator
from .form_fields import (
  build_form_fields,
  form_fields_meta,
  get_field_value,
)


# Simple identity function - labels will be set dynamically per locale
def _(message: str) -> str:
  """Return the message unchanged; locale labels are set by the admin."""
  return message


def get_posts_directory(posts_dirname: str | None = None) -> str:
  """Get the posts directory: `posts_dirname`, else `POSTS_DIR`, else a guess.

  Args:
    posts_dirname: The directory to use, normally the same `posts_dirname`
      passed to `setup_fastapi_blog`/`add_blog_to_fastapi`, so the admin
      panel and the blog/REST API always agree on where posts live.

  Returns:
    Path to posts directory as string

  """
  if posts_dirname is not None:
    return posts_dirname

  posts_dir_env = os.getenv('POSTS_DIR')
  if posts_dir_env:
    warnings.warn(
      'The POSTS_DIR environment variable is deprecated (TODO.md, 4.6): '
      "pass posts_dirname='...' to setup_fastapi_blog()/add_admin_to_app() "
      'instead, so the admin panel and the blog/REST API always agree on '
      'where posts live.',
      DeprecationWarning,
      stacklevel=2,
    )
    return posts_dir_env

  # Try to find posts directory relative to the app
  backend_dir = (
    Path.cwd() / 'backend' if (Path.cwd() / 'backend').exists() else Path.cwd()
  )
  return str(backend_dir / 'posts')


class MarkdownPost:
  """Represents a markdown post with frontmatter.

  `title`, `date`, `published` and `tags` are read from the fields that have
  the matching role in the schema, whatever those fields are called.
  """

  def __init__(
    self,
    slug: str,
    frontmatter: dict[str, Any],
    content: str,
    schema: FrontmatterSchema | None = None,
    etag: str | None = None,
  ):
    """Initialize markdown post with slug, frontmatter, content and schema."""
    self.slug = slug
    self.frontmatter = frontmatter
    self.content = content
    self.schema = schema or DEFAULT_SCHEMA
    self.etag = etag
    self.title = self._role_value('title', slug)
    self.date = self._role_value('date', '')
    self.published = bool(self._role_value('published', False))
    self.tags = self._role_value('tags', [])

  def _role_value(self, role: str, default: Any) -> Any:
    spec = self.schema.field_for_role(role)
    return get_field_value(self.frontmatter, spec, default)


class MarkdownFileManager:
  """Manager for reading/writing markdown files, backed by a `DocumentStore`.

  The one place the admin panel turns a slug into a file (see TODO 4.1):
  everything here goes through `self.store` rather than building paths by
  hand, so slug/path safety is enforced in exactly one place.
  """

  def __init__(
    self,
    posts_dir: str = 'posts',
    schema: FrontmatterSchema | None = None,
    collection_spec: CollectionSpec | None = None,
    collection_specs: Mapping[str, CollectionSpec] | None = None,
    validators: tuple[Validator, ...] = (),
  ):
    """Initialize file manager with posts directory and frontmatter schema."""
    self.posts_dir = Path(posts_dir)
    self.schema = (
      schema
      or (collection_spec.schema if collection_spec else None)
      or DEFAULT_SCHEMA
    )
    self.collection_spec = (
      replace(collection_spec, schema=self.schema)
      if collection_spec is not None
      else None
    )
    self.store = store.DocumentStore(
      collection_spec.to_collection()
      if collection_spec is not None
      else store.blog_collections(self.posts_dir)['posts']
    )
    self.collection_specs = dict(collection_specs or {})
    if collection_spec is not None:
      self.collection_specs.setdefault(collection_spec.name, collection_spec)
    self.service = DocumentService(
      self.store,
      self.schema,
      collection_spec=collection_spec,
      validators=validators,
    )

  def list_posts(self) -> list[MarkdownPost]:
    """List all markdown posts."""
    posts = []
    for slug in self.store.list():
      try:
        post = self.load_post(slug)
        if post:
          posts.append(post)
      except Exception as e:
        print(f'Error loading {slug}: {e}')

    # Sort by date descending (handle both datetime and string)
    def get_sort_key(p):
      if not p.date:
        return ''
      # Convert datetime to string for consistent comparison
      if isinstance(p.date, datetime):
        return p.date.isoformat()
      return str(p.date)

    posts.sort(key=get_sort_key, reverse=True)
    return posts

  def load_post(self, slug: str) -> MarkdownPost | None:
    """Load a single post by slug."""
    try:
      record = self.store.read(slug)
    except FileNotFoundError:
      return None
    except ValueError as e:
      # Invalid slug: no such post. Malformed YAML frontmatter on an
      # otherwise valid file: degrade gracefully (one broken post shouldn't
      # break the whole admin listing) by treating the file as plain body.
      path = self.store.path_for(slug) if SLUG_RE.fullmatch(slug) else None
      if path is None:
        return None
      print(f'Error parsing frontmatter for {slug}: {e}')
      frontmatter: dict[str, Any] = {}
      body = path.read_text(encoding='utf-8')
      return MarkdownPost(slug, frontmatter, body.strip(), self.schema)

    return MarkdownPost(
      slug, record.frontmatter, record.body.strip(), self.schema, record.etag
    )

  def save_post(
    self,
    slug: str | None,
    frontmatter: dict[str, Any],
    content: str,
    *,
    if_match: str | None = None,
    expected_exists: bool | None = None,
    user: Any = None,
  ):
    """Save a post through the shared schema-aware document service."""
    return self.service.save(
      slug,
      frontmatter,
      content,
      if_match=if_match,
      expected_exists=expected_exists,
      user=user,
    )

  def link_suggestions(self) -> dict[str, list[dict[str, str]]]:
    """Build filtered autocomplete options for link fields in the schema."""
    if self.schema is None:
      return {}
    suggestions: dict[str, list[dict[str, str]]] = {}

    def link_fields(fields, parents=()):
      for field in fields:
        if field.is_link:
          yield parents, field
        if field.type in ('object', 'list[object]'):
          yield from link_fields(field.fields or (), (*parents, field))

    for parents, field in link_fields(self.schema.fields):
      if not field.is_link:
        continue
      target_name = field.collection or (
        self.collection_spec.name if self.collection_spec else 'posts'
      )
      target_spec = self.collection_specs.get(target_name)
      if target_spec is not None:
        target_store = store.DocumentStore(target_spec.to_collection())
        target_schema = target_spec.schema or DEFAULT_SCHEMA
      elif target_name == (
        self.collection_spec.name
        if self.collection_spec is not None
        else 'posts'
      ):
        target_store = self.store
        target_schema = self.schema
      else:
        continue

      value_field = None
      if field.value_field:
        value_field = target_schema.get(field.value_field)
        if value_field is None:
          value_field = next(
            (
              item
              for item in target_schema.fields
              if item.key == field.value_field
            ),
            None,
          )
      else:
        value_field = next(
          (item for item in target_schema.fields if item.key == '@id'), None
        )
      title_field = target_schema.field_for_role('title')
      options: list[dict[str, str]] = []
      for slug in sorted(target_store.list()):
        try:
          frontmatter = target_store.read(slug).frontmatter
        except (store.ParseError, store.NotFoundError):
          continue
        matches = True
        for rule in field.filters or ():
          filter_spec = target_schema.get(rule['field'])
          if filter_spec is None:
            filter_spec = next(
              (
                item
                for item in target_schema.fields
                if item.key == rule['field']
              ),
              None,
            )
          filter_key = filter_spec.key if filter_spec else rule['field']
          filter_value = frontmatter.get(filter_key)
          allowed_values = rule['values']
          if isinstance(filter_value, list):
            matches = any(value in allowed_values for value in filter_value)
          else:
            matches = filter_value in allowed_values
          if not matches:
            break
        if not matches:
          continue
        value = frontmatter.get(value_field.key) if value_field else slug
        if value is None:
          continue
        title = frontmatter.get(title_field.key) if title_field else None
        options.append(
          {
            'value': str(value),
            'label': f'{title} ({slug})' if title else slug,
          }
        )
      name = '__'.join([parent.name for parent in parents] + [field.name])
      suggestions[name] = options
    return suggestions

  def diagnostics_for_post(self, slug: str) -> list[dict[str, Any]]:
    """Return collection check findings that apply to one existing document."""
    from ..checks import check_collection

    spec = self.collection_spec or CollectionSpec(
      self.store.collection.name, self.posts_dir, schema=self.schema
    )
    spec = replace(spec, schema=self.schema, validators=())
    collections = dict(self.collection_specs)
    collections[spec.name] = spec
    report = check_collection(
      spec,
      root=Path.cwd(),
      collections=collections,
    )
    return [
      issue.to_dict() for issue in report.issues if issue.slug in (None, slug)
    ]

  def delete_post(self, slug: str) -> bool:
    """Delete a post."""
    try:
      self.service.delete(slug)
    except (ValueError, FileNotFoundError):
      return False
    return True


class _AuthorizedMarkdownView:
  """Shared asynchronous access checks for the file-backed admin views."""

  authorize: Authorizer

  def _set_principal(self, request: Request) -> None:
    if getattr(request.state, 'blog_user', None) is None:
      request.state.blog_user = user_from_session(request)

  async def _require(self, request: Request, action: str) -> None:
    self._set_principal(request)
    await ensure_allowed(self.authorize, request, 'posts', action)


class MarkdownSaveView(_AuthorizedMarkdownView, CustomView):
  """Handle schema-validated Markdown saves inside the admin application."""

  def __init__(
    self,
    manager: MarkdownFileManager,
    authorize: Authorizer | None = None,
    *,
    sanitize_html: bool = True,
  ):
    """Wire the save endpoint to the file manager and the policy."""
    super().__init__(
      menu_label=_('Save Post'),
      path='/posts/save',
      route_name='posts:save',
      add_to_menu=False,
    )
    self.manager = manager
    self.authorize = authorize or default_authorize
    self.sanitize_html = sanitize_html

  @route('/preview', methods=['POST'])
  async def preview(self, request: Request) -> HTMLResponse:
    """Render Markdown through the public renderer and sanitizer."""
    await self._require(request, 'read')
    try:
      data = await request.json()
    except ValueError:
      return HTMLResponse('Request body must be valid JSON', 400)
    if not isinstance(data, dict) or not isinstance(data.get('content'), str):
      return HTMLResponse('content must be text', 400)
    return HTMLResponse(
      helpers.markdown(data['content'], sanitize=self.sanitize_html)
    )

  @route('', methods=['POST'])
  async def save(self, request: Request) -> JSONResponse:
    """Validate and persist a form submission without calling the REST API."""
    try:
      data = await request.json()
    except ValueError:
      return JSONResponse({'detail': 'Request body must be valid JSON'}, 400)
    if not isinstance(data, dict):
      return JSONResponse({'detail': 'Request body must be a JSON object'}, 400)

    slug_value = data.get('slug')
    slug = str(slug_value).strip() if slug_value else None
    is_new = not slug or not self.manager.store.exists(slug)
    action = 'create' if is_new else 'update'
    await self._require(request, action)

    frontmatter = data.get('frontmatter', {})
    content = data.get('content', '')
    if not isinstance(frontmatter, dict) or not isinstance(content, str):
      return JSONResponse(
        {'detail': 'frontmatter must be an object and content must be text'},
        400,
      )
    etag = data.get('etag')
    if not is_new and not etag:
      return JSONResponse(
        {'detail': 'The edit form is missing its etag; reload before saving'},
        428,
      )

    try:
      result = self.manager.save_post(
        slug,
        frontmatter,
        content,
        if_match=str(etag) if etag else None,
        expected_exists=not is_new,
        user=getattr(request.state, 'blog_user', None),
      )
    except BlockingValidationError as exc:
      return JSONResponse(
        {'detail': {'issues': [issue.to_dict() for issue in exc.issues]}}, 422
      )
    except ValidationError as exc:
      return JSONResponse({'detail': str(exc)}, 422)
    except store.ConflictError as exc:
      return JSONResponse({'detail': str(exc)}, exc.status_code)
    except store.OperationNotAllowedError as exc:
      return JSONResponse({'detail': str(exc)}, 403)
    except (ValueError, OSError, store.NotFoundError) as exc:
      return JSONResponse({'detail': str(exc)}, 400)

    response = JSONResponse(
      {'slug': result.slug, 'status': result.status},
      status_code=201 if result.status == 'created' else 200,
    )
    response.headers['ETag'] = result.etag
    return response

  @route('/{slug}', methods=['DELETE'])
  async def delete(self, request: Request) -> JSONResponse:
    """Delete a document through the same service used for form saves."""
    await self._require(request, 'delete')
    slug = str(request.path_params.get('slug', ''))
    if not slug:
      return JSONResponse({'detail': 'A slug is required'}, 400)
    if_match = request.headers.get('if-match')
    if not if_match:
      return JSONResponse({'detail': 'If-Match header is required'}, 428)
    try:
      self.manager.service.delete(
        slug,
        if_match=if_match,
        user=getattr(request.state, 'blog_user', None),
      )
    except store.ConflictError as exc:
      return JSONResponse({'detail': str(exc)}, exc.status_code)
    except store.OperationNotAllowedError as exc:
      return JSONResponse({'detail': str(exc)}, 403)
    except (ValueError, FileNotFoundError, store.NotFoundError) as exc:
      return JSONResponse({'detail': str(exc)}, 404)
    return JSONResponse({'slug': slug, 'status': 'deleted'}, 200)


class MarkdownListView(_AuthorizedMarkdownView, CustomView):
  """List view for markdown posts."""

  def __init__(
    self,
    posts_dir: str = 'posts',
    locale: str = 'en',
    schema: FrontmatterSchema | None = None,
    collection_spec: CollectionSpec | None = None,
    authorize: Authorizer | None = None,
    collection_specs: Mapping[str, CollectionSpec] | None = None,
    validators: tuple[Validator, ...] = (),
  ):
    """Initialize list view with posts directory, locale and schema."""
    super().__init__(
      menu_label=_('Posts'),
      icon='fa fa-file-text',
      path='/posts',
      route_name='posts:list',
    )
    self.schema = (
      schema
      or (collection_spec.schema if collection_spec else None)
      or DEFAULT_SCHEMA
    )
    self.collection_spec = (
      replace(collection_spec, schema=self.schema)
      if collection_spec is not None
      else None
    )
    self.manager = MarkdownFileManager(
      posts_dir,
      self.schema,
      collection_spec,
      collection_specs=collection_specs,
      validators=validators,
    )
    self.locale = locale
    self.authorize = authorize or default_authorize

  @route('')
  async def index(self, request: Request) -> Response:
    """Render list of posts."""
    await self._require(request, 'read')
    posts = self.manager.list_posts()

    # Convert to dict for template
    posts_data = [
      {
        'slug': p.slug,
        'etag': p.etag or '',
        'title': p.title,
        'summary': (
          self.collection_spec.summarize(p.slug, p.frontmatter)
          if self.collection_spec is not None
          else p.title
        ),
        'date': self._format_date(p.date),
        'published': p.published,
        'tags': ', '.join(p.tags)
        if isinstance(p.tags, list)
        else str(p.tags)
        if p.tags
        else '',
      }
      for p in posts
    ]

    # Use locale from instance (set during initialization)
    locale = self.locale

    # Translations dictionary
    translations = {
      'ru': {
        'posts': 'Посты',
        'admin': 'Админ',
        'new_post': 'Новый пост',
        'title': 'Заголовок',
        'slug': 'URL',
        'date': 'Дата',
        'status': 'Статус',
        'tags': 'Теги',
        'actions': 'Действия',
        'published': 'Опубликовано',
        'draft': 'Черновик',
        'edit': 'Редактировать',
        'delete': 'Удалить',
        'no_posts_found': 'Посты не найдены.',
        'create_first_post': 'Создайте свой первый пост',
        'delete_confirm': 'Удалить пост',
        'error': 'Ошибка',
        'failed_to_delete': 'Не удалось удалить',
      },
      'en': {
        'posts': 'Posts',
        'admin': 'Admin',
        'new_post': 'New Post',
        'title': 'Title',
        'slug': 'Slug',
        'date': 'Date',
        'status': 'Status',
        'tags': 'Tags',
        'actions': 'Actions',
        'published': 'Published',
        'draft': 'Draft',
        'edit': 'Edit',
        'delete': 'Delete',
        'no_posts_found': 'No posts found.',
        'create_first_post': 'Create your first post',
        'delete_confirm': 'Delete post',
        'error': 'Error',
        'failed_to_delete': 'Failed to delete',
      },
    }

    # Get translations for current locale (default to English)
    t = translations.get(locale, translations['en'])

    assert self.templates is not None
    return self.templates.TemplateResponse(
      request=request,
      name='markdown_list.html',
      context={
        'title': self.title(request),
        'posts': posts_data,
        'columns': {
          'date': self.schema.field_for_role('date') is not None,
          'published': self.schema.field_for_role('published') is not None,
          'tags': self.schema.field_for_role('tags') is not None,
        },
        'base_url': request.scope['root_path'],
        't': t,  # Add translations
      },
    )

  def _format_date(self, date_value) -> str:
    """Format date for display."""
    if not date_value:
      return ''
    if isinstance(date_value, datetime):
      return date_value.strftime('%Y-%m-%d')
    return str(date_value)


class MarkdownEditView(_AuthorizedMarkdownView, CustomView):
  """Edit view for markdown posts."""

  def __init__(
    self,
    posts_dir: str = 'posts',
    locale: str = 'en',
    schema: FrontmatterSchema | None = None,
    collection_spec: CollectionSpec | None = None,
    authorize: Authorizer | None = None,
    collection_specs: Mapping[str, CollectionSpec] | None = None,
    validators: tuple[Validator, ...] = (),
  ):
    """Initialize edit view with posts directory, locale and schema."""
    super().__init__(
      menu_label=_('Edit Post'),
      path='/posts/edit/{slug}',
      route_name='posts:edit',
      add_to_menu=False,  # Don't show in menu
    )
    self.schema = (
      schema
      or (collection_spec.schema if collection_spec else None)
      or DEFAULT_SCHEMA
    )
    self.manager = MarkdownFileManager(
      posts_dir,
      self.schema,
      collection_spec,
      collection_specs=collection_specs,
      validators=validators,
    )
    self.locale = locale
    self.authorize = authorize or default_authorize

  @route('')
  async def index(self, request: Request) -> Response:
    """Render edit form."""
    await self._require(request, 'update')
    assert self.templates is not None
    slug = request.path_params.get('slug')
    if not slug:
      return self.templates.TemplateResponse(
        request=request,
        name='error.html',
        context={'error': 'Missing slug parameter'},
        status_code=400,
      )
    post = self.manager.load_post(slug)

    if not post:
      return self.templates.TemplateResponse(
        request=request,
        name='admin/404.html',
        context={
          'title': 'Post not found',
          'message': f'Post "{slug}" not found',
        },
        status_code=404,
      )

    # Get translations for this view's locale
    from ..i18n import load_translations

    translations = load_translations(self.locale)
    t = translations['post']

    form_fields = build_form_fields(
      self.schema,
      post.frontmatter,
      t,
      link_choices=self.manager.link_suggestions(),
    )

    return self.templates.TemplateResponse(
      request=request,
      name='markdown_edit.html',
      context={
        'title': f'{t["edit_title"]}: {post.title}',
        'post': {
          'slug': post.slug,
          'title': post.title,
          'content': post.content,
          'frontmatter': post.frontmatter,
          'etag': post.etag or '',
        },
        'form_fields': form_fields,
        'form_fields_meta': form_fields_meta(form_fields),
        'diagnostics': self.manager.diagnostics_for_post(slug),
        'is_new': False,
        'auto_slug': False,
        'base_url': request.scope['root_path'],
        't': t,
      },
    )


class MarkdownCreateView(_AuthorizedMarkdownView, CustomView):
  """Create view for new markdown posts."""

  def __init__(
    self,
    posts_dir: str = 'posts',
    locale: str = 'en',
    schema: FrontmatterSchema | None = None,
    collection_spec: CollectionSpec | None = None,
    authorize: Authorizer | None = None,
    collection_specs: Mapping[str, CollectionSpec] | None = None,
    validators: tuple[Validator, ...] = (),
  ):
    """Initialize create view with posts directory, locale and schema."""
    super().__init__(
      menu_label=_('New Post'),
      path='/posts/new',
      route_name='posts:new',
      add_to_menu=False,
    )
    self.schema = (
      schema
      or (collection_spec.schema if collection_spec else None)
      or DEFAULT_SCHEMA
    )
    self.collection_spec = (
      replace(collection_spec, schema=self.schema)
      if collection_spec is not None
      else None
    )
    self.manager = MarkdownFileManager(
      posts_dir,
      self.schema,
      collection_spec,
      collection_specs=collection_specs,
      validators=validators,
    )
    self.locale = locale
    self.authorize = authorize or default_authorize

  @route('')
  async def index(self, request: Request) -> Response:
    """Render create form."""
    await self._require(request, 'create')
    assert self.templates is not None
    # Get translations for this view's locale
    from ..i18n import load_translations

    translations = load_translations(self.locale)
    t = translations['post']

    form_fields = build_form_fields(
      self.schema,
      {},
      t,
      is_new=True,
      link_choices=self.manager.link_suggestions(),
    )

    return self.templates.TemplateResponse(
      request=request,
      name='markdown_edit.html',
      context={
        'title': t['create_new'],
        'post': {
          'slug': '',
          'title': '',
          'content': '',
          'frontmatter': {},
          'etag': '',
        },
        'form_fields': form_fields,
        'form_fields_meta': form_fields_meta(form_fields),
        'is_new': True,
        'auto_slug': bool(
          self.collection_spec is not None
          and self.collection_spec.slug_template is not None
        ),
        'base_url': request.scope['root_path'],
        't': t,
      },
    )
