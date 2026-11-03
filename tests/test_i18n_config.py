from pathlib import Path

import pytest

from fastapi_blog.config import ConfigError, load_project
from fastapi_blog.i18n_collections import I18nConfig
from fastapi_blog.models import FieldSpec, FrontmatterSchema


def _project(tmp_path: Path, content: str):
  path = tmp_path / 'fastapi_blog.yaml'
  path.write_text(content, encoding='utf-8')
  return load_project(path)


def test_project_i18n_defaults_apply_to_all_collections(tmp_path):
  project = _project(
    tmp_path,
    'i18n:\n  locales: [en, ru]\n  default_locale: en\n'
    'collections:\n  posts:\n    dir: posts\n'
    '  pages:\n    dir: pages\n',
  )
  assert project.collections['posts'].i18n == I18nConfig(('en', 'ru'), 'en')
  assert project.collections['pages'].i18n == I18nConfig(('en', 'ru'), 'en')


def test_collection_i18n_can_override_project_defaults(tmp_path):
  project = _project(
    tmp_path,
    'i18n:\n  locales: [en, ru]\n  default_locale: en\n'
    'collections:\n  posts:\n    dir: posts\n'
    '    i18n:\n      locales: [en, de]\n      default_locale: de\n'
    '      fallback: none\n',
  )
  config = project.collections['posts'].i18n
  assert config is not None
  assert config.locales == ('en', 'de')
  assert config.default_locale == 'de'
  assert config.fallback == 'none'


def test_i18n_translation_options_are_inherited_and_overridden(tmp_path):
  project = _project(
    tmp_path,
    'i18n:\n  locales: [en, ru]\n  default_locale: en\n'
    '  required_in_translations: true\n  write_duplicates: true\n'
    'collections:\n  posts:\n    dir: posts\n'
    '  pages:\n    dir: pages\n'
    '    i18n:\n      required_in_translations: false\n',
  )
  posts = project.collections['posts'].i18n
  pages = project.collections['pages'].i18n
  assert posts is not None and pages is not None
  assert posts.required_in_translations is True
  assert posts.write_duplicates is True
  assert pages.required_in_translations is False
  assert pages.write_duplicates is True


def test_collection_can_disable_project_i18n(tmp_path):
  project = _project(
    tmp_path,
    'i18n:\n  locales: [en, ru]\n  default_locale: en\n'
    'collections:\n  posts:\n    dir: posts\n'
    '    i18n: false\n',
  )
  assert project.collections['posts'].i18n is None


@pytest.mark.parametrize(
  'content',
  [
    'i18n:\n  locales: [en, en]\n  default_locale: en\n'
    'collections:\n  posts:\n    dir: posts\n',
    'i18n:\n  locales: [en, ru]\n  default_locale: de\n'
    'collections:\n  posts:\n    dir: posts\n',
    'i18n:\n  structure: single_file\n  locales: [en]\n'
    '  default_locale: en\ncollections:\n  posts:\n    dir: posts\n',
    'i18n:\n  locales: [en, ru]\n  default_locale: en\n'
    'collections:\n  posts:\n    dir: posts\n    depth: 1\n',
  ],
)
def test_invalid_project_i18n_is_rejected(tmp_path, content):
  with pytest.raises(ConfigError):
    _project(tmp_path, content)


def test_field_i18n_modes_round_trip():
  schema = FrontmatterSchema.from_dict(
    {'fields': {'title': {'i18n': True}, 'status': {'i18n': 'duplicate'}}}
  )
  assert schema.get('title').i18n == 'translate'
  assert schema.get('status').i18n == 'duplicate'
  assert schema.to_dict()['fields']['title']['i18n'] == 'translate'


def test_field_i18n_rejects_unknown_mode():
  with pytest.raises(ValueError, match='i18n mode'):
    FieldSpec('title', i18n='localized')


def test_localized_field_and_collection_labels_round_trip(tmp_path):
  schema_path = tmp_path / 'posts.schema.yaml'
  schema_path.write_text(
    'fields:\n'
    '  title:\n'
    '    type: str\n'
    '    label: {en: Title, ru: Заголовок}\n'
    '    hint: {en: Name, ru: Название}\n'
    '  status:\n'
    '    type: str\n'
    '    choices:\n'
    '      - {value: draft, label: {en: Draft, ru: Черновик}}\n',
    encoding='utf-8',
  )
  project = _project(
    tmp_path,
    'i18n:\n  locales: [en, ru]\n  default_locale: en\n'
    'collections:\n  posts:\n    dir: posts\n'
    '    label: {en: Posts, ru: Записи}\n'
    '    schema: posts.schema.yaml\n',
  )
  spec = project.collections['posts']
  assert spec.label_for('ru') == 'Записи'
  assert spec.label_for('de') == 'Posts'
  assert spec.schema is not None
  assert spec.schema.get('title').label == {'en': 'Title', 'ru': 'Заголовок'}
  assert spec.schema.get('status').choices[0]['label']['ru'] == 'Черновик'


def test_unknown_localized_label_locale_warns(tmp_path):
  schema_path = tmp_path / 'posts.schema.yaml'
  schema_path.write_text(
    'fields:\n  title:\n    type: str\n    label: {en: Title, de: Titel}\n',
    encoding='utf-8',
  )
  with pytest.warns(UserWarning, match='unknown locale'):
    _project(
      tmp_path,
      'i18n:\n  locales: [en, ru]\n  default_locale: en\n'
      'collections:\n  posts:\n    dir: posts\n'
      '    schema: posts.schema.yaml\n',
    )


def test_project_translations_dir_is_resolved_and_shared_with_collections(
  tmp_path,
):
  project = _project(
    tmp_path,
    'translations_dir: translations\n'
    'i18n:\n  locales: [en, ru]\n  default_locale: en\n'
    'collections:\n  posts:\n    dir: posts\n',
  )
  expected = tmp_path / 'translations'
  assert project.translations_dir == expected
  assert project.collections['posts'].translations_dir == expected


@pytest.mark.parametrize('value', ['/tmp/translations', '../outside', ''])
def test_project_translations_dir_must_be_safe_relative_path(tmp_path, value):
  with pytest.raises(ConfigError, match='translations_dir'):
    _project(
      tmp_path,
      f'translations_dir: {value!r}\ncollections:\n  posts:\n    dir: posts\n',
    )
