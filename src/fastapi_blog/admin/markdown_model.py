"""Virtual model adapter for markdown posts stored as files.

This module provides an ORM-like interface for markdown files,
allowing starlette-admin to work with file-based posts.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .. import store


class MarkdownPost:
  """Virtual model representing a markdown post stored as a file.

  This acts as an ORM model but reads/writes to markdown files
  instead of a database.
  """

  # Class-level storage for posts directory
  _posts_dir: Path | None = None

  def __init__(
    self,
    slug: str,
    title: str = '',
    content: str = '',
    date: datetime | None = None,
    published: bool = False,
    tags: list[str] | None = None,
    **extra_frontmatter: Any,
  ):
    """Initialize a markdown post.

    Args:
        slug: URL-safe identifier (also filename without .md)
        title: Post title
        content: Markdown content
        date: Publication date
        published: Whether post is published
        tags: List of tags
        **extra_frontmatter: Additional frontmatter fields

    """
    self.slug = slug
    self.title = title
    self.content = content
    self.date = date
    self.published = published
    self.tags = tags or []
    self.extra_frontmatter = extra_frontmatter

  @classmethod
  def configure(cls, posts_dir: str | Path) -> None:
    """Configure the posts directory.

    Args:
        posts_dir: Path to directory containing markdown files

    """
    cls._posts_dir = Path(posts_dir)
    cls._posts_dir.mkdir(parents=True, exist_ok=True)

  @classmethod
  def get_posts_dir(cls) -> Path:
    """Get the configured posts directory.

    Raises:
        RuntimeError: If posts directory not configured

    """
    if cls._posts_dir is None:
      raise RuntimeError(
        'Posts directory not configured. '
        'Call MarkdownPost.configure(posts_dir) first.'
      )
    return cls._posts_dir

  @classmethod
  def get_file_path(cls, slug: str) -> Path:
    """Get file path for a post by slug."""
    return cls.get_posts_dir() / f'{slug}.md'

  @classmethod
  def exists(cls, slug: str) -> bool:
    """Check if a post exists."""
    return cls.get_file_path(slug).exists()

  @classmethod
  def list_all(cls) -> list['MarkdownPost']:
    """List all markdown posts.

    Returns:
        List of MarkdownPost objects sorted by date (newest first)

    """
    posts = []
    posts_dir = cls.get_posts_dir()

    for file_path in posts_dir.glob('*.md'):
      try:
        post = cls.load_from_file(file_path.stem)
        posts.append(post)
      except Exception as e:
        # Log error but continue with other posts
        print(f'Error loading {file_path}: {e}')

    # Sort by date, newest first. ISO strings compare the same way the dates
    # do, stay comparable across naive/aware datetimes, and sort undated
    # posts (empty string) last.
    posts.sort(key=lambda p: p.date.isoformat() if p.date else '', reverse=True)
    return posts

  @classmethod
  def load_from_file(cls, slug: str) -> 'MarkdownPost':
    """Load a post from markdown file.

    Args:
        slug: Post slug (filename without .md)

    Returns:
        MarkdownPost object

    Raises:
        FileNotFoundError: If post doesn't exist
        ValueError: If markdown format is invalid

    """
    file_path = cls.get_file_path(slug)

    if not file_path.exists():
      raise FileNotFoundError(f'Post not found: {slug}')

    try:
      frontmatter, body = store.read_document(file_path)
    except ValueError as e:
      raise ValueError(f'{slug}: {e}') from e
    body = body.strip()

    # Extract known fields (remove from frontmatter to avoid conflicts)
    # Remove slug from frontmatter if present (slug comes from filename)
    frontmatter.pop('slug', None)

    title = frontmatter.pop('title', slug.replace('-', ' ').title())
    date_value = frontmatter.pop('date', None)

    # Parse date; a missing or unparsable date stays `None` rather than
    # being invented, since callers already treat `None` as "undated"
    if isinstance(date_value, datetime):
      date = date_value
    elif isinstance(date_value, str):
      try:
        date = datetime.fromisoformat(date_value)
      except ValueError:
        date = None
    else:
      date = None

    published = frontmatter.pop('published', False)
    tags = frontmatter.pop('tags', [])

    # Ensure tags is a list
    if isinstance(tags, str):
      tags = [t.strip() for t in tags.split(',')]

    return cls(
      slug=slug,
      title=title,
      content=body,
      date=date,
      published=published,
      tags=tags,
      **frontmatter,  # Pass through any extra fields
    )

  def save_to_file(self) -> None:
    """Save post to markdown file."""
    # Validate slug
    if not self.slug or not re.match(r'^[a-z0-9-]+$', self.slug):
      raise ValueError(
        f'Invalid slug: {self.slug}. '
        'Must contain only lowercase letters, numbers, and hyphens.'
      )

    # Prepare frontmatter. A missing date is left out rather than invented.
    frontmatter: dict[str, Any] = {'title': self.title}
    if self.date is not None:
      frontmatter['date'] = (
        self.date.isoformat() if isinstance(self.date, datetime) else self.date
      )
    frontmatter['published'] = self.published

    if self.tags:
      frontmatter['tags'] = self.tags

    # Add any extra frontmatter fields
    frontmatter.update(self.extra_frontmatter)

    # Write to file
    file_path = self.get_file_path(self.slug)
    store.write_document(file_path, frontmatter, f'\n{self.content}')

  def delete(self) -> None:
    """Delete post file."""
    file_path = self.get_file_path(self.slug)
    if file_path.exists():
      file_path.unlink()

  def to_dict(self) -> dict[str, Any]:
    """Convert post to dictionary."""
    return {
      'slug': self.slug,
      'title': self.title,
      'content': self.content,
      'date': self.date,
      'published': self.published,
      'tags': self.tags,
      **self.extra_frontmatter,
    }

  def __repr__(self) -> str:
    return f"<MarkdownPost(slug='{self.slug}', title='{self.title}', published={self.published})>"
