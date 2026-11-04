from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from fastapi_blog import i18n_collections, store
from fastapi_blog.i18n_collections import (
  I18nCollection,
  I18nConfig,
  I18nConfigError,
)


def test_adapters_share_lock_and_reject_a_stale_write(tmp_path):
  collection = store.Collection('posts', tmp_path)
  config = I18nConfig(('en', 'ru'), 'en')
  first = I18nCollection(collection, config)
  second = I18nCollection(collection, config)
  first.save_entry('entry', {'en': ({'title': 'Original'}, 'body')})
  etag = first.entry_etag('entry')
  barrier = Barrier(2)

  def update(adapter, title):
    barrier.wait()
    try:
      adapter.save_entry(
        'entry', {'en': ({'title': title}, 'body')}, expected_entry_etag=etag
      )
      return 'saved'
    except store.ConflictError:
      return 'conflict'

  with ThreadPoolExecutor(max_workers=2) as pool:
    futures = [
      pool.submit(update, first, 'One'),
      pool.submit(update, second, 'Two'),
    ]
    assert sorted(future.result() for future in futures) == [
      'conflict',
      'saved',
    ]


def test_existing_alternate_extension_is_preserved_on_update_and_rename(
  tmp_path,
):
  collection = store.Collection('posts', tmp_path, extension=('md', 'markdown'))
  adapter = I18nCollection(collection, I18nConfig(('en', 'ru'), 'en'))
  (tmp_path / 'entry.markdown').write_text('---\ntitle: Original\n---\nBody\n')
  assert [entry.slug for entry in adapter.list()] == ['entry']
  adapter.save_entry('entry', {'en': ({'title': 'Updated'}, 'body')})
  assert not (tmp_path / 'entry.md').exists()
  adapter.rename('entry', 'renamed')
  assert (tmp_path / 'renamed.markdown').is_file()


def test_rename_rejects_destination_with_an_orphan_translation(tmp_path):
  adapter = I18nCollection(
    store.Collection('posts', tmp_path), I18nConfig(('en', 'ru'), 'en')
  )
  adapter.save_entry('source', {'en': ({'title': 'Source'}, 'body')})
  orphan = tmp_path / 'destination.ru.md'
  orphan.write_text('---\ntitle: Translation\n---\nText\n')
  with pytest.raises(store.ConflictError):
    adapter.rename('source', 'destination')
  assert (tmp_path / 'source.md').exists()
  assert orphan.read_text().endswith('Text\n')


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


def test_i18n_save_many_rolls_back_all_entries_on_failure(
  tmp_path, monkeypatch
):
  collection = I18nCollection(
    store.Collection('posts', tmp_path), I18nConfig(('en', 'ru'), 'en')
  )
  collection.save_many(
    {
      'first': {'en': ({'title': 'Old'}, 'First')},
      'second': {'en': ({'title': 'Old'}, 'Second')},
    }
  )
  before = {
    slug: collection.path_for(slug, 'en').read_bytes()
    for slug in ('first', 'second')
  }
  original_replace = i18n_collections.os.replace
  calls = 0

  def fail_second_replace(source, target):
    nonlocal calls
    calls += 1
    if calls == 2:
      raise OSError('simulated multi-entry failure')
    return original_replace(source, target)

  monkeypatch.setattr(i18n_collections.os, 'replace', fail_second_replace)
  with pytest.raises(OSError, match='multi-entry'):
    collection.save_many(
      {
        'first': {'en': ({'title': 'New'}, 'Changed first')},
        'second': {'en': ({'title': 'New'}, 'Changed second')},
      }
    )
  assert {
    slug: collection.path_for(slug, 'en').read_bytes()
    for slug in ('first', 'second')
  } == before


def test_i18n_rejects_translation_without_canonical_document(tmp_path):
  collection = I18nCollection(
    store.Collection('posts', tmp_path), I18nConfig(('en', 'ru'), 'en')
  )
  with pytest.raises(ValueError, match='canonical'):
    collection.save_entry('hello', {'ru': ({'title': 'Привет'}, 'Текст')})


def test_i18n_save_many_checks_aggregate_etag(tmp_path):
  collection = I18nCollection(
    store.Collection('posts', tmp_path), I18nConfig(('en', 'ru'), 'en')
  )
  collection.save_entry('hello', {'en': ({'title': 'Hello'}, 'Body')})
  etag = collection.entry_etag('hello')
  assert etag is not None
  with pytest.raises(store.ConflictError) as conflict:
    collection.save_many(
      {'hello': {'en': ({'title': 'Stale'}, 'Stale')}},
      expected_entry_etags={'hello': 'stale'},
    )
  assert conflict.value.status_code == 412
  assert collection.entry_etag('hello') == etag


@pytest.mark.parametrize('structure', ['multiple_files', 'multiple_folders'])
def test_i18n_rename_moves_every_locale(tmp_path, structure):
  collection = I18nCollection(
    store.Collection('posts', tmp_path),
    I18nConfig(('en', 'ru'), 'en', structure=structure),
  )
  collection.save_entry(
    'old-name',
    {
      'en': ({'title': 'Old'}, 'English'),
      'ru': ({'title': 'Старое'}, 'Русский'),
    },
  )
  entry_etag = collection.entry_etag('old-name')
  collection.rename('old-name', 'new-name', expected_entry_etag=entry_etag)
  assert collection.locales_present('old-name') == ()
  assert collection.locales_present('new-name') == ('en', 'ru')
  assert collection.read('new-name', 'ru').frontmatter['title'] == 'Старое'


def test_i18n_rename_rejects_stale_entry_etag(tmp_path):
  collection = I18nCollection(
    store.Collection('posts', tmp_path), I18nConfig(('en', 'ru'), 'en')
  )
  collection.save_entry('old', {'en': ({'title': 'Old'}, 'Body')})
  with pytest.raises(store.ConflictError):
    collection.rename('old', 'new', expected_entry_etag='stale')
  assert collection.has_entry('old')
  assert not collection.has_entry('new')
