"""Custom ModelView classes for admin models."""

import inspect
from datetime import date, datetime
from types import SimpleNamespace
from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette_admin import CustomView
from starlette_admin.contrib.sqla import ModelView
from starlette_admin.routing import route

from ..models import DEFAULT_SCHEMA, FrontmatterSchema
from ..permissions import Authorizer, default_authorize, user_from_session
from .passwords import get_password_hasher


# Password constraints
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
BCRYPT_MAX_BYTES = 72  # bcrypt limitation


def validate_and_prepare_password(password: str) -> str:
  """Validate password length for bcrypt hashing.

  Args:
      password: Plain text password

  Returns:
      Validated password ready for hashing

  Raises:
      ValueError: If password doesn't meet requirements with detailed message

  """
  # Check minimum length
  if len(password) < MIN_PASSWORD_LENGTH:
    raise ValueError(
      f'Password is too short. '
      f'Minimum length: {MIN_PASSWORD_LENGTH} characters. '
      f'Current length: {len(password)} characters.'
    )

  # Check maximum character length
  if len(password) > MAX_PASSWORD_LENGTH:
    raise ValueError(
      f'Password is too long. '
      f'Maximum length: {MAX_PASSWORD_LENGTH} characters. '
      f'Current length: {len(password)} characters.'
    )

  # Check bcrypt byte limit (important for Unicode)
  password_bytes = password.encode('utf-8')
  if len(password_bytes) > BCRYPT_MAX_BYTES:
    raise ValueError(
      f'Password exceeds bcrypt limit of {BCRYPT_MAX_BYTES} bytes when encoded. '
      f'Current size: {len(password_bytes)} bytes. '
      f'Tip: Unicode characters take multiple bytes. '
      f'Try using fewer special characters or a shorter password.'
    )

  return password


class _AuthorizedModelView:
  """Shared synchronous permission hooks used by Starlette Admin views."""

  authorize: Authorizer | None = None
  resource = 'posts'

  def _allowed(self, request: Request, action: str) -> bool:
    if getattr(request.state, 'blog_user', None) is None:
      request.state.blog_user = user_from_session(request)
    callback = self.authorize or default_authorize
    result = callback(request, self.resource, action)
    # Starlette Admin's view hooks are synchronous. The REST/custom views
    # support asynchronous callbacks; admin ModelView hooks fail closed here.
    return bool(result) if not inspect.isawaitable(result) else False

  def is_accessible(self, request: Request) -> bool:
    return self._allowed(request, 'read')

  def can_view_detail(self, request: Request) -> bool:
    return self._allowed(request, 'read')

  def can_create(self, request: Request) -> bool:
    return self._allowed(request, 'create')

  def can_edit(self, request: Request) -> bool:
    return self._allowed(request, 'update')

  def can_delete(self, request: Request) -> bool:
    return self._allowed(request, 'delete')

  def can_export(self, request: Request) -> bool:
    return self._allowed(request, 'read')

  def can_import(self, request: Request) -> bool:
    return self._allowed(request, 'create')

  async def is_action_allowed(self, request: Request, name: str) -> bool:
    # Starlette Admin awaits this hook (unlike the sync `can_*` ones), so an
    # asynchronous authorizer can be supported here.
    if getattr(request.state, 'blog_user', None) is None:
      request.state.blog_user = user_from_session(request)
    callback = self.authorize or default_authorize
    result = callback(request, self.resource, 'update')
    if inspect.isawaitable(result):
      result = await result
    return bool(result)


class UserModelView(_AuthorizedModelView, ModelView):
  resource = 'users'
  """Custom view for User model with password hashing.

  Note: label, name, and label_plural are set dynamically per locale
  in add_admin_to_app() function.
  """

  # Custom templates with theme and language switchers
  list_template = 'list.html'
  detail_template = 'detail.html'
  create_template = 'create.html'
  edit_template = 'edit.html'

  exclude_fields_from_list = ['hashed_password']
  exclude_fields_from_detail = ['hashed_password']
  exclude_fields_from_edit = ['hashed_password', 'created_at', 'updated_at']
  exclude_fields_from_create = ['created_at', 'updated_at']

  async def before_create(
    self, request: Request, data: dict[str, Any], obj: Any
  ) -> None:
    """Hash password before creating user."""
    if 'hashed_password' in data and data['hashed_password']:
      # Validate and prepare password
      password = validate_and_prepare_password(data['hashed_password'])
      # Hash the plain text password
      data['hashed_password'] = get_password_hasher().hash(password)
    await super().before_create(request, data, obj)

  async def before_edit(
    self, request: Request, data: dict[str, Any], obj: Any
  ) -> None:
    """Hash password before editing user if password was changed."""
    if 'hashed_password' in data and data['hashed_password']:
      # Only hash if password is being updated (non-empty)
      # If field is empty, keep existing hash
      if data['hashed_password'] != obj.hashed_password:
        # Validate and prepare password
        password = validate_and_prepare_password(data['hashed_password'])
        data['hashed_password'] = get_password_hasher().hash(password)
    await super().before_edit(request, data, obj)


class PostModelView(_AuthorizedModelView, ModelView):
  resource = 'posts'
  """Custom view for Post model.

  Note: label, name, and label_plural are set dynamically per locale
  in add_admin_to_app() function.
  """

  # Custom templates with theme and language switchers
  list_template = 'list.html'
  detail_template = 'detail.html'
  create_template = 'create.html'
  edit_template = 'edit.html'

  exclude_fields_from_edit = ['created_at', 'updated_at']
  exclude_fields_from_create = ['created_at', 'updated_at']

  # Make content field use textarea
  form_overrides = {
    'content': {'widget': 'textarea', 'rows': 20},
    'description': {'widget': 'textarea', 'rows': 3},
  }


def _as_datetime(value: Any) -> datetime | None:
  """Convert a frontmatter date (datetime, date or ISO string) to a datetime."""
  if isinstance(value, datetime):
    return value
  if isinstance(value, date):
    return datetime.combine(value, datetime.min.time())
  if isinstance(value, str):
    try:
      return datetime.fromisoformat(value)
    except ValueError:
      return None
  return None


def load_posts_for_home(posts_dir: str, schema: FrontmatterSchema) -> list[Any]:
  """Load posts for the dashboard using the roles of a custom schema.

  Args:
      posts_dir: Directory with the markdown files.
      schema: Frontmatter schema of the blog.

  Returns:
      Simple objects with `slug`, `title`, `date` (datetime or `None`),
      `published` and `tags` (list of strings), newest first.

  """
  from .markdown_crud import MarkdownFileManager

  posts = []
  for post in MarkdownFileManager(posts_dir, schema).list_posts():
    if isinstance(post.tags, list | tuple):
      tags = [str(tag) for tag in post.tags]
    else:
      tags = [str(post.tags)] if post.tags else []
    posts.append(
      SimpleNamespace(
        slug=post.slug,
        title=post.title,
        date=_as_datetime(post.date),
        published=post.published,
        tags=tags,
      )
    )
  posts.sort(key=lambda p: p.date.isoformat() if p.date else '', reverse=True)
  return posts


class HomeView(CustomView):
  """Custom home view with blog statistics and recent posts.

  Displays:
  - Latest published posts
  - Blog statistics (total posts, published, drafts, tags)
  - Top tags by usage
  """

  def __init__(
    self,
    label: str = 'Home',
    icon: str = 'fa fa-home',
    locale: str = 'en',
    schema: FrontmatterSchema | None = None,
    posts_dirname: str | None = None,
    authorize=None,
    translations_dir: str | None = None,
  ):
    """Initialize home view with locale and frontmatter schema."""
    super().__init__(menu_label=label, icon=icon)
    self.locale = locale
    self.schema = schema
    self.posts_dirname = posts_dirname
    self.authorize = authorize or default_authorize
    self.translations_dir = translations_dir

  def is_accessible(self, request: Request) -> bool:
    if getattr(request.state, 'blog_user', None) is None:
      request.state.blog_user = user_from_session(request)
    result = self.authorize(request, 'posts', 'read')
    return bool(result) if not inspect.isawaitable(result) else False

  @route('')
  async def index(self, request: Request) -> Response:
    """Render custom home page with blog statistics."""
    from .markdown_crud import get_posts_directory

    posts_dir = get_posts_directory(self.posts_dirname)

    # Get all posts (with error handling for malformed posts)
    try:
      all_posts = load_posts_for_home(posts_dir, self.schema or DEFAULT_SCHEMA)
    except Exception:
      # If loading fails, return empty state
      all_posts = []

    # Filter published posts
    published_posts = [p for p in all_posts if p.published]
    draft_posts = [p for p in all_posts if not p.published]

    # Get latest posts (sorted by date, descending). ISO strings compare the
    # same way the dates do, stay comparable across naive/aware datetimes,
    # and sort undated posts (empty string) last.
    latest_posts = sorted(
      published_posts,
      key=lambda p: p.date.isoformat() if p.date else '',
      reverse=True,
    )[:10]

    # Collect all tags
    all_tags: dict[str, int] = {}
    for post in all_posts:
      for tag in post.tags:
        all_tags[tag] = all_tags.get(tag, 0) + 1

    # Top tags (sorted by usage)
    top_tags = sorted(all_tags.items(), key=lambda x: x[1], reverse=True)[:10]

    # Statistics
    stats = {
      'total_posts': len(all_posts),
      'published_posts': len(published_posts),
      'draft_posts': len(draft_posts),
      'total_tags': len(all_tags),
    }

    # Load translations from YAML files
    from ..i18n import load_translations

    translations = load_translations(self.locale, self.translations_dir)
    t = translations['home']

    # starlette-admin assigns templates at mount time.
    assert self.templates is not None  # nosec B101
    return self.templates.TemplateResponse(
      request=request,
      name='home.html',
      context={
        'posts': latest_posts,
        'stats': stats,
        'top_tags': top_tags,
        't': t,  # Add translations
      },
    )
