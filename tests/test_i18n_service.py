"""Tests for schema-aware multi-locale document service operations."""

import sys

import pytest
from pydantic import ValidationError

from fastapi_blog import store
from fastapi_blog.config import CollectionSpec
from fastapi_blog.i18n_collections import I18nConfig
from fastapi_blog.issues import Issue
from fastapi_blog.models import FieldSpec, FrontmatterSchema
from fastapi_blog.service import BlockingValidationError, DocumentService
from fastapi_blog.validators import Validator


def _service(
  tmp_path, *, write_duplicates=False, required=False, on_change=None
):
  schema = FrontmatterSchema(
    fields=(
      FieldSpec('title', required=True, i18n='translate'),
      FieldSpec('code', required=True, i18n='duplicate'),
      FieldSpec('summary'),
    ),
    extra='forbid',
  )
  collection = CollectionSpec(
    'articles',
    tmp_path,
    schema=schema,
    i18n=I18nConfig(
      ('en', 'ru'),
      'en',
      write_duplicates=write_duplicates,
      required_in_translations=required,
    ),
    on_change=on_change,
  )
  documents = store.DocumentStore(collection.to_collection())
  return DocumentService(documents, schema, collection_spec=collection)


def test_translation_relaxes_required_fields_and_reports_duplicate_mismatch(
  tmp_path,
):
  service = _service(tmp_path)
  result = service.save_localized(
    'hello',
    {
      'en': ({'title': 'Hello', 'code': 'A'}, 'English body'),
      'ru': ({'code': 'B'}, 'Russian body'),
    },
  )
  assert result.status == 'created'
  assert result.locales_present == ('en', 'ru')
  assert [(issue.code, issue.field) for issue in result.issues] == [
    ('translation.duplicate_mismatch', 'code')
  ]
  translated = service.i18n_documents.read('hello', 'ru')
  assert 'title' not in translated.frontmatter
  assert 'code' not in translated.frontmatter


def test_write_duplicates_mirrors_canonical_values(tmp_path):
  service = _service(tmp_path, write_duplicates=True)
  result = service.save_localized(
    'hello',
    {
      'en': ({'title': 'Hello', 'code': 'A'}, 'English body'),
      'ru': ({'code': 'B'}, 'Russian body'),
    },
  )
  translated = service.i18n_documents.read('hello', 'ru')
  assert translated.frontmatter == {'code': 'A'}
  assert [issue.code for issue in result.issues] == [
    'translation.duplicate_mismatch'
  ]


def test_body_is_shared_when_translation_is_disabled(tmp_path):
  service = _service(tmp_path)
  service.save_localized(
    'hello',
    {
      'en': ({'title': 'Hello', 'code': 'A'}, 'Canonical body'),
      'ru': ({'title': 'Привет', 'code': 'A'}, 'Translated body ignored'),
    },
  )
  translated = service.i18n_documents.read('hello', 'ru')
  assert translated.body == 'Canonical body'


def test_localized_save_rejects_empty_canonical_body(tmp_path):
  service = _service(tmp_path)
  with pytest.raises(ValueError, match='must not be empty'):
    service.save_localized(
      'hello', {'en': ({'title': 'Hello', 'code': 'A'}, '  ')}
    )
  assert not (tmp_path / 'hello.md').exists()


def test_localized_save_rejects_changed_existence_after_authorization(tmp_path):
  service = _service(tmp_path)
  service.save_localized(
    'hello', {'en': ({'title': 'Hello', 'code': 'A'}, 'Body')}
  )
  with pytest.raises(store.ConflictError):
    service.save_localized(
      'hello',
      {'en': ({'title': 'Overwrite', 'code': 'A'}, 'Body')},
      expected_exists=False,
    )
  assert (
    service.i18n_documents.read('hello', 'en').frontmatter['title'] == 'Hello'
  )


def test_save_preserves_existing_conflicting_shared_fields(tmp_path):
  service = _service(tmp_path)
  service.i18n_documents.save_entry(
    'hello',
    {
      'en': ({'title': 'Hello', 'code': 'A'}, 'Body'),
      'ru': ({'title': 'Привет', 'code': 'B'}, 'Текст'),
    },
  )
  previous = (tmp_path / 'hello.ru.md').read_bytes()
  with pytest.raises(store.ConflictError, match='conflicting shared field'):
    service.save_localized('hello', {'ru': ({'title': 'Новый'}, 'New body')})
  assert (tmp_path / 'hello.ru.md').read_bytes() == previous


def test_required_fields_can_be_required_in_translations(tmp_path):
  service = _service(tmp_path, required=True)
  with pytest.raises(ValidationError):
    service.save_localized(
      'hello',
      {
        'en': ({'title': 'Hello', 'code': 'A'}, 'English body'),
        'ru': ({'code': 'A'}, 'Russian body'),
      },
    )
  assert service.i18n_documents.locales_present('hello') == ()


def test_localized_blocking_validator_failure_writes_nothing(
  tmp_path, monkeypatch
):
  service = _service(tmp_path)
  service.validators = (
    Validator.from_dict(
      {'name': 'gate', 'argv': ['true'], 'blocking': ['error']}
    ),
  )
  issue = Issue('error', 'validator.failed', 'Rejected', slug='hello')

  def reject_translation(*args, **kwargs):
    if kwargs.get('locale') == 'ru':
      return [issue]
    return []

  monkeypatch.setattr('fastapi_blog.service.run_blocking', reject_translation)
  with pytest.raises(BlockingValidationError) as error:
    service.save_localized(
      'hello',
      {
        'en': ({'title': 'Hello', 'code': 'A'}, 'English body'),
        'ru': ({'title': 'Привет', 'code': 'A'}, 'Russian body'),
      },
    )
  assert error.value.issues == [issue]
  assert service.i18n_documents.locales_present('hello') == ()


def test_translation_updates_use_locale_and_entry_etags(tmp_path):
  service = _service(tmp_path)
  created = service.save_localized(
    'hello',
    {
      'en': ({'title': 'Hello', 'code': 'A'}, 'English body'),
      'ru': ({'title': 'Привет', 'code': 'A'}, 'Russian body'),
    },
  )
  service.save_localized(
    'hello',
    {'ru': ({'title': 'Здравствуйте', 'code': 'A'}, 'Russian body 2')},
    if_match={'ru': created.etags['ru']},
    expected_entry_etag=created.entry_etag,
  )
  with pytest.raises(store.ConflictError) as conflict:
    service.save_localized(
      'hello',
      {'ru': ({'title': 'Stale', 'code': 'A'}, 'Stale body')},
      if_match={'ru': created.etags['ru']},
    )
  assert conflict.value.status_code == 412


def test_localized_delete_requires_cascade_for_canonical_locale(tmp_path):
  service = _service(tmp_path)
  created = service.save_localized(
    'hello',
    {
      'en': ({'title': 'Hello', 'code': 'A'}, 'English body'),
      'ru': ({'title': 'Привет', 'code': 'A'}, 'Russian body'),
    },
  )
  with pytest.raises(ValueError, match='cascade=True'):
    service.delete_locale('hello', 'en')
  service.delete_localized_entry(
    'hello', cascade=True, expected_entry_etag=created.entry_etag
  )
  assert service.i18n_documents.locales_present('hello') == ()


def test_unique_values_are_checked_across_canonical_entries(tmp_path):
  service = _service(tmp_path)
  service.collection_spec = CollectionSpec(
    'articles',
    tmp_path,
    schema=service.schema,
    i18n=service.i18n_documents.config,
    unique=('code',),
  )
  service.save_localized(
    'first', {'en': ({'title': 'First', 'code': 'SHARED'}, 'Body')}
  )
  with pytest.raises(ValueError, match='already used'):
    service.save_localized(
      'second', {'en': ({'title': 'Second', 'code': 'SHARED'}, 'Body')}
    )
  assert service.i18n_documents.locales_present('second') == ()


def test_concurrent_updates_with_same_entry_etag_only_commit_once(tmp_path):
  from concurrent.futures import ThreadPoolExecutor
  from threading import Barrier

  service = _service(tmp_path)
  created = service.save_localized(
    'hello',
    {
      'en': ({'title': 'Hello', 'code': 'A'}, 'English body'),
      'ru': ({'title': 'Привет', 'code': 'A'}, 'Russian body'),
    },
  )
  barrier = Barrier(2)

  def update(title):
    barrier.wait()
    try:
      service.save_localized(
        'hello',
        {'ru': ({'title': title, 'code': 'A'}, 'Updated body')},
        expected_entry_etag=created.entry_etag,
      )
    except store.ConflictError:
      return 'conflict'
    return 'saved'

  with ThreadPoolExecutor(max_workers=2) as executor:
    outcomes = list(executor.map(update, ('Первый', 'Второй')))
  assert sorted(outcomes) == ['conflict', 'saved']


def test_localized_writes_emit_one_extended_event_per_entry(tmp_path):
  events = []
  service = _service(tmp_path, on_change=events.append)
  created = service.save_localized(
    'hello',
    {
      'en': ({'title': 'Hello', 'code': 'A'}, 'English body'),
      'ru': ({'title': 'Привет', 'code': 'A'}, 'Russian body'),
    },
    user={'username': 'editor'},
  )
  assert len(events) == 1
  event = events[0]
  assert (event.kind, event.slug, event.locale, event.locales) == (
    'created',
    'hello',
    None,
    ('en', 'ru'),
  )
  assert event.etag == created.entry_etag
  assert event.entry_etag == created.entry_etag
  assert len(event.paths) == 2
  assert event.user == 'editor'

  service.delete_locale('hello', 'ru')
  assert len(events) == 2
  assert events[1].kind == 'delete_locale'
  assert events[1].locale == 'ru'
  assert events[1].locales == ('ru',)


def test_events_describe_the_committed_snapshot_even_if_hook_writes(tmp_path):
  events = []

  def callback(event):
    events.append(event)
    if event.slug == 'first':
      service.i18n_documents.save_entry(
        'second', {'en': ({'title': 'Later', 'code': 'B'}, 'Later')}
      )

  service = _service(tmp_path, on_change=callback)
  results = service.save_many_localized(
    {
      'first': {'en': ({'title': 'First', 'code': 'A'}, 'Body')},
      'second': {'en': ({'title': 'Second', 'code': 'B'}, 'Body')},
    }
  )
  assert events[1].entry_etag == results['second'].entry_etag
  assert events[1].entry_etag != service.i18n_documents.entry_etag('second')


def test_batch_save_supports_mixed_create_update_and_locale_sets(tmp_path):
  service = _service(tmp_path)
  original = service.save_localized(
    'existing',
    {
      'en': ({'title': 'Original', 'code': 'A'}, 'English'),
      'ru': ({'title': 'Исходный', 'code': 'A'}, 'Русский'),
    },
  )

  results = service.save_many_localized(
    {
      'existing': {
        'en': ({'title': 'Updated', 'code': 'A'}, 'Updated English'),
        'ru': ({'title': 'Обновлённый', 'code': 'A'}, 'Обновлённый русский'),
      },
      'created': {'en': ({'title': 'Created', 'code': 'B'}, 'English')},
    },
    expected_entry_etags={'existing': original.entry_etag, 'created': None},
    expected_exists={'existing': True, 'created': False},
  )

  assert results['existing'].status == 'updated'
  assert results['existing'].locales_present == ('en', 'ru')
  assert results['created'].status == 'created'
  assert results['created'].locales_present == ('en',)
  assert service.i18n_documents.read('existing', 'en').frontmatter['title'] == (
    'Updated'
  )
  assert service.i18n_documents.read('created', 'en').frontmatter['title'] == (
    'Created'
  )


def test_batch_event_callback_failure_does_not_hide_committed_result(
  tmp_path, caplog
):
  def fail(_event):
    raise RuntimeError('event delivery failed')

  service = _service(tmp_path, on_change=fail)
  results = service.save_many_localized(
    {
      'first': {'en': ({'title': 'First', 'code': 'A'}, 'Body')},
      'second': {'en': ({'title': 'Second', 'code': 'B'}, 'Body')},
    }
  )

  assert set(results) == {'first', 'second'}
  assert service.i18n_documents.has_entry('first')
  assert service.i18n_documents.has_entry('second')
  failures = [
    record
    for record in caplog.records
    if 'on_change failed for articles/' in record.message
  ]
  assert len(failures) == 2


def test_batch_stale_etag_leaves_all_entries_unchanged(tmp_path):
  service = _service(tmp_path)
  originals = {
    slug: service.save_localized(
      slug,
      {
        'en': ({'title': slug, 'code': slug.upper()}, f'{slug} English'),
        'ru': ({'title': slug, 'code': slug.upper()}, f'{slug} Russian'),
      },
    )
    for slug in ('first', 'second')
  }
  before = {
    path: path.read_bytes()
    for slug in originals
    for path in service.i18n_documents.inventory()[slug].values()
  }

  with pytest.raises(store.ConflictError):
    service.save_many_localized(
      {
        'first': {'en': ({'title': 'Changed first', 'code': 'FIRST'}, 'New')},
        'second': {
          'en': ({'title': 'Changed second', 'code': 'SECOND'}, 'New')
        },
      },
      expected_entry_etags={
        'first': originals['first'].entry_etag,
        'second': 'stale-entry-etag',
      },
      expected_exists={'first': True, 'second': True},
    )

  assert {path: path.read_bytes() for path in before} == before
  assert not list(tmp_path.rglob('.*.stage-*'))


def test_batch_schema_failure_leaves_all_entries_unchanged(tmp_path):
  service = _service(tmp_path)
  for slug in ('first', 'second'):
    service.save_localized(
      slug,
      {'en': ({'title': slug, 'code': slug.upper()}, f'{slug} body')},
    )
  before = {
    path: path.read_bytes()
    for slug in ('first', 'second')
    for path in service.i18n_documents.inventory()[slug].values()
  }

  with pytest.raises(ValidationError):
    service.save_many_localized(
      {
        'first': {'en': ({'title': 'Changed first', 'code': 'FIRST'}, 'New')},
        'second': {
          'en': (
            {'title': 'Changed second', 'code': 'SECOND', 'unexpected': True},
            'New',
          )
        },
      },
      expected_exists={'first': True, 'second': True},
    )

  assert {path: path.read_bytes() for path in before} == before
  assert not list(tmp_path.rglob('.*.stage-*'))


def test_batch_blocking_validator_failure_leaves_all_entries_unchanged(
  tmp_path,
):
  service = _service(tmp_path)
  for slug in ('first', 'second'):
    service.save_localized(
      slug,
      {'en': ({'title': slug, 'code': slug.upper()}, f'{slug} body')},
    )
  before = {
    path: path.read_bytes()
    for slug in ('first', 'second')
    for path in service.i18n_documents.inventory()[slug].values()
  }
  service.validators = (
    Validator(
      name='reject_second',
      argv=(
        sys.executable,
        '-c',
        "import sys; sys.exit(1 if 'second' in sys.argv[1] else 0)",
        '{path}',
      ),
      blocking=('error',),
      run='write',
    ),
  )

  with pytest.raises(BlockingValidationError):
    service.save_many_localized(
      {
        'first': {'en': ({'title': 'Changed first', 'code': 'FIRST'}, 'New')},
        'second': {
          'en': ({'title': 'Changed second', 'code': 'SECOND'}, 'New')
        },
      },
      expected_exists={'first': True, 'second': True},
    )

  assert {path: path.read_bytes() for path in before} == before
  assert not list(tmp_path.rglob('.*.stage-*'))
