"""Tests for MarkdownPost virtual model."""

import pytest

from fastapi_blog.admin.markdown_model import MarkdownPost


@pytest.fixture
def posts_dir(tmp_path):
  """Create temporary posts directory."""
  posts_dir = tmp_path / 'posts'
  posts_dir.mkdir()
  MarkdownPost.configure(posts_dir)
  yield posts_dir
  MarkdownPost._posts_dir = None


def test_configure_posts_dir(tmp_path):
  """Test configuring posts directory."""
  posts_dir = tmp_path / 'test_posts'
  MarkdownPost.configure(posts_dir)

  assert MarkdownPost.get_posts_dir() == posts_dir
  assert posts_dir.exists()


def test_create_and_save_post(posts_dir):
  """Test creating and saving a post."""
  post = MarkdownPost(
    slug='test-post',
    title='Test Post',
    content='This is test content',
    published=True,
    tags=['test', 'demo'],
  )

  post.save_to_file()

  # Check file exists
  file_path = posts_dir / 'test-post.md'
  assert file_path.exists()

  # Check content
  content = file_path.read_text()
  assert 'title: Test Post' in content
  assert 'published: true' in content
  assert 'This is test content' in content


def test_load_from_file(posts_dir):
  """Test loading post from file."""
  # Create a test file
  test_file = posts_dir / 'hello-world.md'
  test_file.write_text("""---
title: Hello World
date: '2024-01-01T10:00:00'
published: true
tags:
  - hello
  - world
---

This is the content.""")

  post = MarkdownPost.load_from_file('hello-world')

  assert post.slug == 'hello-world'
  assert post.title == 'Hello World'
  assert post.content == 'This is the content.'
  assert post.published is True
  assert 'hello' in post.tags
  assert 'world' in post.tags


def test_list_all_posts(posts_dir):
  """Test listing all posts."""
  # Create multiple posts
  for i in range(3):
    post = MarkdownPost(
      slug=f'post-{i}', title=f'Post {i}', content=f'Content {i}'
    )
    post.save_to_file()

  posts = MarkdownPost.list_all()

  assert len(posts) == 3
  assert all(isinstance(p, MarkdownPost) for p in posts)


def test_exists(posts_dir):
  """Test checking if post exists."""
  assert not MarkdownPost.exists('nonexistent')

  post = MarkdownPost(slug='existing', title='Test', content='Test')
  post.save_to_file()

  assert MarkdownPost.exists('existing')


def test_delete_post(posts_dir):
  """Test deleting a post."""
  post = MarkdownPost(slug='to-delete', title='Delete Me', content='Test')
  post.save_to_file()

  assert MarkdownPost.exists('to-delete')

  post.delete()

  assert not MarkdownPost.exists('to-delete')


def test_invalid_slug(posts_dir):
  """Test that invalid slugs are rejected."""
  post = MarkdownPost(slug='Invalid Slug!', title='Test', content='Test')

  with pytest.raises(ValueError, match='Invalid slug'):
    post.save_to_file()


def test_path_traversal_slug_is_rejected(posts_dir, tmp_path):
  """A slug built from `..` segments must never escape posts_dir.

  `get_file_path` routes through `store.safe_document_path`, which checks
  the slug pattern (no `/` or `.` allowed) and the resolved path's
  containment, so this can never reach a file outside `posts_dir`.
  """
  secret = tmp_path / 'secret.md'
  secret.write_text('---\ntitle: Secret\n---\n', encoding='utf-8')

  post = MarkdownPost(
    slug='../secret', title='Should Not Write', content='pwned'
  )
  with pytest.raises(ValueError, match='Invalid slug'):
    post.save_to_file()
  assert secret.read_text(encoding='utf-8') == '---\ntitle: Secret\n---\n'

  assert not MarkdownPost.exists('../secret')


def test_to_dict(posts_dir):
  """Test converting post to dictionary."""
  post = MarkdownPost(
    slug='test', title='Test', content='Content', published=True, tags=['test']
  )

  data = post.to_dict()

  assert data['slug'] == 'test'
  assert data['title'] == 'Test'
  assert data['content'] == 'Content'
  assert data['published'] is True
  assert 'test' in data['tags']


def test_extra_frontmatter(posts_dir):
  """Test handling extra frontmatter fields."""
  post = MarkdownPost(
    slug='extra',
    title='Extra Fields',
    content='Content',
    author='John Doe',
    category='News',
  )

  post.save_to_file()
  loaded = MarkdownPost.load_from_file('extra')

  assert loaded.extra_frontmatter['author'] == 'John Doe'
  assert loaded.extra_frontmatter['category'] == 'News'
