"""CRUD operations for markdown files using starlette-admin CustomView."""

import os
import warnings
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from pydantic import ValidationError
from starlette.exceptions import HTTPException
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


def _field_spec_at_path(fields: tuple[Any, ...], path: list[str]) -> Any | None:
  """Resolve a schema field from its external-key path."""
  current = None
  candidates = fields
  for key in path:
    current = next(
      (field for field in candidates if key in (field.key, field.name)), None
    )
    if current is None:
      return None
    candidates = current.fields or ()
  return current


def _value_at_path(source: Any, path: list[Any]) -> Any:
  """Read a nested mapping/list value without mutating it."""
  current = source
  for key in path:
    if isinstance(current, Mapping):
      current = current.get(key)
    elif (
      isinstance(current, list) and isinstance(key, int) and key < len(current)
    ):
      current = current[key]
    else:
      return None
  return current


def _replace_at_path(
  target: dict[str, Any], path: list[Any], value: Any
) -> None:
  """Set one nested mapping/list value on an already copied document."""
  current: Any = target
  for index, key in enumerate(path[:-1]):
    if isinstance(current, dict):
      next_key = path[index + 1]
      expected_type = list if isinstance(next_key, int) else dict
      if not isinstance(current.get(key), expected_type):
        current[key] = expected_type()
      current = current[key]
    elif isinstance(current, list) and isinstance(key, int):
      current = current[key]
    else:
      return
  current[path[-1]] = value


def _filter_transition_choices(
  choices: list[dict[str, Any]],
  field: Any,
  path: list[Any],
  before: Mapping[str, Any] | None,
  *,
  service: DocumentService,
  user: Any,
  slug: str,
  locale: str | None,
  is_new: bool,
) -> None:
  """Disable choices that violate the schema or document transition policy."""
  transitions = field.transitions
  if transitions is None:
    return
  previous = _value_at_path(before or {}, path)
  initial = {str(value) for value in transitions.get('initial', [])}
  for choice in choices:
    value = choice['value']
    if is_new or before is None:
      choice['disabled'] = str(value) not in initial
      continue
    if str(value) == str(previous):
      choice['disabled'] = False
      continue
    rule = next(
      (
        item
        for item in transitions.get('allowed', [])
        if str(item['from']) == str(previous) and str(item['to']) == str(value)
      ),
      None,
    )
    choice['disabled'] = rule is None
    if rule is None:
      continue
    candidate = deepcopy(dict(before))
    _replace_at_path(candidate, path, rule['to'])
    if rule.get('permission') and (
      not service.collection_spec
      or not service.collection_spec.document_authorize
    ):
      choice['disabled'] = True
      continue
    for action in (rule.get('permission'), 'transition'):
      if not action:
        continue
      try:
        service._authorize_document(
          user, action, slug, locale, before, candidate
        )
      except store.OperationNotAllowedError:
        choice['disabled'] = True
        break


def _filter_form_transition_choices(
  form_fields: list[dict[str, Any]],
  schema: FrontmatterSchema,
  before: Mapping[str, Any] | None,
  *,
  service: DocumentService,
  user: Any,
  slug: str,
  locale: str | None,
  is_new: bool,
) -> None:
  """Apply transition-aware choice state to schema-backed controls."""
  for form_field in form_fields:
    path = form_field['path']
    spec = _field_spec_at_path(schema.fields, path)
    if spec is None:
      continue
    _filter_transition_choices(
      form_field['choices'],
      spec,
      path,
      before,
      service=service,
      user=user,
      slug=slug,
      locale=locale,
      is_new=is_new,
    )


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
    *,
    entry_etag: str | None = None,
    locales_present: tuple[str, ...] = (),
    locale: str | None = None,
    fallback_used: bool = False,
  ):
    """Initialize markdown post with slug, frontmatter, content and schema."""
    self.slug = slug
    self.frontmatter = frontmatter
    self.content = content
    self.schema = schema or DEFAULT_SCHEMA
    self.etag = etag
    self.entry_etag = entry_etag
    self.locales_present = locales_present
    self.locale = locale
    self.fallback_used = fallback_used
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
    self._request_collection_spec = (
      collection_spec
      if collection_spec is not None and callable(collection_spec.dir)
      else None
    )
    if self._request_collection_spec is not None:
      collection_spec = replace(self._request_collection_spec, dir=Path.cwd())
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

  def for_request(self, request: Request) -> 'MarkdownFileManager':
    """Return a manager bound to each collection root resolved for a request."""
    if self._request_collection_spec is None and not any(
      callable(spec.dir) for spec in self.collection_specs.values()
    ):
      return self
    collection_spec = self._request_collection_spec
    if collection_spec is not None:
      collection_spec = collection_spec.for_request(request)
    collection_specs = {
      name: spec.for_request(request) if callable(spec.dir) else spec
      for name, spec in self.collection_specs.items()
    }
    if collection_spec is not None:
      collection_specs[collection_spec.name] = collection_spec
    return MarkdownFileManager(
      str(collection_spec.dir)
      if collection_spec is not None
      else str(self.posts_dir),
      self.schema,
      collection_spec=collection_spec,
      collection_specs=collection_specs,
      validators=self.service.validators,
    )

  def list_posts(
    self, locale: str | None = None, user: Any = None
  ) -> list[MarkdownPost]:
    """List canonical entries, displaying the requested locale if enabled."""
    posts = []
    adapter = self.service.i18n_documents
    if adapter is not None:
      target_locale = locale or adapter.config.default_locale
      slugs = [entry.slug for entry in adapter.list()]
    else:
      target_locale = None
      slugs = self.store.list()

    for slug in slugs:
      try:
        post = self.load_post(slug, locale=target_locale, user=user)
        if post:
          posts.append(post)
      except store.OperationNotAllowedError:
        continue
      except Exception as exc:
        print(f'Error loading {slug}: {exc}')

    def get_sort_key(post: MarkdownPost):
      if not post.date:
        return ''
      if isinstance(post.date, datetime):
        return post.date.isoformat()
      return str(post.date)

    posts.sort(key=get_sort_key, reverse=True)
    return posts

  def load_post(
    self, slug: str, *, locale: str | None = None, user: Any = None
  ) -> MarkdownPost | None:
    """Load a canonical document or one localized representation."""
    adapter = self.service.i18n_documents
    if adapter is not None:
      target_locale = locale or adapter.config.default_locale
      if target_locale not in adapter.config.locales:
        raise ValueError(f'Unknown content locale: {target_locale!r}')
      try:
        record = adapter.read(slug, target_locale, fallback=True)
        self.service.authorize_read(
          user, slug, record.locale, record.frontmatter
        )
      except FileNotFoundError:
        return None
      localized_frontmatter = dict(record.frontmatter)
      body = record.body
      if record.locale != adapter.config.default_locale:
        canonical = adapter.read(
          slug, adapter.config.default_locale, fallback=False
        )
        self.service.authorize_read(
          user, slug, canonical.locale, canonical.frontmatter
        )
        for field in self.schema.fields:
          if field.i18n in ('none', 'duplicate'):
            if field.key in canonical.frontmatter:
              localized_frontmatter[field.key] = canonical.frontmatter[
                field.key
              ]
            else:
              localized_frontmatter.pop(field.key, None)
        if not adapter.config.translate_body:
          body = canonical.body
      present = adapter.locales_present(slug)
      return MarkdownPost(
        slug,
        localized_frontmatter,
        body.strip(),
        self.schema,
        record.etag,
        entry_etag=adapter.entry_etag(slug),
        locales_present=present,
        locale=target_locale,
        fallback_used=record.locale != target_locale,
      )

    try:
      ordinary_record = self.store.read(slug)
      self.service.authorize_read(user, slug, None, ordinary_record.frontmatter)
    except FileNotFoundError:
      return None
    except ValueError as exc:
      if self.collection_spec and self.collection_spec.document_authorize:
        raise store.OperationNotAllowedError(
          'Cannot authorize malformed document'
        ) from exc
      path = self.store.path_for(slug) if SLUG_RE.fullmatch(slug) else None
      if path is None:
        return None
      print(f'Error parsing frontmatter for {slug}: {exc}')
      frontmatter: dict[str, Any] = {}
      body = path.read_text(encoding='utf-8')
      return MarkdownPost(slug, frontmatter, body.strip(), self.schema)

    return MarkdownPost(
      slug,
      ordinary_record.frontmatter,
      ordinary_record.body.strip(),
      self.schema,
      ordinary_record.etag,
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

  def link_suggestions(
    self, user: Any = None
  ) -> dict[str, list[dict[str, str]]]:
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

      if target_spec is not None and target_spec.document_authorize is not None:
        # Avoid exposing documents through autocomplete until the target
        # collection can be queried with document-level filtering.
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

    if self.collection_spec and self.collection_spec.document_authorize:
      # Collection-wide findings can mention other documents.
      return []
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
    self._set_principal(request)
    manager = self.manager.for_request(request)
    try:
      data = await request.json()
    except ValueError:
      return JSONResponse({'detail': 'Request body must be valid JSON'}, 400)
    if not isinstance(data, dict):
      return JSONResponse({'detail': 'Request body must be a JSON object'}, 400)

    slug_value = data.get('slug')
    slug = str(slug_value).strip() if slug_value else None
    adapter = manager.service.i18n_documents
    content_locale = data.get('content_locale')
    locale_payloads = data.get('locales')
    if adapter is not None and locale_payloads is not None:
      if not slug:
        return JSONResponse(
          {'detail': 'A canonical slug is required for translations'}, 400
        )
      if not isinstance(locale_payloads, dict) or not locale_payloads:
        return JSONResponse(
          {'detail': 'locales must be a non-empty object'}, 400
        )
      is_new = not adapter.has_entry(slug)
      if is_new and adapter.config.default_locale not in locale_payloads:
        return JSONResponse(
          {'detail': 'Create the canonical locale before adding translations'},
          409,
        )
      await self._require(request, 'create' if is_new else 'update')
      documents: dict[str, tuple[Mapping[str, Any], str]] = {}
      etags: dict[str, str] = {}
      entry_etags: set[str] = set()
      for locale, payload in locale_payloads.items():
        if locale not in adapter.config.locales:
          return JSONResponse(
            {'detail': f'Unknown content locale: {locale}'}, 400
          )
        if not isinstance(payload, dict):
          return JSONResponse(
            {'detail': f'Locale payload for {locale} must be an object'}, 400
          )
        frontmatter = payload.get('frontmatter', {})
        content = payload.get('content', '')
        if not isinstance(frontmatter, dict) or not isinstance(content, str):
          return JSONResponse(
            {
              'detail': f'Locale {locale} requires frontmatter object and content text'
            },
            400,
          )
        locale_path = adapter.path_for(slug, locale)
        etag = payload.get('etag')
        entry_etag = payload.get('entry_etag')
        if not is_new and locale_path.is_file():
          if not etag:
            return JSONResponse(
              {'detail': f'The {locale} edit form is missing its etag; reload'},
              428,
            )
          etags[locale] = str(etag)
        elif not is_new:
          if not entry_etag:
            return JSONResponse(
              {'detail': f'The {locale} form is stale; reload'}, 428
            )
          entry_etags.add(str(entry_etag))
        documents[locale] = (frontmatter, content)
      if len(entry_etags) > 1:
        return JSONResponse(
          {
            'detail': 'Locale drafts were opened against different entry versions'
          },
          409,
        )
      try:
        result = manager.service.save_localized(
          slug,
          documents,
          if_match=etags or None,
          expected_entry_etag=next(iter(entry_etags), None),
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
        {
          'slug': result.slug,
          'status': result.status,
          'locales_present': list(result.locales_present),
          'entry_etag': result.entry_etag,
          'etags': result.etags,
          'issues': [issue.to_dict() for issue in result.issues],
        },
        status_code=201 if result.status == 'created' else 200,
      )
      return response

    if adapter is not None and not content_locale:
      await self._require(request, 'update')
      return JSONResponse({'detail': 'A content locale is required'}, 400)
    if adapter is not None and content_locale:
      if not slug:
        return JSONResponse(
          {'detail': 'A canonical slug is required for a translation'}, 400
        )
      if content_locale not in adapter.config.locales:
        return JSONResponse({'detail': 'Unknown content locale'}, 400)
      is_new = not adapter.has_entry(slug)
      if is_new and content_locale != adapter.config.default_locale:
        return JSONResponse(
          {'detail': 'Create the canonical locale before adding translations'},
          409,
        )
      await self._require(request, 'create' if is_new else 'update')
      frontmatter = data.get('frontmatter', {})
      content = data.get('content', '')
      if not isinstance(frontmatter, dict) or not isinstance(content, str):
        return JSONResponse(
          {'detail': 'frontmatter must be an object and content must be text'},
          400,
        )
      locale_path = adapter.path_for(slug, content_locale)
      etag = data.get('etag')
      entry_etag = data.get('entry_etag')
      if not is_new and locale_path.is_file() and not etag:
        return JSONResponse(
          {'detail': 'The locale edit form is missing its etag; reload'}, 428
        )
      if not is_new and not locale_path.is_file() and not entry_etag:
        return JSONResponse(
          {'detail': 'The entry changed or the form is stale; reload'}, 428
        )
      try:
        result = manager.service.save_localized(
          slug,
          {content_locale: (frontmatter, content)},
          if_match=(
            {content_locale: str(etag)}
            if etag and locale_path.is_file()
            else None
          ),
          expected_entry_etag=(str(entry_etag) if entry_etag else None),
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
        {
          'slug': result.slug,
          'status': result.status,
          'locale': content_locale,
          'locales_present': list(result.locales_present),
          'entry_etag': result.entry_etag,
          'issues': [issue.to_dict() for issue in result.issues],
        },
        status_code=201 if result.status == 'created' else 200,
      )
      response.headers['ETag'] = result.etags[content_locale]
      return response

    is_new = not slug or not manager.store.exists(slug)
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
      result = manager.save_post(
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
    self._set_principal(request)
    manager = self.manager.for_request(request)
    await self._require(request, 'delete')
    slug = str(request.path_params.get('slug', ''))
    if not slug:
      return JSONResponse({'detail': 'A slug is required'}, 400)
    if_match = request.headers.get('if-match')
    if not if_match:
      return JSONResponse({'detail': 'If-Match header is required'}, 428)
    try:
      if manager.service.i18n_documents is not None:
        manager.service.delete_localized_entry(
          slug,
          cascade=request.query_params.get('cascade') == 'true',
          expected_entry_etag=if_match,
          user=getattr(request.state, 'blog_user', None),
        )
      else:
        manager.service.delete(
          slug,
          if_match=if_match,
          user=getattr(request.state, 'blog_user', None),
        )
    except store.ConflictError as exc:
      return JSONResponse({'detail': str(exc)}, exc.status_code)
    except store.OperationNotAllowedError as exc:
      return JSONResponse({'detail': str(exc)}, 403)
    except ValueError as exc:
      return JSONResponse({'detail': str(exc)}, 409)
    except (FileNotFoundError, store.NotFoundError) as exc:
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
    translations_dir: str | None = None,
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
    self.translations_dir = translations_dir

  @route('')
  async def index(self, request: Request) -> Response:
    """Render list of posts."""
    await self._require(request, 'read')
    manager = self.manager.for_request(request)
    adapter = manager.service.i18n_documents
    content_locale = None
    locale_options: tuple[str, ...] = ()
    if adapter is not None:
      content_locale = request.query_params.get('content_locale') or (
        self.locale
        if self.locale in adapter.config.locales
        else adapter.config.default_locale
      )
      if content_locale not in adapter.config.locales:
        return JSONResponse({'detail': 'Unknown content locale'}, 400)
      locale_options = adapter.config.locales
    posts = manager.list_posts(
      locale=content_locale, user=getattr(request.state, 'blog_user', None)
    )

    # Convert to dict for template
    posts_data = [
      {
        'slug': p.slug,
        'etag': p.entry_etag or p.etag or '',
        'locales_present': p.locales_present,
        'fallback_used': p.fallback_used,
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
    search_query = getattr(request, 'query_params', {}).get('q', '').strip()
    if search_query:
      search_term = search_query.casefold()
      posts_data = [
        post
        for post in posts_data
        if any(
          search_term in str(post[field]).casefold()
          for field in ('title', 'slug', 'summary', 'tags')
        )
      ]

    from ..i18n import load_translations

    translations = load_translations(self.locale, self.translations_dir)
    post_t = translations.get('post', {})
    nav_t = translations.get('nav', {})
    home_t = translations.get('home', {})
    list_t = translations.get('post_list', {})
    actions_t = translations.get('action', {})
    messages_t = translations.get('message', {})
    t = {
      'posts': nav_t.get('posts', post_t.get('posts', 'Posts')),
      'admin': post_t.get('admin', 'Admin'),
      'new_post': home_t.get('new_post', post_t.get('create_new', 'New Post')),
      'title': post_t.get('title', 'Title'),
      'slug': post_t.get('slug', 'Slug'),
      'date': post_t.get('date', 'Date'),
      'status': list_t.get('status', 'Status'),
      'tags': post_t.get('tags', 'Tags'),
      'actions': list_t.get('actions', 'Actions'),
      'published': post_t.get('published', 'Published'),
      'draft': list_t.get('draft', 'Draft'),
      'edit': actions_t.get('edit', 'Edit'),
      'delete': actions_t.get('delete', 'Delete'),
      'no_posts_found': list_t.get('no_posts_found', 'No posts found'),
      'create_first_post': home_t.get(
        'create_first_post', 'Create your first post'
      ),
      'delete_confirm': list_t.get('delete_confirm', 'Delete this post?'),
      'delete_translations_confirm': list_t.get(
        'delete_translations_confirm',
        'Delete all translations of this post too?',
      ),
      'error': messages_t.get('error', 'Error'),
      'failed_to_delete': list_t.get(
        'failed_to_delete', 'Failed to delete post'
      ),
      'search': actions_t.get('search', 'Search'),
    }

    # starlette-admin assigns templates at mount time.
    assert self.templates is not None  # nosec B101
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
        'locale_options': locale_options,
        'content_locale': content_locale,
        'search_query': search_query,
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
    translations_dir: str | None = None,
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
    self.translations_dir = translations_dir

  @route('')
  async def index(self, request: Request) -> Response:
    """Render edit form."""
    await self._require(request, 'update')
    manager = self.manager.for_request(request)
    # starlette-admin assigns templates at mount time.
    assert self.templates is not None  # nosec B101
    slug = request.path_params.get('slug')
    if not slug:
      return self.templates.TemplateResponse(
        request=request,
        name='error.html',
        context={'error': 'Missing slug parameter'},
        status_code=400,
      )
    adapter = manager.service.i18n_documents
    content_locale = None
    locale_tabs = []
    locale_exists = True
    if adapter is not None:
      requested_locale = request.query_params.get('content_locale')
      content_locale = requested_locale or (
        self.locale
        if self.locale in adapter.config.locales
        else adapter.config.default_locale
      )
      if content_locale not in adapter.config.locales:
        return self.templates.TemplateResponse(
          request=request,
          name='error.html',
          context={'error': f'Unknown content locale: {content_locale}'},
          status_code=400,
        )
      locale_exists = content_locale in adapter.locales_present(slug)
      locale_tabs = [
        {
          'locale': item,
          'present': item in adapter.locales_present(slug),
          'active': item == content_locale,
          'url': f'{request.url.path}?content_locale={quote(item)}',
        }
        for item in adapter.config.locales
      ]
    try:
      post = manager.load_post(
        slug,
        locale=content_locale,
        user=getattr(request.state, 'blog_user', None),
      )
    except store.OperationNotAllowedError as exc:
      raise HTTPException(status_code=403, detail=str(exc)) from exc

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

    translations = load_translations(self.locale, self.translations_dir)
    t = translations['post']

    display_schema = self.schema
    if adapter is not None and content_locale != adapter.config.default_locale:

      def relax_required(fields):
        return tuple(
          replace(
            field,
            required=(
              field.required
              if adapter.config.required_in_translations
              else False
            ),
            read_only=field.read_only or field.i18n in ('none', 'duplicate'),
            fields=(
              relax_required(field.fields) if field.fields is not None else None
            ),
          )
          for field in fields
        )

      display_schema = replace(
        self.schema, fields=relax_required(self.schema.fields)
      )
    form_fields = build_form_fields(
      display_schema,
      post.frontmatter,
      t,
      link_choices=manager.link_suggestions(
        user=getattr(request.state, 'blog_user', None)
      ),
      locale=self.locale,
      default_locale=(
        adapter.config.default_locale if adapter is not None else self.locale
      ),
    )

    for form_field in form_fields:
      field_spec = _field_spec_at_path(self.schema.fields, form_field['path'])
      form_field['shared'] = bool(
        adapter is not None
        and content_locale != adapter.config.default_locale
        and field_spec is not None
        and field_spec.i18n in ('none', 'duplicate')
      )
    _filter_form_transition_choices(
      form_fields,
      self.schema,
      post.frontmatter,
      service=manager.service,
      user=getattr(request.state, 'blog_user', None),
      slug=post.slug,
      locale=content_locale,
      is_new=not locale_exists,
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
          'entry_etag': post.entry_etag or '',
        },
        'content_locale': content_locale,
        'locale_tabs': locale_tabs,
        'locale_exists': locale_exists,
        'fallback_used': post.fallback_used,
        'canonical_post': manager.load_post(
          slug,
          locale=adapter.config.default_locale,
          user=getattr(request.state, 'blog_user', None),
        )
        if adapter is not None
        and content_locale != adapter.config.default_locale
        else None,
        'canonical_url': f'{request.url.path}?content_locale={quote(adapter.config.default_locale)}'
        if adapter is not None
        else '',
        'body_read_only': bool(
          adapter is not None
          and content_locale != adapter.config.default_locale
          and not adapter.config.translate_body
        ),
        'form_fields': form_fields,
        'form_fields_meta': form_fields_meta(form_fields),
        'diagnostics': manager.diagnostics_for_post(slug),
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
    translations_dir: str | None = None,
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
    self.translations_dir = translations_dir

  @route('')
  async def index(self, request: Request) -> Response:
    """Render create form."""
    await self._require(request, 'create')
    manager = self.manager.for_request(request)
    # starlette-admin assigns templates at mount time.
    assert self.templates is not None  # nosec B101
    # Get translations for this view's locale
    from ..i18n import load_translations

    translations = load_translations(self.locale, self.translations_dir)
    t = translations['post']

    adapter = manager.service.i18n_documents
    content_locale = (
      adapter.config.default_locale if adapter is not None else None
    )
    form_fields = build_form_fields(
      self.schema,
      {},
      t,
      is_new=True,
      link_choices=manager.link_suggestions(
        user=getattr(request.state, 'blog_user', None)
      ),
      locale=self.locale,
      default_locale=(
        adapter.config.default_locale if adapter is not None else self.locale
      ),
    )

    _filter_form_transition_choices(
      form_fields,
      self.schema,
      None,
      service=manager.service,
      user=getattr(request.state, 'blog_user', None),
      slug='',
      locale=content_locale,
      is_new=True,
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
          'entry_etag': '',
        },
        'content_locale': content_locale,
        'locale_tabs': [],
        'locale_exists': False,
        'fallback_used': False,
        'form_fields': form_fields,
        'form_fields_meta': form_fields_meta(form_fields),
        'is_new': True,
        'auto_slug': bool(
          adapter is None
          and self.collection_spec is not None
          and self.collection_spec.slug_template is not None
        ),
        'base_url': request.scope['root_path'],
        't': t,
      },
    )
