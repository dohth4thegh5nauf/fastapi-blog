"""Shared primitives for reading and writing frontmatter documents.

A single place to parse and serialize `---`-delimited YAML frontmatter, so
that a `---` inside the body (a Markdown table like `|---|---|`, a setext
heading underline, a horizontal rule) or inside a YAML value never corrupts
the document, and every write goes through the same atomic, UTF-8 path.

This module intentionally knows nothing about posts, schemas or roles: it only
parses/serializes/writes files. Callers that need a `Collection` abstraction,
etags or `If-Match` concurrency build on top of `atomic_write_text` and
`compute_etag` (see `TODO.md`, phase B); that layer isn't built yet.
"""

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import yaml


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
