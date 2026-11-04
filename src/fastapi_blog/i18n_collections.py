"""Multi-locale document storage primitives.

This module is deliberately optional: collections which do not construct an
I18nCollection continue to use :mod:`fastapi_blog.store` unchanged.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import store


_LOCALE_RE = re.compile(r'^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$')


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
  required_in_translations: bool = False
  write_duplicates: bool = False

  def __post_init__(self) -> None:
    if not self.locales:
      raise I18nConfigError('i18n.locales must contain at least one locale')
    invalid = [
      locale
      for locale in self.locales
      if not isinstance(locale, str) or not _LOCALE_RE.fullmatch(locale)
    ]
    if invalid:
      raise I18nConfigError(f'Invalid BCP 47-like locale(s): {invalid!r}')
    if len(set(self.locales)) != len(self.locales):
      raise I18nConfigError('i18n.locales must be unique')
    if self.default_locale not in self.locales:
      raise I18nConfigError('i18n.default_locale must be included in locales')
    if self.structure not in ('multiple_files', 'multiple_folders'):
      if self.structure == 'single_file':
        raise I18nConfigError('i18n.structure=single_file is not supported')
      raise I18nConfigError(f'Unknown i18n.structure: {self.structure!r}')
    if not isinstance(self.omit_default_locale_suffix, bool):
      raise I18nConfigError(
        'i18n.omit_default_locale_suffix must be true or false'
      )
    for name in (
      'translate_body',
      'required_in_translations',
      'write_duplicates',
    ):
      if not isinstance(getattr(self, name), bool):
        raise I18nConfigError(f'i18n.{name} must be true or false')
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
  default locale). Locale-directory layout: ``<locale>/<slug>.<ext>``.
  Mutations share an in-process lock for the collection directory.
  """

  def __init__(
    self,
    collection: store.Collection,
    config: I18nConfig,
    *,
    lock: Any = None,
  ):
    """Bind the collection to its locale configuration."""
    if collection.depth:
      raise I18nConfigError('i18n is not supported with nested collections')
    self.collection = collection
    self.config = config
    self._lock = (
      lock if lock is not None else store.collection_lock(collection.dir)
    )

  def path_for(
    self, slug: str, locale: str, *, extension: str | None = None
  ) -> Path:
    if locale not in self.config.locales:
      raise I18nConfigError(f'Unknown locale {locale!r}')
    pattern = self.collection.slug_pattern
    if isinstance(pattern, str):
      pattern = re.compile(pattern)
    if not pattern.fullmatch(slug):
      raise store.InvalidSlugError(f'Invalid slug: {slug!r}')
    base = self.collection.dir.resolve()
    extensions = (extension,) if extension else self.collection.extensions
    if any(ext not in self.collection.extensions for ext in extensions):
      raise I18nConfigError(f'Unsupported document extension: {extension!r}')
    paths = []
    for ext in extensions:
      if self.config.structure == 'multiple_folders':
        path = self.collection.dir / locale / f'{slug}.{ext}'
      else:
        suffix = (
          ''
          if locale == self.config.default_locale
          and self.config.omit_default_locale_suffix
          else f'.{locale}'
        )
        path = self.collection.dir / f'{slug}{suffix}.{ext}'
      resolved = path.resolve()
      if resolved != base and base not in resolved.parents:
        raise store.InvalidSlugError(
          f'localized document path escapes the collection directory: {slug!r}'
        )
      paths.append(path)
    existing = [path for path in paths if path.is_file()]
    if len(existing) > 1:
      raise store.ConflictError(
        f'Multiple files for {slug!r}/{locale!r}', status_code=409
      )
    return existing[0] if existing else paths[0]

  def _all_paths(self, slug: str) -> dict[str, Path]:
    result = {}
    for locale in self.config.locales:
      path = self.path_for(slug, locale)
      if path.is_file():
        result[locale] = path
    return result

  def locales_present(self, slug: str) -> tuple[str, ...]:
    """Return the configured locales whose files exist for ``slug``."""
    return tuple(sorted(self._all_paths(slug)))

  def has_entry(self, slug: str) -> bool:
    """Return whether the canonical document exists for ``slug``."""
    return self.path_for(slug, self.config.default_locale).is_file()

  def entry_etag(self, slug: str) -> str | None:
    """Return the aggregate ETag, or ``None`` when no locale exists."""
    with self._lock:
      paths = self._all_paths(slug)
      if not paths:
        return None
      source = ''.join(
        f'{locale}:{store.compute_etag(path.read_text(encoding="utf-8"))};'
        for locale, path in sorted(paths.items())
      )
      return hashlib.sha256(source.encode()).hexdigest()

  def inventory(self) -> dict[str, dict[str, Path]]:
    """Return all recognized locale files, including orphan translations."""
    slugs: set[str] = set()
    if self.config.structure == 'multiple_folders':
      for locale in self.config.locales:
        locale_dir = self.collection.dir / locale
        if locale_dir.is_dir() and locale_dir.resolve().is_relative_to(
          self.collection.dir.resolve()
        ):
          for ext in self.collection.extensions:
            slugs.update(
              candidate.stem
              for candidate in locale_dir.glob(f'*.{ext}')
              if candidate.is_file()
            )
    elif self.collection.dir.is_dir():
      locales = sorted(self.config.locales, key=len, reverse=True)
      for ext in self.collection.extensions:
        for candidate in self.collection.dir.glob(f'*.{ext}'):
          stem = candidate.stem
          matched_locale = next(
            (item for item in locales if stem.endswith('.' + item)), None
          )
          slugs.add(
            stem[: -(len(matched_locale) + 1)] if matched_locale else stem
          )
    inventory: dict[str, dict[str, Path]] = {}
    for slug in sorted(slugs):
      try:
        paths = self._all_paths(slug)
      except store.InvalidSlugError:
        # Files with suffixes that are not valid slugs may still be
        # reported as unknown locales by the integrity checker.
        continue
      if paths:
        inventory[slug] = paths
    return inventory

  def list(self) -> list[LocalizedEntry]:
    entries = []
    for slug, paths in self.inventory().items():
      if self.config.default_locale not in paths:
        continue
      canonical = self.read(slug, self.config.default_locale)
      digest = self.entry_etag(slug)
      if digest is None:
        continue
      entries.append(
        LocalizedEntry(slug, canonical, tuple(sorted(paths)), digest)
      )
    return entries

  def read(
    self, slug: str, locale: str, *, fallback: bool | None = None
  ) -> LocalizedDocument:
    with self._lock:
      path = self.path_for(slug, locale)
      used_locale = locale
      should_fallback = (
        fallback if fallback is not None else self.config.fallback == 'default'
      )
      if not path.is_file() and should_fallback:
        used_locale = self.config.default_locale
        path = self.path_for(slug, used_locale)
      if not path.is_file():
        raise store.NotFoundError(f'{slug!r} has no {locale!r} translation')
      text = path.read_text(encoding='utf-8')
      frontmatter, body = store.parse_document(text)
    return LocalizedDocument(
      slug, used_locale, frontmatter, body, store.compute_etag(text), path
    )

  def save_entry(
    self,
    slug: str,
    documents: Mapping[str, tuple[Mapping[str, Any], str]],
    *,
    if_match: Mapping[str, str] | str | None = None,
    expected_entry_etag: str | None = None,
  ) -> dict[str, str]:
    """Atomically replace the supplied locales of one canonical entry."""
    nested_match: Mapping[str, Mapping[str, str] | str] | None = None
    if if_match is not None:
      nested_match = {slug: if_match}
    nested_entry_match = (
      {slug: expected_entry_etag} if expected_entry_etag is not None else None
    )
    return self.save_many(
      {slug: documents},
      if_match=nested_match,
      expected_entry_etags=nested_entry_match,
    )[slug]

  def save_many(
    self,
    entries: Mapping[str, Mapping[str, tuple[Mapping[str, Any], str]]],
    *,
    if_match: Mapping[str, Mapping[str, str] | str] | None = None,
    expected_entry_etags: Mapping[str, str | None] | None = None,
    validate: Callable[[str, str, Path, Mapping[str, Any]], None] | None = None,
  ) -> dict[str, dict[str, str]]:
    """Atomically replace several entries and their supplied locales.

    All files are staged before the first replacement. A failed staging,
    validation callback or replacement restores every destination already
    committed by this call. Readers may still observe the documented brief
    commit window while several filesystem paths are replaced.
    """
    if not entries:
      raise ValueError('At least one entry is required')
    for slug, documents in entries.items():
      self.path_for(slug, self.config.default_locale)
      if not documents:
        raise ValueError(f'Entry {slug!r} has no locale documents')
      unknown = set(documents) - set(self.config.locales)
      if unknown:
        raise I18nConfigError(f'Unknown locale(s): {sorted(unknown)!r}')

    with self._lock:
      targets: dict[tuple[str, str], Path] = {}
      previous_bytes: dict[Path, bytes | None] = {}
      staged: dict[Path, Path] = {}
      committed: list[Path] = []
      try:
        for slug in sorted(entries):
          documents = entries[slug]
          current = self._all_paths(slug)
          if (
            self.config.default_locale not in current
            and self.config.default_locale not in documents
          ):
            raise ValueError(
              f'Cannot create translation {slug!r} without its canonical '
              f'{self.config.default_locale!r} document'
            )
          if (
            expected_entry_etags is not None
            and slug in expected_entry_etags
            and self.entry_etag(slug) != expected_entry_etags[slug]
          ):
            raise store.ConflictError(
              f'entry etag does not match for {slug!r}', status_code=412
            )

          entry_match = if_match.get(slug) if if_match is not None else None
          for locale in sorted(documents):
            frontmatter, body = documents[locale]
            target = self.path_for(slug, locale)
            targets[(slug, locale)] = target
            previous = target.read_bytes() if target.is_file() else None
            previous_bytes[target] = previous
            expected = (
              entry_match.get(locale)
              if isinstance(entry_match, Mapping)
              else entry_match
            )
            if expected is not None:
              actual = (
                store.compute_etag(previous.decode('utf-8'))
                if previous is not None
                else None
              )
              if actual != expected:
                status_code = 412 if actual is not None else 409
                raise store.ConflictError(
                  f'{locale} etag does not match for {slug!r}',
                  status_code=status_code,
                )
            if previous is None and not self.collection.create:
              raise store.OperationNotAllowedError(
                'Creating documents is disabled'
              )
            text = store.serialize_document(dict(frontmatter), body)
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(
              prefix=f'.{target.stem}.stage-',
              suffix=target.suffix,
              dir=target.parent,
            )
            tmp = Path(tmp_name)
            staged[target] = tmp
            with os.fdopen(fd, 'w', encoding='utf-8', newline='') as stream:
              stream.write(text)
              stream.flush()
              os.fsync(stream.fileno())
            if validate is not None:
              validate(slug, locale, tmp, frontmatter)

        for target in sorted(staged, key=lambda item: str(item)):
          os.replace(staged[target], target)
          committed.append(target)
      except BaseException:
        for target in reversed(committed):
          previous = previous_bytes[target]
          if previous is None:
            target.unlink(missing_ok=True)
          else:
            store.atomic_write_text(target, previous.decode('utf-8'))
        raise
      finally:
        for tmp in staged.values():
          tmp.unlink(missing_ok=True)

      result: dict[str, dict[str, str]] = {}
      for slug, documents in entries.items():
        result[slug] = {
          locale: store.compute_etag(
            targets[(slug, locale)].read_text(encoding='utf-8')
          )
          for locale in documents
        }
      return result

  def delete_locale(
    self,
    slug: str,
    locale: str,
    *,
    cascade: bool = False,
    if_match: str | None = None,
  ) -> None:
    if not self.collection.delete:
      raise store.OperationNotAllowedError('Deleting documents is disabled')
    with self._lock:
      paths = self._all_paths(slug)
      path = paths.get(locale)
      if path is None:
        raise store.NotFoundError(f'{slug!r} has no {locale!r} translation')
      if (
        locale == self.config.default_locale
        and any(key != locale for key in paths)
        and not cascade
      ):
        raise ValueError('Deleting the canonical locale requires cascade=True')
      if if_match is not None:
        actual = store.compute_etag(path.read_text(encoding='utf-8'))
        if actual != if_match:
          raise store.ConflictError(
            f'{locale} etag does not match for {slug!r}', status_code=412
          )
      paths_to_delete = (
        list(paths.values())
        if locale == self.config.default_locale and cascade
        else [path]
      )
      self._delete_paths(paths_to_delete)

  def delete_entry(self, slug: str, *, cascade: bool = False) -> None:
    if not self.collection.delete:
      raise store.OperationNotAllowedError('Deleting documents is disabled')
    with self._lock:
      paths = self._all_paths(slug)
      if not paths:
        raise store.NotFoundError(f'entry not found: {slug!r}')
      if self.config.default_locale in paths and len(paths) > 1 and not cascade:
        raise ValueError(
          'Deleting the canonical entry with translations requires cascade=True'
        )
      self._delete_paths(list(paths.values()))

  def _delete_paths(self, paths: Sequence[Path]) -> None:
    """Remove several paths with a rollback if staging one fails."""
    moved: list[tuple[Path, Path]] = []
    try:
      for path in sorted(paths, key=str):
        backup = path.with_name(
          f'.{path.name}.delete-{os.getpid()}-{len(moved)}'
        )
        if backup.exists():
          raise store.ConflictError(
            f'delete staging path already exists: {backup.name}',
            status_code=409,
          )
        os.replace(path, backup)
        moved.append((path, backup))
    except BaseException:
      for original, backup in reversed(moved):
        os.replace(backup, original)
      raise
    for _original, backup in moved:
      backup.unlink(missing_ok=True)

  def rename(
    self,
    old_slug: str,
    new_slug: str,
    *,
    expected_entry_etag: str | None = None,
  ) -> None:
    with self._lock:
      if old_slug == new_slug:
        return
      paths = self._all_paths(old_slug)
      if self.config.default_locale not in paths:
        raise store.NotFoundError(f'canonical entry not found: {old_slug!r}')
      if not self.collection.create:
        raise store.OperationNotAllowedError('Creating documents is disabled')
      if (
        expected_entry_etag is not None
        and self.entry_etag(old_slug) != expected_entry_etag
      ):
        raise store.ConflictError(
          f'entry etag does not match for {old_slug!r}', status_code=412
        )
      if self._all_paths(new_slug):
        raise store.ConflictError(
          f'{new_slug!r} already exists', status_code=409
        )
      destinations = {
        locale: self.path_for(
          new_slug, locale, extension=source.suffix.removeprefix('.')
        )
        for locale, source in paths.items()
      }
      moved: list[tuple[Path, Path]] = []
      try:
        for locale, source in sorted(paths.items()):
          target = destinations[locale]
          target.parent.mkdir(parents=True, exist_ok=True)
          os.replace(source, target)
          moved.append((source, target))
      except BaseException:
        for source, target in reversed(moved):
          os.replace(target, source)
        raise
