import pathlib
import re
import warnings
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import jinja2
from fastapi import (
  APIRouter,
  Depends,
  FastAPI,
  Header,
  HTTPException,
  Path,
  Request,
  Response,
  status,
)
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from . import helpers, store
from .auth import add_startup_check, check_api_auth_config
from .config import CollectionSpec
from .models import (
  SLUG_PATTERN,
  SLUG_RE,
  FrontmatterSchema,
  payload_model,
)
from .permissions import (
  ADMIN,
  Authorizer,
  default_authorize,
  ensure_allowed,
  user_from_session,
)
from .security import install_origin_check_middleware
from .validators import Validator, run_blocking


def _event_actor(user: Any) -> Any:
  """Return a stable, non-sensitive actor identifier for change events."""
  if isinstance(user, dict):
    return user.get('username') or user.get('id')
  return user


async def require_authentication(request: Request) -> dict:
  """Require authentication via session cookie.

  This function is part of fastapi-blog and only checks session-based
  authentication (needs a `SessionMiddleware`, for example the one added by
  the `admin` extra).

  For any other scheme, pass your own dependency as `auth_dependency` to
  `get_api_router()`.

  Returns:
      dict with user info if authenticated

  Raises:
      HTTPException 401 if not authenticated

  """
  # Check session cookie (set by the admin panel or any SessionMiddleware)
  # Only check session if SessionMiddleware is installed
  session_user = user_from_session(request)
  if session_user:
    return session_user

  # No valid session found
  raise HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail='Authentication required. Please login via admin panel.',
    headers={'WWW-Authenticate': 'Session'},
  )


async def optional_authentication(request: Request) -> dict | None:
  """Return user info if authenticated, None otherwise.

  This is used when require_auth=False (e.g., in tests).
  Does NOT raise 401, just returns None.

  Returns:
      dict with user info if authenticated, None otherwise

  """
  # Check if session exists (SessionMiddleware installed)
  return user_from_session(request)


def _post_path(slug: str, posts_dirname: str) -> pathlib.Path:
  try:
    return store.safe_document_path(
      pathlib.Path(posts_dirname), slug, pattern=SLUG_RE
    )
  except ValueError as exc:
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail=(
        'Invalid slug. Allowed: lowercase letters, digits, hyphens (max 100).'
      ),
    ) from exc


def _frontmatter_dump(
  payload: Any,
  schema: FrontmatterSchema | None = None,
  *,
  is_create: bool = True,
  existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
  if schema is None:
    return payload.frontmatter.model_dump(exclude_none=True)
  # Write the keys other services expect (aliases), not internal names;
  # fills `on_create` fields and enforces `read_only` ones (see 4.5).
  try:
    return schema.dump_for_write(
      payload.frontmatter, is_create=is_create, existing=existing
    )
  except ValueError as exc:
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
    ) from exc


def _body(payload: Any) -> str:
  # `payload` is an instance of the dynamically built `Payload` model
  # (`payload_model()`), which mypy can't see `.content` on statically.
  return f'\n{payload.content.rstrip()}\n'


def _parse_file(path: pathlib.Path) -> dict[str, Any]:
  try:
    frontmatter, content = store.read_document(path)
  except ValueError as exc:
    raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail=f'{path.name}: {exc}',
    ) from exc
  return {'frontmatter': frontmatter, 'content': content.lstrip('\n')}


def get_api_router(
  posts_dirname: str = 'posts',
  strict: bool = True,
  require_auth: bool = True,
  admin_username: str | None = None,
  admin_password: str | None = None,
  frontmatter_schema: FrontmatterSchema | None = None,
  auth_dependency: Callable[..., Any] | None = None,
  require_if_match: bool = False,
  validators: tuple[Validator, ...] = (),
  collection_spec: CollectionSpec | None = None,
  authorize: Authorizer | None = None,
) -> APIRouter:
  """Get REST API router for post management.

  This function returns a configured APIRouter that can be included in any
  FastAPI application. It provides REST API endpoints for CRUD operations
  on markdown posts.

  Args:
      posts_dirname: Directory containing markdown posts (default: 'posts')
      strict: Use strict frontmatter validation (default: True)
      require_auth: Require authentication for all endpoints (default: True)
      admin_username: Admin username for unified auth (optional)
      admin_password: Admin password for unified auth (optional)
      frontmatter_schema: Custom frontmatter schema (optional). Requests are
          validated with it and posts are written with its keys (aliases).
          `strict` is ignored when it is given.
      auth_dependency: Custom FastAPI dependency that authenticates a request.
          It must raise `HTTPException` when access is denied. When given, it
          replaces the session and Basic checks. Works without any session
          support.
      require_if_match: When `True`, `PUT /update/{slug}` and
          `DELETE /delete/{slug}` need an `If-Match` header (its value from a
          prior `GET /{slug}/raw`'s `ETag` response header) and reject the
          write with 412 if the post changed since, or 428 if the header is
          missing (see TODO 4.7). `False` (default) makes the header
          optional: when sent, it's still checked; when not, the write goes
          through unconditionally like before.
      validators: External validators run on every write (TODO 6.2). A
          write whose outcome is in a validator's `blocking` list is rolled
          back and answered with HTTP 422 carrying the `issues` (TODO 6.3).
      collection_spec: Optional project collection settings. When it has a
          `slug_template`, POST /create and POST /save can generate a slug.
      authorize: Shared permission callback; defaults to the built-in RBAC
          policy and may be synchronous or asynchronous.

  Returns:
      APIRouter with REST API endpoints

  Note:
      With `require_auth=True` and no credentials or dependency, the router
      only accepts requests that carry a session (it needs a
      `SessionMiddleware`); other requests get 401. `add_blog_to_fastapi()` and
      `add_editor_to_app()` also report this misconfiguration at startup.

  Example:
      ```python
      from fastapi import (
        FastAPI,
      )
      from fastapi_blog.editor import (
        get_api_router,
      )

      app = FastAPI()
      api_router = get_api_router(
        require_auth=True
      )
      app.include_router(
        api_router,
        prefix='/api/posts',
      )
      ```

  """
  api_router = APIRouter(tags=['editor'])
  if collection_spec is not None:
    slug_re = collection_spec.to_collection().slug_pattern
    slug_pattern = (
      slug_re.pattern if isinstance(slug_re, re.Pattern) else slug_re
    )
    slug_max_length = 200
  else:
    slug_pattern = SLUG_PATTERN
    slug_max_length = 100
  slug_path = Path(pattern=slug_pattern, max_length=slug_max_length)
  if collection_spec is not None:
    posts_dirname = str(collection_spec.dir)
    if frontmatter_schema is not None:
      collection_spec = collection_spec.with_schema(frontmatter_schema)
    else:
      frontmatter_schema = collection_spec.schema
    if not validators:
      validators = collection_spec.validators
  docs = store.DocumentStore(
    collection_spec.to_collection()
    if collection_spec is not None
    else store.blog_collections(posts_dirname)['posts']
  )
  Payload = payload_model(strict, frontmatter_schema)

  def _require_if_match(if_match: str | None) -> None:
    if require_if_match and if_match is None:
      raise HTTPException(
        status_code=status.HTTP_428_PRECONDITION_REQUIRED,
        detail='If-Match header is required',
      )

  def _document_path(slug: str) -> pathlib.Path:
    path = docs.path_for(slug)
    if path is not None:
      return path
    return pathlib.Path(posts_dirname) / f'{slug}.md'

  def _check_unique_on_create(slug: str, frontmatter: dict[str, Any]) -> None:
    """Reject duplicate configured values before a new file is written."""
    if collection_spec is None or not collection_spec.unique:
      return
    schema = collection_spec.schema or frontmatter_schema
    seq_regex = (
      collection_spec.slug_template.slug_regex()
      if collection_spec.slug_template is not None
      else None
    )
    new_seq = None
    if 'seq' in collection_spec.unique:
      match = seq_regex.fullmatch(slug) if seq_regex is not None else None
      if match is None or 'seq' not in match.groupdict():
        raise HTTPException(
          status_code=status.HTTP_400_BAD_REQUEST,
          detail='Slug does not match the configured sequence template',
        )
      new_seq = match.group('seq')
    new_values: dict[str, Any] = {}
    for name in collection_spec.unique:
      if name == 'seq':
        new_values[name] = new_seq
      else:
        field = schema.get(name) if schema is not None else None
        key = field.key if field is not None else name
        new_values[name] = frontmatter.get(key)
    for existing_slug in docs.list():
      try:
        existing = docs.read(existing_slug).frontmatter
      except (store.ParseError, store.NotFoundError):
        continue
      for name, value in new_values.items():
        if value is None or value == '':
          continue
        if name == 'seq':
          match = seq_regex.fullmatch(existing_slug) if seq_regex else None
          existing_value = (
            match.group('seq')
            if match is not None and 'seq' in match.groupdict()
            else None
          )
        else:
          field = schema.get(name) if schema is not None else None
          key = field.key if field is not None else name
          existing_value = existing.get(key)
        if existing_value == value:
          raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
              f'Value {value!r} of unique field {name!r} is already used '
              f'by {existing_slug!r}'
            ),
          )

  def _remove_created(slug: str) -> None:
    """Remove a file created by this request, even when deletes are off.

    Rollback of a just-created document is not a user-facing delete, so a
    collection with `delete: false` must not stop it.
    """
    target = docs.path_for(slug)
    if target is None:
      return
    try:
      docs.delete(slug, notify=False)
    except store.OperationNotAllowedError:
      target.unlink()

  def _write_validated(
    slug: str,
    frontmatter: dict[str, Any],
    body: str,
    *,
    previous_text: str | None,
    if_match: str | None = None,
    user: dict[str, Any] | None = None,
  ) -> str:
    """Write, run the blocking validators, roll back on a blocking outcome.

    A blocking outcome restores the previous bytes (or removes a file that
    was just created) and raises HTTP 422 with the findings. Between the
    write and a rollback the new content is on disk and visible to
    concurrent readers; checking a temporary copy first is out of scope
    (TODO 6.3 documents this).
    """
    # A configured `unique` constraint must be checked in the same critical
    # section as the write. In particular, `unique: [seq]` applies to manual
    # slugs too, not only to slugs produced by `POST /create`.
    with docs._lock:
      if previous_text is None and collection_spec is not None:
        _check_unique_on_create(slug, frontmatter)
      try:
        etag = docs.write(
          slug,
          frontmatter,
          body,
          if_match=if_match,
          user=_event_actor(user),
          notify=False,
        )
      except store.OperationNotAllowedError as exc:
        raise HTTPException(
          status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    blocking = run_blocking(
      validators,
      collection_name=(collection_spec.name if collection_spec else 'posts'),
      slug=slug,
      path=_document_path(slug),
      frontmatter=frontmatter,
      cwd=pathlib.Path.cwd(),
    )
    if not blocking:
      docs.notify_change(
        'updated' if previous_text is not None else 'created',
        slug,
        etag,
        user=_event_actor(user),
      )
      return etag
    if previous_text is None:
      _remove_created(slug)
    else:
      target = docs.path_for(slug)
      if target is not None:
        store.atomic_write_text(target, previous_text)
    helpers.clear_posts_cache()
    raise HTTPException(
      status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
      detail={'issues': [issue.to_dict() for issue in blocking]},
    )

  # Setup authentication dependency
  auth_func: Callable[..., Any]
  if require_auth:
    if auth_dependency is not None:
      # Custom dependency (any scheme, no session support needed)
      auth_func = auth_dependency
    elif admin_username and admin_password:
      # Use unified auth (session + Basic auth)
      from .auth import require_current_user

      async def _unified_auth(request: Request) -> dict[str, Any]:
        # Session identities retain their assigned role; Basic auth is the
        # separately configured administrator credential.
        session_user = user_from_session(request)
        if session_user is not None:
          return session_user
        username = await require_current_user(
          request,
          admin_username=admin_username,
          admin_password=admin_password,
        )
        return {'username': username, 'role': ADMIN, 'is_admin': True}

      auth_func = _unified_auth
    else:
      # Use legacy session-only auth
      auth_func = require_authentication
  else:
    auth_func = optional_authentication

  permission_check = authorize or default_authorize

  def _guard(action: str):
    async def guard(
      request: Request, user: dict[str, Any] | None = Depends(auth_func)
    ) -> dict[str, Any] | None:
      principal: dict[str, Any] | None
      if isinstance(user, dict):
        principal = dict(user)
      elif user is None:
        principal = None
      else:
        principal = {'username': str(user), 'role': None}
      if principal is not None:
        principal.setdefault(
          'role', ADMIN if principal.get('is_admin') else None
        )
      request.state.blog_user = principal
      if not require_auth and authorize is None:
        return principal
      await ensure_allowed(permission_check, request, 'posts', action)
      return principal
    return guard

  def _create_generated(
    payload: Any, user: dict[str, Any] | None = None
  ) -> tuple[str, str]:
    if collection_spec is None or collection_spec.slug_template is None:
      raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
          'A slug is required; configure a collection slug_template to '
          'generate it.'
        ),
      )
    fm_dump = _frontmatter_dump(payload, frontmatter_schema, is_create=True)
    try:
      slug, etag = collection_spec.create_document(
        docs,
        fm_dump,
        _body(payload),
        created_at=datetime.now(UTC),
        user=_event_actor(user),
        notify=False,
      )
    except store.OperationNotAllowedError as exc:
      raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
      ) from exc
    except store.ConflictError as exc:
      raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except (ValueError, OSError) as exc:
      raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
      ) from exc

    blocking = run_blocking(
      validators,
      collection_name=collection_spec.name,
      slug=slug,
      path=docs.path_for(slug) or (pathlib.Path(posts_dirname) / f'{slug}.md'),
      frontmatter=fm_dump,
      cwd=pathlib.Path.cwd(),
    )
    if blocking:
      _remove_created(slug)
      raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={'issues': [issue.to_dict() for issue in blocking]},
      )
    docs.notify_change('created', slug, etag, user=_event_actor(user))
    helpers.clear_posts_cache()
    return slug, etag

  @api_router.post('/create', status_code=status.HTTP_201_CREATED)
  async def create_generated_post(
    payload: Payload,  # type: ignore[valid-type]
    response: Response,
    user: dict | None = Depends(_guard('create')),
  ) -> dict[str, str]:
    slug, etag = _create_generated(payload, user=user)
    response.headers['ETag'] = etag
    return {'slug': slug, 'status': 'created'}

  @api_router.get('/{slug}/raw')
  async def get_raw(
    response: Response,
    slug: str = slug_path,
    user: dict | None = Depends(_guard('read')),
  ) -> dict[str, Any]:
    try:
      record = docs.read(slug)
    except (ValueError, FileNotFoundError) as exc:
      raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Post '{slug}' not found",
      ) from exc
    response.headers['ETag'] = record.etag
    return {
      'slug': slug,
      'frontmatter': record.frontmatter,
      'content': record.body.lstrip('\n'),
    }

  @api_router.post('/create/{slug}', status_code=status.HTTP_201_CREATED)
  async def create_post(
    payload: Payload,  # type: ignore[valid-type]
    response: Response,
    slug: str = slug_path,
    user: dict | None = Depends(_guard('create')),
  ) -> dict[str, str]:
    if docs.exists(slug):
      raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Post '{slug}' already exists",
      )
    fm_dump = _frontmatter_dump(payload, frontmatter_schema, is_create=True)
    etag = _write_validated(
      slug, fm_dump, _body(payload), previous_text=None, user=user
    )
    helpers.clear_posts_cache()
    response.headers['ETag'] = etag
    return {'slug': slug, 'status': 'created'}

  @api_router.put('/update/{slug}')
  async def update_post(
    payload: Payload,  # type: ignore[valid-type]
    response: Response,
    slug: str = slug_path,
    user: dict | None = Depends(_guard('update')),
    if_match: str | None = Header(None, alias='If-Match'),
  ) -> dict[str, str]:
    _require_if_match(if_match)
    try:
      existing = docs.read(slug).frontmatter
    except (ValueError, FileNotFoundError) as exc:
      raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Post '{slug}' not found",
      ) from exc
    fm_dump = _frontmatter_dump(
      payload, frontmatter_schema, is_create=False, existing=existing
    )
    previous_path = docs.path_for(slug)
    previous_text = (
      previous_path.read_text(encoding='utf-8') if previous_path else None
    )
    try:
      etag = _write_validated(
        slug,
        fm_dump,
        _body(payload),
        previous_text=previous_text,
        if_match=if_match,
        user=user,
      )
    except store.ConflictError as exc:
      raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    helpers.clear_posts_cache()
    response.headers['ETag'] = etag
    return {'slug': slug, 'status': 'updated'}

  @api_router.delete('/delete/{slug}', status_code=status.HTTP_204_NO_CONTENT)
  async def delete_post(
    slug: str = slug_path,
    user: dict | None = Depends(_guard('delete')),
    if_match: str | None = Header(None, alias='If-Match'),
  ) -> None:
    _require_if_match(if_match)
    try:
      docs.delete(slug, if_match=if_match, user=_event_actor(user))
    except store.OperationNotAllowedError as exc:
      raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
      ) from exc
    except (ValueError, FileNotFoundError) as exc:
      raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Post '{slug}' not found",
      ) from exc
    except store.ConflictError as exc:
      raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    helpers.clear_posts_cache()

  @api_router.post('/save')
  async def save_post(
    request: Request,
    response: Response,
    user: dict | None = Depends(auth_func),
  ) -> JSONResponse:
    data = await request.json()
    slug = data.get('slug')

    frontmatter = data.get('frontmatter', {})
    content = data.get('content', '')

    try:
      payload = Payload(  # type: ignore[call-arg]
        frontmatter=frontmatter, content=content
      )
    except Exception as e:
      raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f'Invalid payload: {str(e)}',
      ) from e

    is_new = not slug or not docs.exists(slug)
    await _guard('create' if is_new else 'update')(request, user)
    if not slug:
      generated_slug, etag = _create_generated(payload, user=user)
      response.headers['ETag'] = etag
      return JSONResponse(
        content={'slug': generated_slug, 'status': 'created'},
        status_code=status.HTTP_201_CREATED,
      )

    existing = None if is_new else docs.read(slug).frontmatter
    fm_dump = _frontmatter_dump(
      payload, frontmatter_schema, is_create=is_new, existing=existing
    )
    if is_new:
      previous_text = None
    else:
      previous_path = docs.path_for(slug)
      previous_text = (
        previous_path.read_text(encoding='utf-8') if previous_path else None
      )
    etag = _write_validated(
      slug, fm_dump, _body(payload), previous_text=previous_text, user=user
    )
    helpers.clear_posts_cache()
    response.headers['ETag'] = etag

    return JSONResponse(
      content={'slug': slug, 'status': 'created' if is_new else 'updated'},
      status_code=status.HTTP_201_CREATED if is_new else status.HTTP_200_OK,
    )

  return api_router


def add_editor_to_app(
  app: FastAPI,
  prefix: str = '/api/posts',
  posts_dirname: str = 'posts',
  strict: bool = True,
  ui: bool = True,
  ui_prefix: str = '/admin/editor',
  require_auth: bool = True,
  frontmatter_schema: FrontmatterSchema | None = None,
  admin_username: str | None = None,
  admin_password: str | None = None,
  auth_dependency: Callable[..., Any] | None = None,
  require_if_match: bool = False,
  collection_spec: CollectionSpec | None = None,
  authorize: Authorizer | None = None,
) -> FastAPI:
  """Add editor REST API and optional UI to FastAPI app.

  .. deprecated:: 0.8.0
      The UI parameter (ui=True) is deprecated. Use add_admin_to_app() for
      admin interface instead. The REST API will remain available but should
      be enabled explicitly via include_api parameter in future versions.

  Args:
      app: FastAPI application instance
      prefix: URL prefix for REST API (default: '/api/posts')
      posts_dirname: Directory containing markdown posts (default: 'posts')
      strict: Use strict frontmatter validation (default: True)
      ui: (DEPRECATED) Include UI routes (default: True)
      ui_prefix: (DEPRECATED) URL prefix for UI (default: '/admin/editor')
      require_auth: Require authentication for all endpoints (default: True)
      frontmatter_schema: Custom frontmatter schema for the REST API (optional).
          The deprecated UI doesn’t support it and keeps the built-in fields.
      admin_username: Username for Basic auth (optional)
      admin_password: Password for Basic auth (optional)
      auth_dependency: Custom authentication dependency (optional), see
          `get_api_router()`
      require_if_match: Require an `If-Match` header on update/delete
          (optional), see `get_api_router()`
      collection_spec: Optional project collection settings. A configured
          `slug_template` enables `POST /create` and blank-slug `/save`.

  Returns:
      FastAPI application with editor routes added

  Raises:
      ConfigurationError: At app startup, if `require_auth=True` and there is
          no credentials, no dependency and no `SessionMiddleware`.

  Example:
      ```python
      from fastapi import (
        FastAPI,
      )
      from fastapi_blog import (
        add_editor_to_app,
      )

      app = FastAPI()
      # REST API only (recommended)
      add_editor_to_app(
        app, ui=False
      )

      # Or use new admin panel instead (extra `admin`)
      from fastapi_blog import (
        add_admin_to_app,
      )

      add_admin_to_app(
        app
      )
      ```

  """
  # Emit deprecation warning if UI is enabled
  if ui:
    warnings.warn(
      "The 'ui' parameter in add_editor_to_app() is deprecated and will be "
      'removed in version 1.0.0. Please use add_admin_to_app() from '
      'fastapi_blog.admin for a modern admin interface with better features. '
      'The REST API (/api/posts) will remain available.',
      DeprecationWarning,
      stacklevel=2,
    )

  if ui and frontmatter_schema is not None:
    warnings.warn(
      'The deprecated editor UI doesn’t support `frontmatter_schema` and '
      'keeps the built-in fields. Use `ui=False` and the admin panel.',
      UserWarning,
      stacklevel=2,
    )

  # Use get_api_router() to get REST API endpoints
  api_router = get_api_router(
    posts_dirname=posts_dirname,
    strict=strict,
    require_auth=require_auth,
    admin_username=admin_username,
    admin_password=admin_password,
    frontmatter_schema=frontmatter_schema,
    auth_dependency=auth_dependency,
    require_if_match=require_if_match,
    collection_spec=collection_spec,
    authorize=authorize,
  )
  app.include_router(api_router, prefix=prefix)
  install_origin_check_middleware(app, (prefix,))
  add_startup_check(
    app,
    lambda: check_api_auth_config(
      app,
      require_auth=require_auth,
      admin_username=admin_username,
      admin_password=admin_password,
      auth_dependency=auth_dependency,
    ),
  )

  # Add deprecated UI routes if requested
  if ui:
    _add_ui_routes(
      app,
      ui_prefix=ui_prefix,
      posts_dirname=posts_dirname,
      strict=strict,
      require_auth=require_auth,
      authorize=authorize,
    )

  return app


def _add_ui_routes(
  app: FastAPI,
  ui_prefix: str,
  posts_dirname: str,
  strict: bool,
  require_auth: bool,
  authorize: Authorizer | None = None,
) -> None:
  """Add deprecated UI routes for editor."""
  ui_router = APIRouter(prefix=ui_prefix, tags=['editor-ui'])
  slug_path = Path(pattern=SLUG_PATTERN, max_length=100)
  auth_func = (
    require_authentication if require_auth else optional_authentication
  )
  permission_check = authorize or default_authorize

  async def _require_ui_permission(
    request: Request, user: dict[str, Any] | None, action: str
  ) -> None:
    principal = dict(user) if isinstance(user, dict) else None
    request.state.blog_user = principal
    if not require_auth and authorize is None:
      return
    await ensure_allowed(permission_check, request, 'posts', action)

  # Prep templates
  env = jinja2.Environment(
    loader=jinja2.PackageLoader('fastapi_blog', 'templates'),
    autoescape=jinja2.select_autoescape(['html', 'xml']),
  )
  templates = Jinja2Templates(env=env)

  def _context(request: Request, **kwargs: Any) -> dict[str, Any]:
    return {'request': request, **kwargs}

  @ui_router.get('/', response_class=HTMLResponse)
  async def editor_index(
    request: Request,
    user: dict | None = Depends(auth_func),
  ) -> Any:
    await _require_ui_permission(request, user, 'read')
    posts = helpers.list_posts(
      posts_dirname=posts_dirname, strict=strict, published=True
    )
    drafts = helpers.list_posts(
      posts_dirname=posts_dirname, strict=strict, published=False
    )
    return templates.TemplateResponse(
      request=request,
      name='admin/list.html',
      context=_context(request, posts=list(posts) + list(drafts)),
    )

  @ui_router.get('/new', response_class=HTMLResponse)
  async def editor_new(
    request: Request,
    user: dict | None = Depends(auth_func),
  ) -> Any:
    await _require_ui_permission(request, user, 'create')
    return templates.TemplateResponse(
      request=request,
      name='admin/edit.html',
      context=_context(
        request,
        is_new=True,
        slug='',
        frontmatter={'title': '', 'date': '', 'tags': [], 'published': False},
        content='',
      ),
    )

  @ui_router.get('/{slug}', response_class=HTMLResponse)
  async def editor_edit(
    request: Request,
    slug: str = slug_path,
    user: dict | None = Depends(auth_func),
  ) -> Any:
    await _require_ui_permission(request, user, 'update')
    path = _post_path(slug, posts_dirname)
    if not path.is_file():
      raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Post '{slug}' not found",
      )
    data = _parse_file(path)
    return templates.TemplateResponse(
      request=request,
      name='admin/edit.html',
      context=_context(
        request,
        is_new=False,
        slug=slug,
        frontmatter=data['frontmatter'],
        content=data['content'],
      ),
    )

  app.include_router(ui_router)
