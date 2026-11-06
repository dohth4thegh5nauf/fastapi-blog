import dataclasses
import pathlib
import re
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

from fastapi import (
  APIRouter,
  Body,
  Depends,
  FastAPI,
  Header,
  HTTPException,
  Path,
  Query,
  Request,
  Response,
  status,
)
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from . import store
from .auth import add_startup_check, check_api_auth_config
from .config import CollectionSpec, ConfigError
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
from .service import (
  BlockingValidationError,
  DocumentService,
  UniqueViolationError,
)
from .validators import Validator


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
  dynamic_collection_spec = (
    collection_spec
    if collection_spec is not None and callable(collection_spec.dir)
    else None
  )
  if dynamic_collection_spec is not None:
    collection_spec = dataclasses.replace(
      dynamic_collection_spec, dir=pathlib.Path.cwd()
    )

  request_collection_context: ContextVar[tuple[Any, Any] | None] = ContextVar(
    'fastapi_blog_request_collection_context', default=None
  )
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
  docs: Any = store.DocumentStore(
    collection_spec.to_collection()
    if collection_spec is not None
    else store.blog_collections(posts_dirname)['posts']
  )
  document_service: Any = DocumentService(
    docs,
    frontmatter_schema,
    collection_spec=collection_spec,
    validators=validators,
    cwd=pathlib.Path.cwd(),
  )

  async def bind_request_collection(request: Request):
    if dynamic_collection_spec is None:
      yield
      return
    try:
      request_spec = dynamic_collection_spec.for_request(request)
      request_docs = store.DocumentStore(request_spec.to_collection())
      request_service = DocumentService(
        request_docs,
        frontmatter_schema,
        collection_spec=request_spec,
        validators=validators,
        cwd=pathlib.Path.cwd(),
      )
    except ConfigError as exc:
      raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail='Unable to resolve document collection for this request',
      ) from exc
    token = request_collection_context.set((request_docs, request_service))
    try:
      yield
    finally:
      request_collection_context.reset(token)

  if dynamic_collection_spec is not None:
    api_router.dependencies.append(Depends(bind_request_collection))

  class RequestBoundProxy:
    def __init__(self, index: int, attribute: str | None = None):
      self.index = index
      self.attribute = attribute

    def _target(self):
      context = request_collection_context.get()
      target = (
        context[self.index]
        if context is not None
        else (
          static_docs,
          static_service,
        )[self.index]
      )
      return getattr(target, self.attribute) if self.attribute else target

    def __getattr__(self, name):
      return getattr(self._target(), name)

  if dynamic_collection_spec is not None:
    static_docs, static_service = docs, document_service
    docs = RequestBoundProxy(0)
    document_service = RequestBoundProxy(1)
  Payload = payload_model(strict, frontmatter_schema)

  def _require_if_match(if_match: str | None) -> None:
    if require_if_match and if_match is None:
      raise HTTPException(
        status_code=status.HTTP_428_PRECONDITION_REQUIRED,
        detail='If-Match header is required',
      )

  def _write_document(
    slug: str | None,
    frontmatter: dict[str, Any],
    body: str,
    *,
    if_match: str | None = None,
    user: dict[str, Any] | None = None,
  ) -> tuple[str, str]:
    """Write through the shared document service, mapping failures to HTTP.

    The service checks configured uniqueness, writes, runs the blocking
    validators and rolls back on a blocking outcome (TODO 6.3): a blocking
    outcome restores the previous bytes (or removes a just-created file) and
    raises HTTP 422 with the findings. Between the write and a rollback the
    new content is on disk and visible to concurrent readers; checking a
    temporary copy first is out of scope.
    """
    try:
      result = document_service.commit(
        slug,
        frontmatter,
        body,
        if_match=if_match,
        user=user,
      )
    except BlockingValidationError as exc:
      raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={'issues': [issue.to_dict() for issue in exc.issues]},
      ) from exc
    except UniqueViolationError as exc:
      raise HTTPException(
        status_code=status.HTTP_409_CONFLICT, detail=str(exc)
      ) from exc
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
    return result.slug, result.etag

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
      if (
        authorize is None
        and auth_dependency is not None
        and principal is not None
        and principal.get('role') is None
        and not principal.get('is_admin')
        and 'permissions' not in principal
      ):
        # An explicit API dependency is the host's authorization boundary.
        return principal
      await ensure_allowed(permission_check, request, 'posts', action)
      return principal

    return guard

  def _create_generated(
    payload: Any, user: dict[str, Any] | None = None
  ) -> tuple[str, str]:
    fm_dump = _frontmatter_dump(payload, frontmatter_schema, is_create=True)
    return _write_document(None, fm_dump, _body(payload), user=user)

  adapter = (
    None
    if collection_spec is not None and collection_spec.i18n is None
    else RequestBoundProxy(1, 'i18n_documents')
    if dynamic_collection_spec is not None
    else document_service.i18n_documents
  )

  if adapter is not None:

    @api_router.get('/{slug}')
    async def get_localized_post(
      response: Response,
      slug: str = slug_path,
      locale: str | None = Query(None),
      fallback: bool | None = Query(None),
      user: dict | None = Depends(_guard('read')),
    ) -> dict[str, Any]:
      requested_locale = locale or adapter.config.default_locale
      if requested_locale not in adapter.config.locales:
        raise HTTPException(
          status_code=status.HTTP_400_BAD_REQUEST,
          detail=f'Unknown locale: {requested_locale}',
        )
      try:
        record = adapter.read(slug, requested_locale, fallback=fallback)
        document_service.authorize_read(
          user, slug, record.locale, record.frontmatter
        )
      except store.OperationNotAllowedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
      except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(
          status_code=status.HTTP_404_NOT_FOUND,
          detail=f"Post '{slug}' has no '{requested_locale}' translation",
        ) from exc
      response.headers['ETag'] = record.etag
      response.headers['Entry-ETag'] = adapter.entry_etag(slug) or ''
      response_frontmatter = dict(record.frontmatter)
      response_body = record.body
      if record.locale != adapter.config.default_locale:
        canonical_record = adapter.read(
          slug, adapter.config.default_locale, fallback=False
        )
        try:
          document_service.authorize_read(
            user, slug, canonical_record.locale, canonical_record.frontmatter
          )
        except store.OperationNotAllowedError as exc:
          raise HTTPException(status_code=403, detail=str(exc)) from exc
        canonical = canonical_record.frontmatter
        if not adapter.config.translate_body:
          response_body = canonical_record.body
        for field in document_service.schema.fields:
          if field.i18n in ('none', 'duplicate'):
            if field.key in canonical:
              response_frontmatter[field.key] = canonical[field.key]
            else:
              response_frontmatter.pop(field.key, None)
      return {
        'slug': slug,
        'locale': record.locale,
        'fallback_used': record.locale != requested_locale,
        'locales_present': list(adapter.locales_present(slug)),
        'entry_etag': adapter.entry_etag(slug),
        'frontmatter': response_frontmatter,
        'content': response_body.lstrip('\n'),
      }

    @api_router.put('/{slug}')
    async def put_localized_post(
      request: Request,
      response: Response,
      data: dict[str, Any] = Body(...),
      slug: str = slug_path,
      locale: str | None = Query(None),
      user: dict | None = Depends(auth_func),
      if_match: str | None = Header(None, alias='If-Match'),
    ) -> JSONResponse:
      """Create or update one locale, or several locales as one entry."""
      if not isinstance(data, dict):
        raise HTTPException(
          status_code=status.HTTP_400_BAD_REQUEST,
          detail='The request body must be an object',
        )

      is_many = 'locales' in data
      locales_payload = data.get('locales')
      if is_many:
        if locale is not None:
          raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Do not combine the locale query parameter with locales',
          )
        if not isinstance(locales_payload, dict) or not locales_payload:
          raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='locales must be a non-empty object',
          )
        source_documents = locales_payload
      else:
        source_documents = {locale or adapter.config.default_locale: data}

      documents: dict[str, tuple[dict[str, Any], str]] = {}
      for target_locale, item in source_documents.items():
        if not isinstance(target_locale, str) or not isinstance(item, dict):
          raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Each locale must map to a document object',
          )
        frontmatter = item.get('frontmatter', {})
        content = item.get('content', '')
        if not isinstance(frontmatter, dict) or not isinstance(content, str):
          raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
              f"Locale '{target_locale}' must contain an object frontmatter "
              'and string content'
            ),
          )
        documents[target_locale] = (frontmatter, content)

      is_new = not adapter.has_entry(slug)
      user = await _guard('create' if is_new else 'update')(request, user)
      if not is_new:
        _require_if_match(if_match)

      locale_etags: dict[str, str] | None = None
      expected_entry_etag: str | None = None
      if if_match is not None:
        if is_many:
          expected_entry_etag = if_match
        else:
          target_locale = next(iter(documents))
          target_path = adapter.path_for(slug, target_locale)
          target_etag = (
            adapter.read(slug, target_locale, fallback=False).etag
            if target_path.is_file()
            else None
          )
          current_entry_etag = adapter.entry_etag(slug)
          if target_etag == if_match:
            locale_etags = {target_locale: if_match}
          elif current_entry_etag == if_match:
            expected_entry_etag = if_match
          else:
            # A fallback GET returns the canonical locale's ETag. Accept it
            # for creating a missing translation, but guard the write with
            # the aggregate ETag so a concurrent edit to any locale conflicts.
            canonical = adapter.read(
              slug, adapter.config.default_locale, fallback=False
            )
            if (
              not target_path.is_file()
              and canonical.etag == if_match
              and current_entry_etag is not None
            ):
              expected_entry_etag = current_entry_etag
            else:
              raise HTTPException(
                status_code=(
                  status.HTTP_412_PRECONDITION_FAILED
                  if current_entry_etag is not None
                  else status.HTTP_409_CONFLICT
                ),
                detail='If-Match does not match the current localized entry',
              )

      try:
        result = document_service.save_localized(
          slug,
          documents,
          if_match=locale_etags,
          expected_entry_etag=expected_entry_etag,
          expected_exists=not is_new,
          user=user,
        )
      except BlockingValidationError as exc:
        raise HTTPException(
          status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
          detail={'issues': [issue.to_dict() for issue in exc.issues]},
        ) from exc
      except UniqueViolationError as exc:
        raise HTTPException(
          status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
      except store.OperationNotAllowedError as exc:
        raise HTTPException(
          status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
      except store.ConflictError as exc:
        raise HTTPException(
          status_code=exc.status_code, detail=str(exc)
        ) from exc
      except ValidationError as exc:
        raise HTTPException(
          status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
          detail=exc.errors(),
        ) from exc
      except (ValueError, OSError) as exc:
        raise HTTPException(
          status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

      response.headers['ETag'] = (
        result.entry_etag if is_many else result.etags[next(iter(documents))]
      )
      content = {
        'slug': slug,
        'status': result.status,
        'locales': list(result.etags),
        'locales_present': list(result.locales_present),
        'entry_etag': result.entry_etag,
        'issues': [issue.to_dict() for issue in result.issues],
      }
      return JSONResponse(
        content=content,
        status_code=(
          status.HTTP_201_CREATED
          if result.status == 'created'
          else status.HTTP_200_OK
        ),
        headers={'ETag': response.headers['ETag']},
      )

  @api_router.post('/create', status_code=status.HTTP_201_CREATED)
  async def create_generated_post(
    payload: Payload,  # type: ignore[valid-type]
    response: Response,
    user: dict | None = Depends(_guard('create')),
  ) -> dict[str, str]:
    if adapter is not None:
      raise HTTPException(405, 'Use PUT /{slug} for localized entries')
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
      record = (
        adapter.read(slug, adapter.config.default_locale, fallback=False)
        if adapter is not None
        else docs.read(slug)
      )
      document_service.authorize_read(
        user,
        slug,
        adapter.config.default_locale if adapter is not None else None,
        record.frontmatter,
      )
    except store.OperationNotAllowedError as exc:
      raise HTTPException(status_code=403, detail=str(exc)) from exc
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
    if adapter is not None:
      raise HTTPException(405, 'Use PUT /{slug} for localized entries')
    if docs.exists(slug):
      raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Post '{slug}' already exists",
      )
    fm_dump = _frontmatter_dump(payload, frontmatter_schema, is_create=True)
    _slug, etag = _write_document(slug, fm_dump, _body(payload), user=user)
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
    if adapter is not None:
      raise HTTPException(405, 'Use PUT /{slug} for localized entries')
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
    _slug, etag = _write_document(
      slug, fm_dump, _body(payload), if_match=if_match, user=user
    )
    response.headers['ETag'] = etag
    return {'slug': slug, 'status': 'updated'}

  @api_router.delete('/delete/{slug}', status_code=status.HTTP_204_NO_CONTENT)
  async def delete_post(
    slug: str = slug_path,
    cascade: bool = False,
    user: dict | None = Depends(_guard('delete')),
    if_match: str | None = Header(None, alias='If-Match'),
  ) -> None:
    _require_if_match(if_match)
    try:
      if adapter is not None:
        document_service.delete_localized_entry(
          slug,
          cascade=cascade,
          expected_entry_etag=if_match,
          user=user,
        )
      else:
        document_service.delete(slug, if_match=if_match, user=user)
    except store.OperationNotAllowedError as exc:
      raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
      ) from exc
    except ValueError as exc:
      if adapter is not None:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
      raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Post '{slug}' not found",
      ) from exc
    except FileNotFoundError as exc:
      raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Post '{slug}' not found",
      ) from exc
    except store.ConflictError as exc:
      raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

  @api_router.post('/save')
  async def save_post(
    request: Request,
    response: Response,
    user: dict | None = Depends(auth_func),
  ) -> JSONResponse:
    if adapter is not None:
      raise HTTPException(405, 'Use PUT /{slug} for localized entries')
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
    _slug, etag = _write_document(slug, fm_dump, _body(payload), user=user)
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
  require_auth: bool = True,
  frontmatter_schema: FrontmatterSchema | None = None,
  admin_username: str | None = None,
  admin_password: str | None = None,
  auth_dependency: Callable[..., Any] | None = None,
  require_if_match: bool = False,
  collection_spec: CollectionSpec | None = None,
  authorize: Authorizer | None = None,
) -> FastAPI:
  """Add the post editor REST API to a FastAPI app.

  Args:
      app: FastAPI application instance
      prefix: URL prefix for REST API (default: '/api/posts')
      posts_dirname: Directory containing markdown posts (default: 'posts')
      strict: Use strict frontmatter validation (default: True)
      require_auth: Require authentication for all endpoints (default: True)
      frontmatter_schema: Custom frontmatter schema for the REST API (optional).
      admin_username: Username for Basic auth (optional)
      admin_password: Password for Basic auth (optional)
      auth_dependency: Custom authentication dependency (optional), see
          `get_api_router()`
      require_if_match: Require an `If-Match` header on update/delete
          (optional), see `get_api_router()`
      collection_spec: Optional project collection settings. A configured
          `slug_template` enables `POST /create` and blank-slug `/save`.
      authorize: Shared `(request, resource, action) -> bool` permission
          callback; when omitted, the built-in role policy is used.

  Returns:
      FastAPI application with editor routes added

  Raises:
      ConfigurationError: At app startup, if `require_auth=True` and there is
          no credentials, dependency or `SessionMiddleware`.

  Example:
      ```python
      from fastapi import (
        FastAPI,
      )
      from fastapi_blog import (
        add_editor_to_app,
      )

      app = FastAPI()
      add_editor_to_app(
        app,
        auth_dependency=your_auth_dependency,
      )
      ```

  """
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

  return app
