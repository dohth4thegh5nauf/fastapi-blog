"""Tests for schema-aware multi-locale document service operations."""

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
