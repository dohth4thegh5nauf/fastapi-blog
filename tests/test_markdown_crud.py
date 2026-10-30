"""Tests for MarkdownFileManager's slug/path safety."""

import pytest

from fastapi_blog.admin.markdown_crud import MarkdownFileManager


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
  manager.save_post('hello-world', {'title': 'Hello'}, 'Body text')

  post = manager.load_post('hello-world')
  assert post is not None
  assert post.title == 'Hello'
