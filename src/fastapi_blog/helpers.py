import datetime
import logging
import os
import pathlib
import threading
from collections.abc import Callable
from typing import Any

import markdown as md  # type: ignore[import-untyped]
import nh3
from pydantic import ValidationError
from pymdownx import emoji  # type: ignore

from . import store
from .models import (
  DEFAULT_SCHEMA,
  LOOSE_DEFAULT_SCHEMA,
  FieldSpec,
  FrontmatterSchema,
  frontmatter_model,
)


logger = logging.getLogger(__name__)

# Pages validate against their own schema with the fields they have always
# had, keeping unknown keys (`extra: 'allow'`); a page that
# doesn't match is still served, with its raw frontmatter (see
# `load_content_from_markdown_file`).
PAGES_SCHEMA = FrontmatterSchema(
  fields=(
    FieldSpec('title', role='title'),
    FieldSpec('description', role='description'),
    FieldSpec('author'),
  ),
  extra='allow',
)


def resolve_schema(
  strict: bool = True, schema: FrontmatterSchema | None = None
) -> FrontmatterSchema:
  """Return the schema in effect: the given one or the built-in default.

  Args:
      strict: Used only when `schema` isn’t given (see `frontmatter_model`).
      schema: Custom frontmatter schema.

  Returns:
      The schema whose roles tell the blog which field means what.

  """
  if schema is not None:
    return schema
  return DEFAULT_SCHEMA if strict else LOOSE_DEFAULT_SCHEMA


def build_post(
  values: dict[str, Any], slug: str, schema: FrontmatterSchema
) -> dict[str, Any]:
  """Build the post dict used by routes and templates.

  The dict has every frontmatter field under its internal name, plus each
  bound role under the role’s own name (for example `post["date"]` is the
  value of the field with the `date` role). Templates only use role names.

  Args:
      values: Validated frontmatter values keyed by internal field name.
      slug: Post slug (the file name without `.md`).
      schema: Frontmatter schema that produced `values`.

  Returns:
      The post dict. `title` falls back to the slug when it’s empty.

  """
  post = dict(values)
  post['slug'] = slug
  for role, name in schema.role_map().items():
    post[role] = values.get(name)
  if not post.get('title'):
    post['title'] = slug
  return post


def _date_sort_key(value: Any) -> str:
  # `datetime` is a subclass of `date`. ISO strings sort like the dates do and
  # stay comparable with plain string dates (and with naive/aware datetimes).
  if isinstance(value, datetime.date):
    return value.isoformat()
  return str(value)


def sort_posts(
  posts: list[dict[str, Any]], schema: FrontmatterSchema
) -> list[dict]:
  """Sort posts: newest first by the `date` role, undated ones last.

  Without a `date` role there is nothing to sort by, so posts are ordered by
  slug. Posts with an empty date come after the dated ones, ordered by slug.

  Args:
      posts: Post dicts made by `build_post`.
      schema: Frontmatter schema in effect.

  Returns:
      A new sorted list.

  """
  if 'date' not in schema.role_map():
    return sorted(posts, key=lambda x: x['slug'])
  dated = [x for x in posts if x.get('date') is not None]
  undated = [x for x in posts if x.get('date') is None]
  dated.sort(key=lambda x: _date_sort_key(x['date']), reverse=True)
  undated.sort(key=lambda x: x['slug'])
  return dated + undated


def _is_published(post: dict[str, Any], schema: FrontmatterSchema) -> bool:
  # `status` generalizes `published`: public iff its value is
  # one of `schema.published_values`. The schema forbids binding both
  # roles on the same schema (see `FrontmatterSchema.__post_init__`).
  roles = schema.role_map()
  if 'status' in roles:
    return post.get(roles['status']) in (schema.published_values or ())
  # Without a `published` role either, there is no draft concept: all
  # posts are public.
  if 'published' not in roles:
    return True
  return bool(post.get('published'))


# Results of `list_posts` keyed by its arguments. Each entry keeps the
# signature of the directory it was built from (see `_cached_by_signature`).
_CACHE_LIMIT = 128
_cache: dict[tuple, tuple[tuple, tuple[dict, ...]]] = {}
_cache_lock = threading.Lock()


def _cached_by_signature(
  key: tuple,
  directory: pathlib.Path,
  pattern: str,
  compute: Callable[[], tuple[dict, ...]],
) -> tuple[dict, ...]:
  """Return `compute()` and reuse it until the directory changes.

  The "signature" of a directory is the sorted tuple of `(name, mtime_ns,
  size)` for the files that match `pattern`. When it differs from the stored
  one, the result is recomputed. There is no TTL and no external service, so
  edits made outside the app are picked up on the next call. This is the only
  place that caches file reads; to add an external cache, wrap this function.

  Args:
      key: Hashable key of the call (the arguments that change the result).
      directory: Directory with the files.
      pattern: Glob pattern of the files that matter.
      compute: Builds the result by reading the files.

  Returns:
      The (possibly cached) result.

  """
  signature: list[tuple[str, int, int]] = []
  try:
    for path in directory.glob(pattern):
      try:
        info = path.stat()
      except OSError:
        continue  # The file vanished between listing and stat
      signature.append((path.name, info.st_mtime_ns, info.st_size))
  except OSError:
    pass
  signature.sort()
  full_key = (os.getcwd(), *key)
  frozen = tuple(signature)
  with _cache_lock:
    cached = _cache.get(full_key)
  if cached is not None and cached[0] == frozen:
    return cached[1]
  # The signature was taken before reading, so a change that happens while we
  # read makes the next call see a different signature and recompute
  result = compute()
  with _cache_lock:
    if len(_cache) >= _CACHE_LIMIT and full_key not in _cache:
      _cache.clear()
    _cache[full_key] = (frozen, result)
  return result


def list_posts(
  published: bool = True,
  posts_dirname: str = 'posts',
  strict: bool = True,
  schema: FrontmatterSchema | None = None,
) -> tuple[dict, ...]:
  """List posts from markdown files, newest first.

  Args:
      published: Return published posts (`True`) or drafts (`False`).
      posts_dirname: Directory with the markdown files.
      strict: Forbid unknown frontmatter keys. Ignored if `schema` is given.
      schema: Custom frontmatter schema. Its roles decide which field is the
          title, date, published flag, tags and description.

  Returns:
      Tuple of post dicts (see `build_post`). Invalid files are skipped.

  """
  return _cached_by_signature(
    (published, posts_dirname, strict, schema),
    pathlib.Path(posts_dirname),
    '*.md',
    lambda: _read_posts(published, posts_dirname, strict, schema),
  )


def clear_posts_cache() -> None:
  """Forget all cached post lists (also `list_posts.cache_clear`)."""
  with _cache_lock:
    _cache.clear()


list_posts.cache_clear = clear_posts_cache  # type: ignore[attr-defined]


def _read_posts(
  published: bool,
  posts_dirname: str,
  strict: bool,
  schema: FrontmatterSchema | None,
) -> tuple[dict, ...]:
  effective = resolve_schema(strict, schema)
  Model = frontmatter_model(strict, schema)
  posts: list[dict] = []
  for post in pathlib.Path(posts_dirname).glob('*.md'):
    try:
      data, _ = store.read_document(post)
    except ValueError as exc:
      logger.warning('Skipping %s: %s', post, exc)
      continue

    try:
      fm = Model(**data)
    except ValidationError as exc:
      logger.warning('Skipping %s: %s', post, exc)
      continue

    posts.append(build_post(fm.model_dump(), post.stem, effective))

  posts = sort_posts(posts, effective)
  return tuple(x for x in posts if _is_published(x, effective) is published)


def load_content_from_markdown_file(
  path: pathlib.Path,
  sanitize: bool = False,
  schema: FrontmatterSchema | None = PAGES_SCHEMA,
) -> dict[str, str | dict]:
  """Render a markdown page from `path`.

  Args:
      path: Markdown file to read.
      sanitize: Sanitize the rendered HTML (as the blog does for posts).
      schema: Frontmatter schema pages validate against; defaults
          to `PAGES_SCHEMA`, the fields pages have always had). Unknown keys
          are kept (`extra: 'allow'`); a page that doesn't match the schema
          is still served, with its raw frontmatter.

  Returns:
      Dict with `metadata`, `markdown` and `html` keys.

  """
  metadata, markdown_text = store.read_document(path)
  if schema is not None:
    try:
      metadata = schema.dump(schema.model()(**metadata))
    except ValidationError as exc:
      logger.warning('Serving %s with raw frontmatter: %s', path, exc)
  page: dict[str, str | dict] = {
    'metadata': metadata,
    'markdown': markdown_text,
    'html': markdown(markdown_text, sanitize=sanitize),
  }
  return page


extensions = [
  'markdown.extensions.tables',
  'toc',  # "markdown.extensions.toc
  # "markdown.extensions.toc",
  'pymdownx.magiclink',
  'pymdownx.betterem',
  'pymdownx.tilde',
  'pymdownx.emoji',
  'pymdownx.tasklist',
  'pymdownx.superfences',
  'pymdownx.saneheaders',
]

extension_configs: dict[str, dict[str, Any]] = {
  'markdown.extensions.toc': {
    'permalink': True,
    'permalink_leading': True,
    'title': 'Tabula Rasa',
  },
  'pymdownx.magiclink': {
    'repo_url_shortener': True,
    'repo_url_shorthand': True,
    'provider': 'github',
    'user': 'facelessuser',
    'repo': 'pymdown-extensions',
  },
  'pymdownx.tilde': {'subscript': False},
  'pymdownx.emoji': {
    'emoji_index': emoji.gemoji,
    'emoji_generator': emoji.to_png,
    'alt': 'short',
    'options': {
      'attributes': {'align': 'absmiddle', 'height': '20px', 'width': '20px'},
      'image_path': 'https://github.githubassets.com/images/icons/emoji/unicode/',
      'non_standard_image_path': 'https://github.githubassets.com/images/icons/emoji/',
    },
  },
  'toc': {
    'title': 'Table of Contents!',  # Title for the table of contents
    'anchorlink': True,  # Add anchor links to the headers
    'permalink': '# ',  # Add permanent links to the headers
    'permalink_leading': True,  # Add permanent links to the headers
  },
}


def markdown(text: str, sanitize: bool = False) -> str:
  html = md.markdown(
    text, extensions=extensions, extension_configs=extension_configs
  )
  if sanitize:
    html = nh3.clean(html)
  return html
