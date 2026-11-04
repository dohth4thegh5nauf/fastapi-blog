from dataclasses import replace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fastapi_blog import store
from fastapi_blog.config import CollectionSpec
from fastapi_blog.editor import get_api_router
from fastapi_blog.i18n_collections import I18nConfig
from fastapi_blog.models import FieldSpec, FrontmatterSchema
from fastapi_blog.service import DocumentService
from fastapi_blog.templates import SLUG_TAGS_DEFAULT, parse_template


def make_service(tmp_path, policy=None):
  schema = FrontmatterSchema(
    fields=(
      FieldSpec('title', required=True, i18n='translate'),
      FieldSpec(
        'status',
        required=True,
        transitions={
          'initial': ['draft'],
          'allowed': [
            {'from': 'draft', 'to': 'published', 'permission': 'publish'}
          ],
        },
      ),
    )
  )
  spec = CollectionSpec(
    'notes',
    tmp_path,
    schema=schema,
    i18n=I18nConfig(('en', 'ru'), 'en'),
    document_authorize=policy,
  )
  return DocumentService(
    store.DocumentStore(spec.to_collection()), schema, collection_spec=spec
  )


def test_document_policy_authorizes_generated_slug_before_writing(tmp_path):
  calls = []
  schema = FrontmatterSchema(
    fields=(FieldSpec('title', required=True, role='title'),)
  )

  def policy(user, action, collection, slug, locale, before, after):
    calls.append((action, collection, slug, locale, before, after))
    return True

  spec = CollectionSpec(
    'notes',
    tmp_path,
    schema=schema,
    slug_template=parse_template('{title_slug}', SLUG_TAGS_DEFAULT, {'title'}),
    document_authorize=policy,
  )
  service = DocumentService(
    store.DocumentStore(spec.to_collection()), schema, collection_spec=spec
  )

  result = service.save(None, {'title': 'Generated Note'}, 'Body')

  assert result.slug == 'generated-note'
  assert calls == [
    (
      'create',
      'notes',
      'generated-note',
      None,
      None,
      {'title': 'Generated Note'},
    )
  ]
  assert (tmp_path / 'generated-note.md').is_file()


def test_document_policy_can_deny_generated_slug_before_writing(tmp_path):
  schema = FrontmatterSchema(
    fields=(FieldSpec('title', required=True, role='title'),)
  )
  spec = CollectionSpec(
    'notes',
    tmp_path,
    schema=schema,
    slug_template=parse_template('{title_slug}', SLUG_TAGS_DEFAULT, {'title'}),
    document_authorize=lambda *args: 'Generated notes are not allowed',
  )
  service = DocumentService(
    store.DocumentStore(spec.to_collection()), schema, collection_spec=spec
  )

  with pytest.raises(store.OperationNotAllowedError, match='Generated notes'):
    service.save(None, {'title': 'Generated Note'}, 'Body')

  assert not (tmp_path / 'generated-note.md').exists()


def test_transition_policy_rejects_invalid_values_before_writing(tmp_path):
  service = make_service(tmp_path)
  with pytest.raises(ValueError, match='Initial value'):
    service.save_localized(
      'note', {'en': ({'title': 'Title', 'status': 'published'}, 'Body')}
    )
  assert not (tmp_path / 'note.md').exists()
  service.save_localized(
    'note', {'en': ({'title': 'Title', 'status': 'draft'}, 'Body')}
  )
  with pytest.raises(store.OperationNotAllowedError, match='publish'):
    service.save_localized(
      'note', {'en': ({'title': 'Title', 'status': 'published'}, 'Body')}
    )
  assert (
    service.i18n_documents.read('note', 'en').frontmatter['status'] == 'draft'
  )


def test_transitions_inside_object_lists_require_stable_row_identity():
  with pytest.raises(ValueError, match='no stable identity'):
    FieldSpec(
      'steps',
      type='list[object]',
      fields=(
        FieldSpec(
          'status',
          transitions={
            'initial': ['draft'],
            'allowed': [{'from': 'draft', 'to': 'done'}],
          },
        ),
      ),
    )


def test_document_policy_receives_full_user_and_can_allow_transition(tmp_path):
  calls = []

  def policy(user, action, collection, slug, locale, before, after):
    calls.append((user, action, collection, slug, locale))
    return True

  service = make_service(tmp_path, policy)
  user = {'username': 'editor', 'role': 'editor'}
  service.save_localized(
    'note', {'en': ({'title': 'Title', 'status': 'draft'}, 'Body')}, user=user
  )
  service.save_localized(
    'note',
    {'en': ({'title': 'Title', 'status': 'published'}, 'Body')},
    user=user,
  )
  assert (user, 'publish', 'notes', 'note', 'en') in calls
  assert (user, 'transition', 'notes', 'note', 'en') in calls


def test_api_denies_document_read_and_write(tmp_path):
  service = make_service(tmp_path)
  service.save_localized(
    'note', {'en': ({'title': 'Title', 'status': 'draft'}, 'Body')}
  )
  spec = replace(
    service.collection_spec,
    document_authorize=lambda user, action, collection, slug, locale, before, after: (
      'Denied by policy' if action in ('read', 'update') else True
    ),
  )
  app = FastAPI()
  app.include_router(
    get_api_router(require_auth=False, collection_spec=spec),
    prefix='/api/notes',
  )
  client = TestClient(app)
  assert client.get('/api/notes/note').status_code == 403
  response = client.put(
    '/api/notes/note',
    json={
      'frontmatter': {'title': 'Changed', 'status': 'draft'},
      'content': 'Body',
    },
  )
  assert response.status_code == 403
  assert (
    service.i18n_documents.read('note', 'en').frontmatter['title'] == 'Title'
  )


def test_batch_denial_leaves_every_entry_unchanged(tmp_path):
  def policy(user, action, collection, slug, locale, before, after):
    return 'Entry denied' if slug == 'second' else True

  service = make_service(tmp_path, policy)
  with pytest.raises(store.OperationNotAllowedError, match='Entry denied'):
    service.save_many_localized(
      {
        'first': {'en': ({'title': 'First', 'status': 'draft'}, 'Body')},
        'second': {'en': ({'title': 'Second', 'status': 'draft'}, 'Body')},
      }
    )
  assert not (tmp_path / 'first.md').exists()
  assert not (tmp_path / 'second.md').exists()


def test_admin_list_and_dashboard_exclude_denied_documents(tmp_path):
  pytest.importorskip('starlette_admin')
  from fastapi_blog.admin.markdown_crud import MarkdownFileManager
  from fastapi_blog.admin.views import load_posts_for_home

  service = make_service(tmp_path)
  service.save_localized(
    'secret', {'en': ({'title': 'Secret', 'status': 'draft'}, 'Body')}
  )
  service.save_localized(
    'public', {'en': ({'title': 'Visible', 'status': 'draft'}, 'Body')}
  )
  spec = replace(
    service.collection_spec,
    document_authorize=lambda user, action, collection, slug, locale, before, after: (
      slug != 'secret'
    ),
  )
  manager = MarkdownFileManager(str(tmp_path), collection_spec=spec)
  assert [
    post.slug for post in manager.list_posts(user={'role': 'editor'})
  ] == ['public']
  with pytest.raises(store.OperationNotAllowedError):
    manager.load_post('secret', user={'role': 'editor'})
  assert [
    post.slug
    for post in load_posts_for_home(
      str(tmp_path), spec.schema, spec, {'role': 'editor'}
    )
  ] == ['public']
