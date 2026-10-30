"""Shared primitives for reading and writing frontmatter documents.

A single place to parse and serialize `---`-delimited YAML frontmatter, so
that a `---` inside the body (a Markdown table like `|---|---|`, a setext
heading underline, a horizontal rule) or inside a YAML value never corrupts
the document, and every write goes through the same atomic, UTF-8 path.

The low-level functions (`parse_document`, `serialize_document`,
`atomic_write_text`, `read_document`, `write_document`, `safe_document_path`,
`compute_etag`) know nothing about posts, schemas or roles. `Collection` and
`DocumentStore` are the one layer above that does: a directory of same-shaped
documents, with path safety, `if_match` concurrency and `create`/`delete`
permissions built in (see `TODO.md`, phase B, 4.1/4.6/4.7). Every caller that
turns a slug into a file (the blog, the REST API, the admin panel) goes
through a `DocumentStore`.
"""

import dataclasses
import hashlib
import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Any

import yaml


# Default slug shape when a `Collection` doesn't set its own `slug_pattern`:
# lowercase letters, digits and hyphens, starting with a letter or digit, up
# to 100 characters. Kept local (not imported from `models`) so this module
# stays free of any dependency on the schema/validation layer above it.
DEFAULT_SLUG_PATTERN = re.compile(r'^[a-z0-9][a-z0-9-]{0,99}$')


def parse_document(text: str) -> tuple[dict[str, Any], str]:
  """Split a file's text into frontmatter and body.

  The frontmatter is the block between the first line that is `---` (a
  leading BOM is skipped) and the nearest following line that is `---` or
  `...`. Everything after that closing line is the body, byte for byte: a
  `---` inside a table, a YAML value or anywhere else in the body never
  affects the split, because only the *first* document's lines are scanned.

  A file that doesn't open with `---` has empty frontmatter and the whole
  file is the body.

  Args:
      text: The file's full text (already decoded).

  Returns:
      `(frontmatter, body)`. `frontmatter` is `{}` when there is none or it
      is empty; otherwise it is the parsed YAML mapping.

  Raises:
      ValueError: The frontmatter block isn't valid YAML, or isn't a mapping.

  """
  if text.startswith('﻿'):
    text = text[1:]
  lines = text.splitlines(keepends=True)
  if not lines or lines[0].rstrip('\r\n') != '---':
    return {}, text

  end = None
  for i in range(1, len(lines)):
    if lines[i].rstrip('\r\n') in ('---', '...'):
      end = i
      break
  if end is None:
    # No closing marker: there is no well-formed frontmatter block, so the
    # whole file is the body (nothing to guess at).
    return {}, text

  fm_text = ''.join(lines[1:end])
  try:
    data = yaml.safe_load(fm_text)
  except yaml.YAMLError as exc:
    raise ValueError(f'invalid YAML frontmatter: {exc}') from exc
  if data is None:
    data = {}
  if not isinstance(data, dict):
    raise ValueError('frontmatter is not a mapping')

  body = ''.join(lines[end + 1 :])
  return data, body


def serialize_document(frontmatter: dict[str, Any], body: str) -> str:
  r"""Render frontmatter and body back into a file's text.

  Args:
      frontmatter: Mapping to dump as YAML (empty dict writes no fields).
      body: Document body, written byte for byte after the closing `---`.

  Returns:
      The full file text, `\n`-terminated frontmatter lines, UTF-8 safe.

  """
  fm_yaml = (
    yaml.safe_dump(
      frontmatter, sort_keys=False, allow_unicode=True, default_flow_style=False
    )
    if frontmatter
    else ''
  )
  return f'---\n{fm_yaml}---\n{body}'


def read_document(path: Path) -> tuple[dict[str, Any], str]:
  """Read and parse a document file as UTF-8.

  Args:
      path: File to read.

  Returns:
      `(frontmatter, body)`, see `parse_document`.

  """
  return parse_document(path.read_text(encoding='utf-8'))


def atomic_write_text(path: Path, text: str) -> None:
  r"""Write `text` to `path` as UTF-8, atomically.

  Writes to a temporary file in the same directory and `os.replace()`s it
  into place, so readers never see a partial write. The temp file is cleaned
  up if anything goes wrong before the replace.

  Args:
      path: Destination file. Its parent directory must already exist.
      text: Text to write, `\n` line endings.

  """
  fd, tmp_name = tempfile.mkstemp(
    dir=str(path.parent), prefix=f'.{path.name}.', suffix='.tmp'
  )
  try:
    with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
      f.write(text)
    os.replace(tmp_name, path)
  except BaseException:
    try:
      os.unlink(tmp_name)
    except OSError:
      pass
    raise


def write_document(path: Path, frontmatter: dict[str, Any], body: str) -> None:
  """Serialize and atomically write a document (see `serialize_document`)."""
  atomic_write_text(path, serialize_document(frontmatter, body))


def safe_document_path(
  directory: Path, slug: str, *, pattern: re.Pattern[str], suffix: str = '.md'
) -> Path:
  """Resolve `slug` to a file path inside `directory`, or raise.

  Args:
      directory: Collection directory the file must stay inside.
      slug: Candidate slug, checked against `pattern` first.
      pattern: Compiled regex the whole slug must match.
      suffix: File extension.

  Returns:
      The file path (not required to exist).

  Raises:
      ValueError: `slug` doesn't match `pattern`, or the resolved path (after
          following any symlinks) would land outside `directory`.

  """
  if not pattern.fullmatch(slug):
    raise ValueError(f'invalid slug: {slug!r}')
  base = directory.resolve()
  candidate = (directory / f'{slug}{suffix}').resolve()
  if candidate != base and base not in candidate.parents:
    raise ValueError(f'slug escapes the collection directory: {slug!r}')
  return directory / f'{slug}{suffix}'


def compute_etag(text: str) -> str:
  """Return the content hash used as a document's etag."""
  return hashlib.sha256(text.encode('utf-8')).hexdigest()


class ConflictError(Exception):
  """A `DocumentStore.write`/`delete` precondition wasn't met.

  Attributes:
      status_code: The HTTP status a REST API should answer with: `409` when
          the document a caller expected to exist (via `if_match`) doesn't,
          or already exists on a create; `412` when it exists but its current
          etag doesn't match `if_match`.

  """

  def __init__(self, message: str, *, status_code: int) -> None:
    """Initialize with a message and the HTTP status code it maps to."""
    super().__init__(message)
    self.status_code = status_code


@dataclasses.dataclass(frozen=True)
class DocumentRecord:
  """A document as read from a `DocumentStore`.

  Attributes:
      slug: The document's slug.
      frontmatter: Parsed frontmatter (see `parse_document`).
      body: Document body.
      etag: Content hash of the whole file at read time (see `compute_etag`);
          pass back as `if_match` to `write`/`delete` to detect a concurrent
          change.

  """

  slug: str
  frontmatter: dict[str, Any]
  body: str
  etag: str


@dataclasses.dataclass(frozen=True)
class Collection:
  """A directory of same-shaped documents.

  Bundles the storage-layer rules from TODO 4.4–4.7: slug pattern and
  path-containment safety (`safe_document_path`), which file extensions are
  read and which one new documents are written with, and whether creating or
  deleting documents is allowed at all. A `DocumentStore` is built on one.

  This deliberately does *not* carry a `FrontmatterSchema` (unlike the literal
  `Collection(name, dir, schema, ...)` signature sketched in `TODO.md` 4.6):
  keeping the storage layer free of the Pydantic/schema layer above it avoids
  a layering inversion. Field validation and the `on_create`/`read_only`
  rules already live in `FrontmatterSchema.dump_for_write`; callers run that
  first and pass `DocumentStore.write` the resulting plain dict.

  Attributes:
      name: Collection name, used only in error messages.
      dir: Directory holding the documents. Only created on the first write
          (see `atomic_write_text`), never just by reading or listing.
      slug_pattern: Compiled regex the whole slug must match (default:
          lowercase letters, digits, hyphens, max 100 chars, see
          `DEFAULT_SLUG_PATTERN`).
      extension: One file extension, or several to also read/list (the first
          is what new documents are written with), without the leading dot.
      depth: Nested-collection depth. Only `0` (flat, no subdirectories) is
          implemented so far; anything else raises `NotImplementedError`
          (TODO 4.6 is not done).
      create: When `False`, `DocumentStore.write` refuses to create a new
          document (an existing one can still be rewritten).
      delete: When `False`, `DocumentStore.delete` always refuses.

  """

  name: str
  dir: Path
  slug_pattern: re.Pattern[str] = DEFAULT_SLUG_PATTERN
  extension: str | tuple[str, ...] = 'md'
  depth: int = 0
  create: bool = True
  delete: bool = True

  def __post_init__(self) -> None:
    object.__setattr__(self, 'dir', Path(self.dir))
    if not self.extensions:
      raise ValueError(f'collection {self.name!r} needs at least one extension')
    if self.depth != 0:
      raise NotImplementedError(
        f'collection {self.name!r}: depth > 0 (nested collections) is not '
        'implemented yet (see TODO.md, 4.6)'
      )

  @property
  def extensions(self) -> tuple[str, ...]:
    """Normalized extensions (no leading dot), as a tuple."""
    raw = (
      (self.extension,) if isinstance(self.extension, str) else self.extension
    )
    return tuple(ext.removeprefix('.') for ext in raw)


class DocumentStore:
  """`list`/`read`/`write`/`delete`/`exists` over one `Collection`.

  Every caller that turns a slug into a document on disk (the blog, the REST
  API, the admin panel) should go through a `DocumentStore` instead of
  building paths itself, so slug/path safety, `if_match` concurrency and
  `create`/`delete` permissions are enforced in exactly one place.

  Writes are protected by an in-process lock scoped to this instance (one
  `DocumentStore` per collection is expected to be shared by all callers in
  the process); there is no cross-process locking (TODO 4.7 explicitly rules
  it out).
  """

  def __init__(self, collection: Collection) -> None:
    """Initialize a store over `collection`."""
    self.collection = collection
    self._lock = threading.Lock()

  def _candidate(self, slug: str, ext: str) -> Path:
    return safe_document_path(
      self.collection.dir,
      slug,
      pattern=self.collection.slug_pattern,
      suffix=f'.{ext}',
    )

  def path_for(self, slug: str) -> Path | None:
    """Return the on-disk path of `slug`'s document, trying each extension.

    `None` when no file matches (not an error); raises when the slug itself
    is invalid, which every public method below relies on to reject a bad
    slug before touching the filesystem.

    Raises:
        ValueError: `slug` is invalid (see `safe_document_path`); checked
            once regardless of how many extensions are configured.

    """
    candidates = [
      self._candidate(slug, ext) for ext in self.collection.extensions
    ]
    for candidate in candidates:
      if candidate.is_file():
        return candidate
    return None

  def list(self) -> list[str]:
    """Return the slug of every document in the collection, in no particular order."""
    if not self.collection.dir.is_dir():
      return []
    slugs: list[str] = []
    for ext in self.collection.extensions:
      slugs.extend(path.stem for path in self.collection.dir.glob(f'*.{ext}'))
    return slugs

  def exists(self, slug: str) -> bool:
    """Return whether a document with this slug exists.

    An invalid slug simply doesn't exist, rather than raising.
    """
    try:
      return self.path_for(slug) is not None
    except ValueError:
      return False

  def read(self, slug: str) -> DocumentRecord:
    """Read and parse a document by slug.

    Raises:
        ValueError: `slug` is invalid.
        FileNotFoundError: No document with this slug exists.

    """
    path = self.path_for(slug)
    if path is None:
      raise FileNotFoundError(f'document not found: {slug!r}')
    text = path.read_text(encoding='utf-8')
    frontmatter, body = parse_document(text)
    return DocumentRecord(
      slug=slug, frontmatter=frontmatter, body=body, etag=compute_etag(text)
    )

  def write(
    self,
    slug: str,
    frontmatter: dict[str, Any],
    body: str,
    *,
    if_match: str | None = None,
  ) -> str:
    """Create or overwrite a document by slug. Returns its new etag.

    Args:
        slug: Document slug.
        frontmatter: Frontmatter to write (by external key/alias).
        body: Document body.
        if_match: When given, the write only proceeds if it equals the
            document's current etag (from a prior `read`); pass the literal
            etag of a document you know doesn't exist yet to require that it
            still doesn't.

    Raises:
        ValueError: `slug` is invalid or escapes the collection directory.
        PermissionError: The document doesn't exist yet and
            `collection.create` is `False`.
        ConflictError: `if_match` doesn't match the document's current state:
            409 if the document doesn't exist, 412 if it exists with a
            different etag.

    """
    existing_path = self.path_for(slug)
    if if_match is not None:
      if existing_path is None:
        raise ConflictError(
          f'document {slug!r} does not exist', status_code=409
        )
      current_etag = compute_etag(existing_path.read_text(encoding='utf-8'))
      if if_match != current_etag:
        raise ConflictError(f'etag mismatch for {slug!r}', status_code=412)
    if existing_path is None and not self.collection.create:
      raise PermissionError(
        f'collection {self.collection.name!r} does not allow creating new documents'
      )
    # An update keeps whatever extension the document was already stored
    # with; only a new document picks the collection's primary extension.
    target = existing_path or self._candidate(
      slug, self.collection.extensions[0]
    )
    text = serialize_document(frontmatter, body)
    with self._lock:
      target.parent.mkdir(parents=True, exist_ok=True)
      atomic_write_text(target, text)
    return compute_etag(text)

  def delete(self, slug: str, *, if_match: str | None = None) -> None:
    """Delete a document by slug.

    Args:
        slug: Document slug.
        if_match: When given, the delete only proceeds if it equals the
            document's current etag.

    Raises:
        ValueError: `slug` is invalid.
        PermissionError: `collection.delete` is `False`.
        FileNotFoundError: No document with this slug exists.
        ConflictError: 412, `if_match` doesn't match the document's current
            etag.

    """
    if not self.collection.delete:
      raise PermissionError(
        f'collection {self.collection.name!r} does not allow deleting documents'
      )
    path = self.path_for(slug)
    if path is None:
      raise FileNotFoundError(f'document not found: {slug!r}')
    if if_match is not None:
      current_etag = compute_etag(path.read_text(encoding='utf-8'))
      if if_match != current_etag:
        raise ConflictError(f'etag mismatch for {slug!r}', status_code=412)
    with self._lock:
      path.unlink()
