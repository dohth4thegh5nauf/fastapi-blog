"""Contract tests for the localized collection REST endpoints."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from fastapi_blog.config import CollectionSpec
from fastapi_blog.editor import get_api_router
from fastapi_blog.i18n_collections import I18nConfig
from fastapi_blog.models import FieldSpec, FrontmatterSchema


def _client(tmp_path, *, require_if_match=False):
  schema = FrontmatterSchema(
    fields=(
      FieldSpec('title', required=True, i18n='translate'),
      FieldSpec('code', required=True, i18n='duplicate'),
    ),
    extra='forbid',
  )
  collection = CollectionSpec(
    'articles',
    tmp_path / 'articles',
    schema=schema,
    i18n=I18nConfig(('en', 'ru'), 'en', translate_body=True),
  )
  app = FastAPI()
  app.include_router(
    get_api_router(
      collection_spec=collection,
      require_auth=False,
      require_if_match=require_if_match,
    ),
    prefix='/api/articles',
  )
  return TestClient(app)


def test_put_one_locale_and_get_fallback(tmp_path):
  client = _client(tmp_path)
  created = client.put(
    '/api/articles/hello',
    json={
      'frontmatter': {'title': 'Hello', 'code': 'A'},
      'content': 'English body',
    },
  )
  assert created.status_code == 201
  assert created.headers['ETag']

  translated = client.put(
    '/api/articles/hello?locale=ru',
    json={'frontmatter': {}, 'content': 'Russian body'},
  )
  assert translated.status_code == 200
  assert translated.json()['locales_present'] == ['en', 'ru']

  raw = client.get('/api/articles/hello?locale=ru')
  assert raw.status_code == 200
  assert raw.json()['locale'] == 'ru'
  assert raw.json()['fallback_used'] is False
  assert raw.json()['content'] == 'Russian body'

  fallback = client.get('/api/articles/hello?locale=fr&fallback=true')
  assert fallback.status_code == 400


def test_legacy_routes_cannot_bypass_localized_storage(tmp_path):
  client = _client(tmp_path)
  payload = {'frontmatter': {'title': 'Hello', 'code': 'A'}, 'content': 'Body'}
  assert client.put('/api/articles/hello', json=payload).status_code == 201
  assert (
    client.post('/api/articles/create/other', json=payload).status_code == 405
  )
  assert (
    client.put('/api/articles/update/hello', json=payload).status_code == 405
  )
  assert (
    client.post(
      '/api/articles/save', json={'slug': 'hello', **payload}
    ).status_code
    == 405
  )
  assert not (tmp_path / 'articles' / 'other.md').exists()


def test_delete_entry_requires_explicit_cascade_and_current_etag(tmp_path):
  client = _client(tmp_path)
  created = client.put(
    '/api/articles/hello',
    json={
      'locales': {
        'en': {
          'frontmatter': {'title': 'Hello', 'code': 'A'},
          'content': 'Body',
        },
        'ru': {'frontmatter': {'title': 'Привет'}, 'content': 'Текст'},
      }
    },
  )
  etag = created.json()['entry_etag']
  assert (
    client.delete(
      '/api/articles/delete/hello', headers={'If-Match': etag}
    ).status_code
    == 409
  )
  assert (
    client.delete(
      '/api/articles/delete/hello?cascade=true', headers={'If-Match': 'stale'}
    ).status_code
    == 412
  )
  assert client.get('/api/articles/hello?locale=ru').status_code == 200
  assert (
    client.delete(
      '/api/articles/delete/hello?cascade=true', headers={'If-Match': etag}
    ).status_code
    == 204
  )


def test_get_missing_translation_uses_configured_fallback(tmp_path):
  client = _client(tmp_path)
  assert (
    client.put(
      '/api/articles/hello',
      json={
        'frontmatter': {'title': 'Hello', 'code': 'A'},
        'content': 'English body',
      },
    ).status_code
    == 201
  )

  response = client.get('/api/articles/hello?locale=ru')
  assert response.status_code == 200
  assert response.json()['locale'] == 'en'
  assert response.json()['fallback_used'] is True
  assert response.json()['locales_present'] == ['en']


def test_put_whole_entry_checks_aggregate_etag(tmp_path):
  client = _client(tmp_path)
  response = client.put(
    '/api/articles/hello',
    json={
      'locales': {
        'en': {
          'frontmatter': {'title': 'Hello', 'code': 'A'},
          'content': 'English body',
        },
        'ru': {'frontmatter': {}, 'content': 'Russian body'},
      }
    },
  )
  assert response.status_code == 201
  assert response.headers['ETag'] == response.json()['entry_etag']

  stale = client.put(
    '/api/articles/hello',
    headers={'If-Match': 'stale'},
    json={
      'locales': {
        'en': {
          'frontmatter': {'title': 'Changed', 'code': 'A'},
          'content': 'Changed body',
        }
      }
    },
  )
  assert stale.status_code == 412
  current = client.get('/api/articles/hello?locale=en')
  assert current.json()['frontmatter']['title'] == 'Hello'


def test_put_translation_checks_locale_etag(tmp_path):
  client = _client(tmp_path)
  assert (
    client.put(
      '/api/articles/hello',
      json={
        'frontmatter': {'title': 'Hello', 'code': 'A'},
        'content': 'English body',
      },
    ).status_code
    == 201
  )
  created_ru = client.put(
    '/api/articles/hello?locale=ru',
    json={'frontmatter': {}, 'content': 'Russian body'},
  )
  assert created_ru.status_code == 200

  stale = client.put(
    '/api/articles/hello?locale=ru',
    headers={'If-Match': 'stale'},
    json={'frontmatter': {}, 'content': 'Changed body'},
  )
  assert stale.status_code == 412
  actual = client.get('/api/articles/hello?locale=ru')
  assert actual.json()['content'] == 'Russian body'


def test_localized_openapi_exposes_get_and_put_contracts(tmp_path):
  client = _client(tmp_path)
  schema = client.get('/openapi.json').json()
  assert '/api/articles/{slug}' in schema['paths']
  path = schema['paths']['/api/articles/{slug}']
  assert 'get' in path and 'put' in path
  assert any(item['name'] == 'locale' for item in path['get']['parameters'])
  assert 'requestBody' in path['put']


def test_missing_locale_can_be_created_with_fallback_etag(tmp_path):
  client = _client(tmp_path, require_if_match=True)
  created = client.put(
    '/api/articles/hello',
    json={
      'frontmatter': {'title': 'Hello', 'code': 'A'},
      'content': 'English body',
    },
  )
  assert created.status_code == 201

  fallback = client.get('/api/articles/hello?locale=ru')
  assert fallback.status_code == 200
  assert fallback.json()['fallback_used'] is True
  assert fallback.json()['entry_etag']

  translated = client.put(
    '/api/articles/hello?locale=ru',
    headers={'If-Match': fallback.headers['ETag']},
    json={'frontmatter': {}, 'content': 'Russian body'},
  )
  assert translated.status_code == 200
  assert client.get('/api/articles/hello?locale=ru').json()['content'] == (
    'Russian body'
  )


def test_if_match_is_required_for_update_but_not_create(tmp_path):
  client = _client(tmp_path, require_if_match=True)
  created = client.put(
    '/api/articles/hello',
    json={
      'frontmatter': {'title': 'Hello', 'code': 'A'},
      'content': 'English body',
    },
  )
  assert created.status_code == 201
  missing = client.put(
    '/api/articles/hello',
    json={
      'frontmatter': {'title': 'Changed', 'code': 'A'},
      'content': 'Changed body',
    },
  )
  assert missing.status_code == 428
