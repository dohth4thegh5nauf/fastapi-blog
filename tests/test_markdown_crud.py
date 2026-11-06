"""Tests for MarkdownFileManager's slug/path safety."""

import asyncio
import json

import pytest
from starlette.requests import Request

from fastapi_blog.admin.markdown_crud import (
  MarkdownFileManager,
  MarkdownSaveView,
)
from fastapi_blog.config import CollectionSpec
from fastapi_blog.i18n_collections import I18nConfig
from fastapi_blog.models import FieldSpec, FrontmatterSchema
from fastapi_blog.templates import SLUG_TAGS_DEFAULT, parse_template


@pytest.fixture
def manager(tmp_path):
  """Return a MarkdownFileManager over a fresh temporary posts directory."""
  posts_dir = tmp_path / 'posts'
  return MarkdownFileManager(str(posts_dir))


def test_load_post_rejects_path_traversal(manager, tmp_path):
  """A `..`-based slug must never resolve outside posts_dir.

  `load_post` routes the slug through `store.safe_document_path`, which
  rejects it before any file is touched.
  """
  secret = tmp_path / 'secret.md'
  secret.write_text('---\ntitle: Secret\n---\n', encoding='utf-8')

  assert manager.load_post('../secret') is None


def test_save_post_rejects_path_traversal(manager, tmp_path):
  """A `..`-based slug must raise rather than write outside posts_dir."""
  secret = tmp_path / 'secret.md'
  secret.write_text('---\ntitle: Secret\n---\n', encoding='utf-8')

  with pytest.raises(ValueError, match='invalid slug'):
    manager.save_post('../secret', {'title': 'pwned'}, 'pwned')

  assert secret.read_text(encoding='utf-8') == '---\ntitle: Secret\n---\n'


def test_delete_post_rejects_path_traversal(manager, tmp_path):
  """A `..`-based slug must never be able to delete a file outside posts_dir."""
  secret = tmp_path / 'secret.md'
  secret.write_text('---\ntitle: Secret\n---\n', encoding='utf-8')

  assert manager.delete_post('../secret') is False
  assert secret.exists()


def test_save_then_load_round_trips_through_safe_document_path(manager):
  """A normal slug still works end to end."""
  manager.save_post(
    'hello-world', {'title': 'Hello', 'date': '2024-01-01'}, 'Body text'
  )

  post = manager.load_post('hello-world')
  assert post is not None
  assert post.title == 'Hello'


def test_admin_preview_uses_the_public_html_sanitizer(manager):
  async def receive():
    content = '<script>alert(1)</script>\n\nSafe'
    return {
      'type': 'http.request',
      'body': json.dumps({'content': content}).encode(),
      'more_body': False,
    }

  request = Request(
    {
      'type': 'http',
      'asgi': {'version': '3.0'},
      'http_version': '1.1',
      'method': 'POST',
      'scheme': 'http',
      'path': '/admin/posts/save/preview',
      'raw_path': b'/admin/posts/save/preview',
      'query_string': b'',
      'headers': [],
      'client': ('127.0.0.1', 12345),
      'server': ('testserver', 80),
      'root_path': '',
      'path_params': {},
    },
    receive,
  )
  request.state.blog_user = {'username': 'admin', 'role': 'admin'}
  view = MarkdownSaveView(manager, authorize=lambda *_: True)

  response = asyncio.run(view.preview(request))

  assert response.status_code == 200
  assert '<script>' not in response.body.decode()
  assert 'Safe' in response.body.decode()


def test_admin_save_uses_service_without_rest_api(manager):
  async def receive():
    return {
      'type': 'http.request',
      'body': json.dumps(
        {
          'slug': 'service-created',
          'frontmatter': {'title': 'Created in admin', 'date': '2024-01-01'},
          'content': 'Body',
        }
      ).encode(),
      'more_body': False,
    }

  request = Request(
    {
      'type': 'http',
      'asgi': {'version': '3.0'},
      'http_version': '1.1',
      'method': 'POST',
      'scheme': 'http',
      'path': '/admin/posts/save',
      'raw_path': b'/admin/posts/save',
      'query_string': b'',
      'headers': [(b'content-type', b'application/json')],
      'client': ('127.0.0.1', 12345),
      'server': ('testserver', 80),
      'root_path': '',
      'path_params': {},
    },
    receive,
  )
  request.state.blog_user = {'username': 'admin', 'role': 'admin'}
  response = asyncio.run(
    MarkdownSaveView(manager, authorize=lambda *_: True).save(request)
  )

  assert response.status_code == 201
  assert manager.load_post('service-created').title == 'Created in admin'


def test_admin_localized_create_passes_request_to_sequence_allocator(tmp_path):
  contexts = []
  schema = FrontmatterSchema(
    fields=(FieldSpec('title', required=True, role='title', i18n='translate'),)
  )
  collection = CollectionSpec(
    'posts',
    tmp_path / 'posts',
    schema=schema,
    i18n=I18nConfig(('en', 'ru'), 'en'),
    slug_template=parse_template(
      '{seq|pad(4)}-{title_slug}', SLUG_TAGS_DEFAULT, {'title'}
    ),
    sequence_allocator=lambda context: contexts.append(context) or 31,
  )
  view = MarkdownSaveView(
    MarkdownFileManager(
      str(tmp_path / 'posts'), schema=schema, collection_spec=collection
    ),
    authorize=lambda *_args: True,
  )

  async def receive():
    return {
      'type': 'http.request',
      'body': json.dumps(
        {
          'slug': '',
          'content_locale': 'en',
          'frontmatter': {'title': 'Reserved ADR'},
          'content': 'Decision body',
        }
      ).encode(),
      'more_body': False,
    }

  request = Request(
    {
      'type': 'http',
      'asgi': {'version': '3.0'},
      'http_version': '1.1',
      'method': 'POST',
      'scheme': 'http',
      'path': '/admin/posts/save',
      'raw_path': b'/admin/posts/save',
      'query_string': b'',
      'headers': [(b'content-type', b'application/json')],
      'client': ('127.0.0.1', 12345),
      'server': ('testserver', 80),
      'root_path': '',
      'path_params': {},
    },
    receive,
  )
  request.state.blog_user = {'username': 'author', 'role': 'editor'}
  response = asyncio.run(view.save(request))
  payload = json.loads(response.body)

  assert response.status_code == 201
  assert payload['slug'] == '0031-reserved-adr'
  assert contexts == [request]
