from pathlib import Path

import pytest

from fastapi_blog import i18n_collections, store
from fastapi_blog.i18n_collections import (
  I18nCollection,
  I18nConfig,
  I18nConfigError,
)


def test_i18n_config_validation():
  with pytest.raises(I18nConfigError):
    I18nConfig(('en', 'en'), 'en')
  with pytest.raises(I18nConfigError):
    I18nConfig(('en', 'ru'), 'de')
  with pytest.raises(I18nConfigError):
    I18nConfig(('en',), 'en', structure='single_file')


@pytest.mark.parametrize('structure', ['multiple_files', 'multiple_folders'])
def test_i18n_save_read_list_delete(tmp_path: Path, structure: str):
  config = I18nConfig(('en', 'ru'), 'en', structure=structure)
  collection = I18nCollection(store.Collection('posts', tmp_path), config)
  hashes = collection.save_entry(
    'hello',
    {
      'en': ({'title': 'Hello'}, 'English body'),
      'ru': ({'title': 'Привет'}, 'Русский текст'),
    },
  )
  assert set(hashes) == {'en', 'ru'}
  assert collection.read('hello', 'ru').frontmatter['title'] == 'Привет'
  assert collection.read('hello', 'ru').body == 'Русский текст'
  assert collection.list()[0].locales_present == ('en', 'ru')
  with pytest.raises(ValueError, match='cascade=True'):
    collection.delete_locale('hello', 'en')
  collection.delete_entry('hello', cascade=True)
  assert collection.list() == []


def test_i18n_save_rolls_back_when_second_replace_fails(tmp_path, monkeypatch):
  config = I18nConfig(('en', 'ru'), 'en')
  collection = I18nCollection(store.Collection('posts', tmp_path), config)
  collection.save_entry(
    'hello',
    {
      'en': ({'title': 'Old'}, 'Old English'),
      'ru': ({'title': 'Старое'}, 'Старый текст'),
    },
  )
  before = {
    locale: collection.read('hello', locale).path.read_bytes()
    for locale in ('en', 'ru')
  }
  original_replace = store.os.replace
  calls = 0

  def fail_second_replace(source, target):
    nonlocal calls
    calls += 1
    if calls == 2:
      raise OSError('simulated replace failure')
    return original_replace(source, target)

  monkeypatch.setattr(i18n_collections.os, 'replace', fail_second_replace)
  with pytest.raises(OSError, match='simulated'):
    collection.save_entry(
      'hello',
      {
        'en': ({'title': 'New'}, 'New English'),
        'ru': ({'title': 'Новое'}, 'Новый текст'),
      },
    )
  after = {
    locale: collection.read('hello', locale).path.read_bytes()
    for locale in ('en', 'ru')
  }
  assert after == before


def test_i18n_delete_respects_collection_delete_flag(tmp_path):
  collection = I18nCollection(
    store.Collection('posts', tmp_path, delete=False),
    I18nConfig(('en', 'ru'), 'en'),
  )
  collection.save_entry('hello', {'en': ({'title': 'Hello'}, 'Body')})
  with pytest.raises(store.OperationNotAllowedError):
    collection.delete_entry('hello', cascade=True)


def test_i18n_path_rejects_slugs_that_escape_custom_pattern(tmp_path):
  collection = I18nCollection(
    store.Collection('posts', tmp_path, slug_pattern=r'.*'),
    I18nConfig(('en', 'ru'), 'en'),
  )
  with pytest.raises(store.InvalidSlugError):
    collection.path_for('../outside', 'en')
