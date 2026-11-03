"""Translations for the public blog and optional admin interface."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml


logger = logging.getLogger('fastapi_blog.i18n')


class TranslationSection:
  """Expose nested translation mappings through attribute and item access."""

  def __init__(self, values: Mapping[str, Any]):
    """Store a translation mapping."""
    self._values = dict(values)

  def __getattr__(self, name: str) -> Any:
    try:
      value = self._values[name]
    except KeyError as exc:
      raise AttributeError(name) from exc
    return TranslationSection(value) if isinstance(value, Mapping) else value

  def __getitem__(self, name: str) -> Any:
    value = self._values[name]
    return TranslationSection(value) if isinstance(value, Mapping) else value

  def get(self, name: str, default: Any = None) -> Any:
    value = self._values.get(name, default)
    return TranslationSection(value) if isinstance(value, Mapping) else value

  def __contains__(self, name: str) -> bool:
    return name in self._values


def resolve_localized(
  value: Any, locale: str | None, default_locale: str | None = None
) -> str | None:
  """Resolve localized UI text using locale, default locale, then first value."""
  if value is None:
    return None
  if isinstance(value, str):
    return value
  if not isinstance(value, Mapping) or not value:
    return None
  if locale and isinstance(value.get(locale), str):
    return value[locale]
  if default_locale and isinstance(value.get(default_locale), str):
    return value[default_locale]
  first = next(iter(value.values()), None)
  return first if isinstance(first, str) else None


def _read_yaml(path: Any) -> dict[str, Any]:
  """Read a YAML translation file, returning an empty mapping for no file."""
  if not path.is_file():
    return {}
  try:
    value = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
  except (OSError, yaml.YAMLError) as exc:
    logger.warning('Unable to load translation file %s: %s', path, exc)
    return {}
  if not isinstance(value, dict):
    logger.warning('Translation file %s must contain a mapping', path)
    return {}
  return value


def _deep_merge(
  base: Mapping[str, Any], overlay: Mapping[str, Any]
) -> dict[str, Any]:
  """Merge nested translation mappings without mutating either input."""
  merged = dict(base)
  for key, value in overlay.items():
    previous = merged.get(key)
    if isinstance(previous, Mapping) and isinstance(value, Mapping):
      merged[key] = _deep_merge(previous, value)
    else:
      merged[key] = value
  return merged


def _missing_translation_keys(
  english: Mapping[str, Any], localized: Mapping[str, Any], prefix: str = ''
) -> list[str]:
  """Return deterministic English leaf paths absent from a locale file."""
  missing: list[str] = []
  for key, value in english.items():
    path = f'{prefix}.{key}' if prefix else str(key)
    translated = localized.get(key)
    if isinstance(value, Mapping):
      if not isinstance(translated, Mapping):
        missing.extend(_missing_translation_keys(value, {}, path))
      else:
        missing.extend(_missing_translation_keys(value, translated, path))
    elif key not in localized:
      missing.append(path)
  return missing


@lru_cache(maxsize=64)
def _load_translations_cached(
  locale: str, translations_dir: str | None
) -> dict[str, Any]:
  """Load bundled and optional project translations for one locale."""
  base = files('fastapi_blog').joinpath('translations')
  english = _read_yaml(base.joinpath('en.yaml'))
  bundled = _read_yaml(base.joinpath(f'{locale}.yaml'))
  localized = _deep_merge(bundled, {})

  external_path = (
    Path(translations_dir) / f'{locale}.yaml'
    if translations_dir is not None
    else None
  )
  external_exists = external_path is not None and external_path.is_file()
  if external_exists and external_path is not None:
    localized = _deep_merge(localized, _read_yaml(external_path))

  if locale != 'en' and external_exists:
    missing = _missing_translation_keys(english, localized)
    if missing:
      logger.warning(
        'Translation %r is missing %d key(s); using English fallback: %s',
        locale,
        len(missing),
        ', '.join(missing),
      )

  return _deep_merge(english, localized)


@lru_cache(maxsize=64)
def load_translations(
  locale: str, translations_dir: str | Path | None = None
) -> dict[str, Any]:
  """Load a locale, overlaying project YAML on bundled values and English."""
  directory = (
    str(Path(translations_dir).resolve()) if translations_dir else None
  )
  return _load_translations_cached(locale, directory)


def get_all_locale_names(
  translations_dir: str | Path | None = None,
  locales: tuple[str, ...] | list[str] = (),
) -> dict[str, str]:
  """Return bundled, project-defined and explicitly configured locale names."""
  base = files('fastapi_blog').joinpath('translations')
  locale_codes = {
    path.name.removesuffix('.yaml')
    for path in base.iterdir()
    if path.name.endswith('.yaml')
  }
  directory = Path(translations_dir) if translations_dir is not None else None
  if directory is not None and directory.is_dir():
    locale_codes.update(
      path.stem for path in directory.glob('*.yaml') if path.is_file()
    )
  locale_codes.update(locales)

  bundled_codes = {
    path.name.removesuffix('.yaml')
    for path in base.iterdir()
    if path.name.endswith('.yaml')
  }
  names: dict[str, str] = {}
  for locale in sorted(locale_codes):
    has_translation = locale in bundled_codes or (
      directory is not None and (directory / f'{locale}.yaml').is_file()
    )
    if not has_translation:
      names[locale] = locale
      continue
    values = load_translations(locale, directory)
    metadata = values.get('locale', {})
    name = metadata.get('name') if isinstance(metadata, Mapping) else None
    names[locale] = str(name or locale)
  return names


def get_locale_name(
  locale: str, translations_dir: str | Path | None = None
) -> str:
  """Return the display name for a locale, or its code when unknown."""
  return get_all_locale_names(translations_dir).get(locale, locale)


class Translator(TranslationSection):
  """Attribute-based access to translations for one interface locale."""

  def __init__(self, locale: str, translations_dir: str | Path | None = None):
    """Load translations for the requested interface locale."""
    super().__init__(load_translations(locale, translations_dir))
