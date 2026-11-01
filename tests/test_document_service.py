"""Tests for schema-aware document service operations."""

import pytest

from fastapi_blog import store
from fastapi_blog.config import CollectionSpec
from fastapi_blog.issues import Issue
from fastapi_blog.models import FieldSpec, FrontmatterSchema
from fastapi_blog.service import BlockingValidationError, DocumentService


@pytest.fixture
def service(tmp_path):
  schema = FrontmatterSchema(
    fields=(
      FieldSpec('title', required=True),
      FieldSpec('status', required=True, choices=('draft', 'published')),
      FieldSpec('immutable_id', on_create='uuid', read_only=True),
    ),
    extra='allow',
  )
  collection = CollectionSpec('notes', tmp_path, schema=schema)
  documents = store.DocumentStore(collection.to_collection())
  return DocumentService(documents, schema, collection_spec=collection)


def test_service_validates_schema_and_applies_on_create(service):
  result = service.save(
    'first-note',
    {'title': 'First', 'status': 'draft', 'unmodeled': 'preserved'},
    'Body',
  )

  record = service.documents.read(result.slug)
  assert result.status == 'created'
  assert record.frontmatter['title'] == 'First'
  assert record.frontmatter['status'] == 'draft'
  assert record.frontmatter['immutable_id']
  assert record.frontmatter['unmodeled'] == 'preserved'
  assert record.etag == result.etag


def test_service_preserves_omitted_read_only_fields_and_checks_etag(service):
  created = service.save(
    'first-note', {'title': 'First', 'status': 'draft'}, 'Body'
  )
  original = service.documents.read('first-note')

  updated = service.save(
    'first-note',
    {'title': 'Updated', 'status': 'published'},
    'Changed body',
    if_match=created.etag,
    expected_exists=True,
  )
  record = service.documents.read('first-note')

  assert updated.status == 'updated'
  assert (
    record.frontmatter['immutable_id']
    == original.frontmatter['immutable_id']
  )
  assert record.frontmatter['title'] == 'Updated'
  assert record.body.strip() == 'Changed body'

  with pytest.raises(store.ConflictError) as conflict:
    service.save(
      'first-note',
      {'title': 'Stale', 'status': 'draft'},
      'Stale body',
      if_match=created.etag,
      expected_exists=True,
    )
  assert conflict.value.status_code == 412
  assert service.documents.read('first-note').body.strip() == 'Changed body'


def test_service_rejects_create_update_races(service):
  service.save('already-exists', {'title': 'A', 'status': 'draft'}, 'Body')

  with pytest.raises(store.ConflictError) as conflict:
    service.save(
      'already-exists',
      {'title': 'B', 'status': 'draft'},
      'Body',
      expected_exists=False,
    )
  assert conflict.value.status_code == 409

  with pytest.raises(store.ConflictError) as conflict:
    service.save(
      'deleted-during-edit',
      {'title': 'B', 'status': 'draft'},
      'Body',
      expected_exists=True,
    )
  assert conflict.value.status_code == 409


def test_service_rejects_schema_values(service):
  with pytest.raises(ValueError):
    service.save(
      'invalid-status', {'title': 'Bad', 'status': 'unknown'}, 'Body'
    )


def test_blocking_validation_rolls_back_a_previous_document(
  service, monkeypatch
):
  created = service.save(
    'first-note', {'title': 'First', 'status': 'draft'}, 'Original body'
  )
  before = service.documents.path_for('first-note').read_bytes()
  issue = Issue(
    'error',
    'validator.failed',
    'A blocking validation failed',
    slug='first-note',
  )
  monkeypatch.setattr(
    'fastapi_blog.service.run_blocking', lambda *args, **kwargs: [issue]
  )

  with pytest.raises(BlockingValidationError) as error:
    service.save(
      'first-note',
      {'title': 'Changed', 'status': 'published'},
      'Rejected body',
      if_match=created.etag,
      expected_exists=True,
    )

  assert error.value.issues == [issue]
  assert service.documents.path_for('first-note').read_bytes() == before
