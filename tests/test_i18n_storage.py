from pathlib import Path

import pytest

from fastapi_blog import store
from fastapi_blog.i18n import I18nCollection, I18nConfig, I18nConfigError


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
  hashes = collection.save_entry('hello', {
    'en': ({'title': 'Hello'}, 'English body'),
    'ru': ({'title': 'Привет'}, 'Русский текст'),
  })
  assert set(hashes) == {'en', 'ru'}
  assert collection.read('hello', 'ru').frontmatter['title'] == 'Привет'
  assert collection.read('hello', 'de' if False else 'ru').body == 'Русский текст'
  assert collection.list()[0].locales_present == ('en', 'ru')
  with pytest.raises(ValueError, match='cascade=True'):
    collection.delete_locale('hello', 'en')
  collection.delete_entry('hello', cascade=True)
  assert collection.list() == []
