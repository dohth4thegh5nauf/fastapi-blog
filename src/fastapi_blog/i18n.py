"""Multi-locale document storage primitives.

This module is deliberately optional: collections which do not construct an
I18nCollection continue to use :mod:`fastapi_blog.store` unchanged.
"""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from . import store

_LOCALE_RE = re.compile(r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")


class I18nConfigError(ValueError):
  """Invalid multi-locale collection configuration."""


@dataclass(frozen=True)
class I18nConfig:
  locales: tuple[str, ...]
  default_locale: str
  structure: str = 'multiple_files'
  omit_default_locale_suffix: bool = True
  fallback: str = 'default'
  translate_body: bool = False

  def __post_init__(self) -> None:
    if not self.locales:
      raise I18nConfigError('i18n.locales must contain at least one locale')
    if len(set(self.locales)) != len(self.locales):
      raise I18nConfigError('i18n.locales must be unique')
    invalid = [locale for locale in self.locales if not _LOCALE_RE.fullmatch(locale)]
    if invalid:
      raise I18nConfigError(f'Invalid BCP 47-like locale(s): {invalid!r}')
    if self.default_locale not in self.locales:
      raise I18nConfigError('i18n.default_locale must be included in locales')
    if self.structure not in ('multiple_files', 'multiple_folders'):
      if self.structure == 'single_file':
        raise I18nConfigError('i18n.structure=single_file is not supported')
      raise I18nConfigError(f'Unknown i18n.structure: {self.structure!r}')
    if self.fallback not in ('default', 'none'):
      raise I18nConfigError("i18n.fallback must be 'default' or 'none'")
    if self.structure == 'multiple_folders' and self.omit_default_locale_suffix:
      object.__setattr__(self, 'omit_default_locale_suffix', False)


@dataclass(frozen=True)
class LocalizedDocument:
  slug: str
  locale: str
  frontmatter: dict[str, Any]
  body: str
  etag: str
  path: Path


@dataclass(frozen=True)
class LocalizedEntry:
  slug: str
  canonical: LocalizedDocument
  locales_present: tuple[str, ...]
  entry_etag: str


class I18nCollection:
  """Filesystem store for translations sharing one canonical slug.

  Multi-file layout: ``<slug>.<locale>.<ext>`` (optionally unsuffixed
  default locale). Multi-folder layout: ``<locale>/<slug>.<ext>``.
  All mutations are guarded by a per-instance reentrant lock.
  """

  def __init__(self, collection: store.Collection, config: I18nConfig):
    if collection.depth:
      raise I18nConfigError('i18n is not supported with nested collections')
    self.collection = collection
    self.config = config
    self._lock = threading.RLock()

  def path_for(self, slug: str, locale: str) -> Path:
    if locale not in self.config.locales:
      raise I18nConfigError(f'Unknown locale {locale!r}')
    if not self.collection.slug_pattern.fullmatch(slug):
      raise store.InvalidSlugError(f'Invalid slug: {slug!r}')
    ext = self.collection.extensions[0]
    if self.config.structure == 'multiple_folders':
      path = self.collection.dir / locale / f'{slug}.{ext}'
      return path
    suffix = '' if locale == self.config.default_locale and self.config.omit_default_locale_suffix else f'.{locale}'
    return self.collection.dir / f'{slug}{suffix}.{ext}'

  def _all_paths(self, slug: str) -> dict[str, Path]:
    result = {}
    for locale in self.config.locales:
      path = self.path_for(slug, locale)
      if path.is_file():
        result[locale] = path
    return result

  def list(self) -> list[LocalizedEntry]:
    slugs: set[str] = set()
    ext = self.collection.extensions[0]
    if self.config.structure == 'multiple_folders':
      for locale in self.config.locales:
        folder = self.collection.dir / locale
        if folder.is_dir():
          slugs.update(p.stem for p in folder.glob(f'*.{ext}') if p.is_file())
    else:
      if self.collection.dir.is_dir():
        for path in self.collection.dir.glob(f'*.{ext}'):
          stem = path.stem
          locale = next((x for x in self.config.locales if stem.endswith('.' + x)), None)
          slugs.add(stem[:-(len(locale) + 1)] if locale else stem)
    entries = []
    for slug in sorted(slugs):
      paths = self._all_paths(slug)
      if self.config.default_locale not in paths:
        continue
      canonical = self.read(slug, self.config.default_locale)
      digest = hashlib.sha256(''.join(f'{k}:{self.read(slug,k).etag};' for k in sorted(paths)).encode()).hexdigest()
      entries.append(LocalizedEntry(slug, canonical, tuple(sorted(paths)), digest))
    return entries

  def read(self, slug: str, locale: str, *, fallback: bool | None = None) -> LocalizedDocument:
    path = self.path_for(slug, locale)
    used_locale = locale
    if not path.is_file() and (fallback if fallback is not None else self.config.fallback == 'default'):
      used_locale = self.config.default_locale
      path = self.path_for(slug, used_locale)
    if not path.is_file():
      raise store.NotFoundError(f'{slug!r} has no {locale!r} translation')
    frontmatter, body = store.read_document(path)
    text = path.read_text(encoding='utf-8')
    return LocalizedDocument(slug, used_locale, frontmatter, body, store.compute_etag(text), path)

  def save_entry(
    self,
    slug: str,
    documents: Mapping[str, tuple[Mapping[str, Any], str]],
    *,
    if_match: Mapping[str, str] | str | None = None,
    expected_entry_etag: str | None = None,
  ) -> dict[str, str]:
    """Atomically replace the supplied locales; restore all old bytes on error."""
    if not documents:
      raise ValueError('At least one locale document is required')
    unknown = set(documents) - set(self.config.locales)
    if unknown:
      raise I18nConfigError(f'Unknown locale(s): {sorted(unknown)!r}')
    with self._lock:
      current = self._all_paths(slug)
      if expected_entry_etag is not None:
        current_hash = hashlib.sha256(''.join(f'{k}:{self.read(slug,k).etag};' for k in sorted(current)).encode()).hexdigest() if current else None
        if current_hash != expected_entry_etag:
          raise store.ConflictError('entry etag does not match', status_code=412)
      targets: dict[str, Path] = {}
      old: dict[Path, bytes | None] = {}
      staged: dict[Path, Path] = {}
      for locale, (frontmatter, body) in documents.items():
        target = self.path_for(slug, locale)
        targets[locale] = target
        previous = target.read_bytes() if target.exists() else None
        old[target] = previous
        expected = if_match.get(locale) if isinstance(if_match, Mapping) else if_match
        if expected is not None:
          actual = store.compute_etag(previous.decode('utf-8')) if previous is not None else None
          if actual != expected:
            raise store.ConflictError(f'{locale} etag does not match', status_code=412)
        if previous is None and not self.collection.create:
          raise store.OperationNotAllowedError('Creating documents is disabled')
        text = store.serialize_document(dict(frontmatter), body)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=f'.{target.name}.', suffix='.tmp', dir=target.parent)
        tmp = Path(tmp_name)
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as stream:
          stream.write(text)
          stream.flush()
          os.fsync(stream.fileno())
        staged[target] = tmp
      committed: list[Path] = []
      try:
        for target, tmp in staged.items():
          os.replace(tmp, target)
          committed.append(target)
      except OSError:
        for target in reversed(committed):
          previous = old[target]
          if previous is None:
            target.unlink(missing_ok=True)
          else:
            target.write_bytes(previous)
        raise
      finally:
        for tmp in staged.values():
          tmp.unlink(missing_ok=True)
      return {locale: store.compute_etag(target.read_text(encoding='utf-8')) for locale, target in targets.items()}

  def delete_locale(self, slug: str, locale: str) -> None:
    if locale == self.config.default_locale and any(k != locale for k in self._all_paths(slug)):
      raise ValueError('Deleting the canonical locale requires cascade=True')
    with self._lock:
      path = self.path_for(slug, locale)
      if path.exists():
        path.unlink()

  def delete_entry(self, slug: str, *, cascade: bool = False) -> None:
    with self._lock:
      paths = self._all_paths(slug)
      if self.config.default_locale in paths and len(paths) > 1 and not cascade:
        raise ValueError('Deleting the canonical entry with translations requires cascade=True')
      for path in paths.values():
        path.unlink(missing_ok=True)

  def rename(self, old_slug: str, new_slug: str) -> None:
    with self._lock:
      paths = self._all_paths(old_slug)
      if not paths:
        raise store.NotFoundError(old_slug)
      destinations = {locale: self.path_for(new_slug, locale) for locale in paths}
      if any(path.exists() for path in destinations.values()):
        raise store.ConflictError(f'{new_slug!r} already exists', status_code=409)
      moved: list[tuple[Path, Path]] = []
      try:
        for locale, source in paths.items():
          target = destinations[locale]
          os.replace(source, target)
          moved.append((source, target))
      except OSError:
        for source, target in reversed(moved):
          os.replace(target, source)
        raise
