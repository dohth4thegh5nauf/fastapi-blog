"""CRUD operations for markdown files using starlette-admin CustomView."""

import os
from datetime import datetime
from pathlib import Path
from typing import Any

from starlette.requests import Request
from starlette.responses import Response
from starlette_admin.routing import route
from starlette_admin.views import CustomView

from .. import store
from ..models import DEFAULT_SCHEMA, FrontmatterSchema
from .form_fields import (
  build_form_fields,
  form_fields_meta,
  get_field_value,
)


# Simple identity function - labels will be set dynamically per locale
def _(message: str) -> str:
  """Identity function. Labels are set dynamically in _create_admin_for_locale()."""
  return message


def get_posts_directory() -> str:
  """Get posts directory from environment or default location.

  Returns:
    Path to posts directory as string

  """
  posts_dir_env = os.getenv('POSTS_DIR')
  if posts_dir_env:
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
  ):
    """Initialize markdown post with slug, frontmatter, content and schema."""
    self.slug = slug
    self.frontmatter = frontmatter
    self.content = content
    self.schema = schema or DEFAULT_SCHEMA
    self.title = self._role_value('title', slug)
    self.date = self._role_value('date', '')
    self.published = bool(self._role_value('published', False))
    self.tags = self._role_value('tags', [])

  def _role_value(self, role: str, default: Any) -> Any:
    spec = self.schema.field_for_role(role)
    return get_field_value(self.frontmatter, spec, default)


class MarkdownFileManager:
  """Manager for reading/writing markdown files."""

  def __init__(
    self, posts_dir: str = 'posts', schema: FrontmatterSchema | None = None
  ):
    """Initialize file manager with posts directory and frontmatter schema."""
    self.posts_dir = Path(posts_dir)
    self.posts_dir.mkdir(exist_ok=True)
    self.schema = schema

  def list_posts(self) -> list[MarkdownPost]:
    """List all markdown posts."""
    posts = []
    for file_path in self.posts_dir.glob('*.md'):
      try:
        post = self.load_post(file_path.stem)
        if post:
          posts.append(post)
      except Exception as e:
        print(f'Error loading {file_path}: {e}')

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
    file_path = self.posts_dir / f'{slug}.md'
    if not file_path.exists():
      return None

    try:
      frontmatter, body = store.read_document(file_path)
    except ValueError as e:
      print(f'Error parsing frontmatter for {slug}: {e}')
      frontmatter, body = {}, file_path.read_text(encoding='utf-8')
    body = body.strip()

    return MarkdownPost(slug, frontmatter, body, self.schema)

  def save_post(
    self, slug: str, frontmatter: dict[str, Any], content: str
  ) -> None:
    """Save a post to file."""
    file_path = self.posts_dir / f'{slug}.md'
    store.write_document(file_path, frontmatter, f'\n{content}')

  def delete_post(self, slug: str) -> bool:
    """Delete a post."""
    file_path = self.posts_dir / f'{slug}.md'
    if file_path.exists():
      file_path.unlink()
      return True
    return False


class MarkdownListView(CustomView):
  """List view for markdown posts."""

  def __init__(
    self,
    posts_dir: str = 'posts',
    locale: str = 'en',
    schema: FrontmatterSchema | None = None,
  ):
    """Initialize list view with posts directory, locale and schema."""
    super().__init__(
      menu_label=_('Posts'),
      icon='fa fa-file-text',
      path='/posts',
      route_name='posts:list',
    )
    self.schema = schema or DEFAULT_SCHEMA
    self.manager = MarkdownFileManager(posts_dir, self.schema)
    self.locale = locale

  @route('')
  async def index(self, request: Request) -> Response:
    """Render list of posts."""
    posts = self.manager.list_posts()

    # Convert to dict for template
    posts_data = [
      {
        'slug': p.slug,
        'title': p.title,
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


class MarkdownEditView(CustomView):
  """Edit view for markdown posts."""

  def __init__(
    self,
    posts_dir: str = 'posts',
    locale: str = 'en',
    schema: FrontmatterSchema | None = None,
  ):
    """Initialize edit view with posts directory, locale and schema."""
    super().__init__(
      menu_label=_('Edit Post'),
      path='/posts/edit/{slug}',
      route_name='posts:edit',
      add_to_menu=False,  # Don't show in menu
    )
    self.schema = schema or DEFAULT_SCHEMA
    self.manager = MarkdownFileManager(posts_dir, self.schema)
    self.locale = locale

  @route('')
  async def index(self, request: Request) -> Response:
    """Render edit form."""
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

    form_fields = build_form_fields(self.schema, post.frontmatter, t)

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
        },
        'form_fields': form_fields,
        'form_fields_meta': form_fields_meta(form_fields),
        'base_url': request.scope['root_path'],
        't': t,
      },
    )


class MarkdownCreateView(CustomView):
  """Create view for new markdown posts."""

  def __init__(
    self,
    posts_dir: str = 'posts',
    locale: str = 'en',
    schema: FrontmatterSchema | None = None,
  ):
    """Initialize create view with posts directory, locale and schema."""
    super().__init__(
      menu_label=_('New Post'),
      path='/posts/new',
      route_name='posts:new',
      add_to_menu=False,
    )
    self.schema = schema or DEFAULT_SCHEMA
    self.manager = MarkdownFileManager(posts_dir, self.schema)
    self.locale = locale

  @route('')
  async def index(self, request: Request) -> Response:
    """Render create form."""
    assert self.templates is not None
    # Get translations for this view's locale
    from ..i18n import load_translations

    translations = load_translations(self.locale)
    t = translations['post']

    form_fields = build_form_fields(self.schema, {}, t, is_new=True)

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
        },
        'form_fields': form_fields,
        'form_fields_meta': form_fields_meta(form_fields),
        'is_new': True,
        'base_url': request.scope['root_path'],
        't': t,
      },
    )
