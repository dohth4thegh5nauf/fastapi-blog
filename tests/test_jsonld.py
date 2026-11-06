"""Tests for JSON-LD emission."""

import urllib.request

import pytest

from fastapi_blog.jsonld import (
  ContextUnavailableError,
  JsonLdError,
  collection_to_jsonld,
  document_to_jsonld,
  pyld_available,
  resolve_context,
)
from fastapi_blog.jsonld import (
  uncovered_keys as jsonld_uncovered_keys,
)
from fastapi_blog.models import FieldSpec, FrontmatterSchema, JsonLdConfig


NOTES_SCHEMA = FrontmatterSchema(
  fields=(
    FieldSpec('doc_id', alias='@id', type='str', read_only=True),
    FieldSpec('kind', alias='@type', default='Note', hidden=True),
    FieldSpec('title', required=True, role='title'),
    FieldSpec('status', required=True, choices=('draft', 'active', 'retired')),
    FieldSpec('pub_date', alias='date', type='date', on_create='today'),
    FieldSpec('tags', type='list[str]', role='tags'),
    FieldSpec('empty_field', required=False),
  ),
  extra='forbid',
  jsonld=JsonLdConfig(
    context={'@vocab': 'https://example.org/vocab#'},
    base='https://example.org/',
    id_template='{base}{collection}/{slug}',
    type='Note',
    content_term='content',
  ),
)


# --- JsonLdConfig ------------------------------------------------------------


def test_jsonld_config_to_dict_omits_defaults():
  config = JsonLdConfig(type='Note')
  assert config.to_dict() == {'type': 'Note'}


def test_jsonld_config_from_dict_round_trips():
  data = {'context': {'@vocab': 'https://x/'}, 'type': 'Note'}
  config = JsonLdConfig.from_dict(data)
  assert config.context == {'@vocab': 'https://x/'}
  assert config.type == 'Note'
  assert config.to_dict() == data


def test_jsonld_config_from_dict_rejects_unknown_key():
  with pytest.raises(ValueError, match='Unknown jsonld option'):
    JsonLdConfig.from_dict({'bogus': 1})


def test_schema_from_dict_parses_jsonld_section():
  schema = FrontmatterSchema.from_dict(
    {
      'fields': {'title': {'required': True}},
      'jsonld': {'type': 'Note', 'content_term': 'content'},
    }
  )
  assert schema.jsonld is not None
  assert schema.jsonld.type == 'Note'
  assert schema.jsonld.content_term == 'content'


def test_schema_to_dict_round_trips_jsonld_section():
  schema = FrontmatterSchema(
    fields=(FieldSpec('title', required=True),),
    jsonld=JsonLdConfig(type='Note'),
  )
  data = schema.to_dict()
  assert data['jsonld'] == {'type': 'Note'}
  rebuilt = FrontmatterSchema.from_dict(data)
  assert rebuilt.jsonld == schema.jsonld


def test_with_extra_preserves_jsonld_config():
  schema = FrontmatterSchema(
    fields=(FieldSpec('title'),), jsonld=JsonLdConfig(type='Note')
  )
  assert schema.with_extra('allow').jsonld == schema.jsonld


# --- document_to_jsonld -------------------------------------------------------


def test_document_to_jsonld_uses_field_with_id_alias():
  frontmatter = {
    '@id': 'note:0007',
    'title': 'Use plain files',
    'status': 'active',
    'date': '2026-10-01',
    'tags': ['storage'],
  }
  result = document_to_jsonld(
    frontmatter, schema=NOTES_SCHEMA, slug='0007', collection='notes'
  )
  assert result['@id'] == 'note:0007'
  assert result['@context'] == {'@vocab': 'https://example.org/vocab#'}
  assert result['title'] == 'Use plain files'
  assert result['status'] == 'active'
  assert result['date'] == '2026-10-01'
  assert result['tags'] == ['storage']


def test_document_to_jsonld_falls_back_to_id_template_when_no_id_field():
  frontmatter = {'title': 'Hi', 'status': 'draft'}
  result = document_to_jsonld(
    frontmatter, schema=NOTES_SCHEMA, slug='hello', collection='notes'
  )
  assert result['@id'] == 'https://example.org/notes/hello'


def test_document_to_jsonld_falls_back_to_configured_type():
  frontmatter = {'title': 'Hi', 'status': 'draft'}
  result = document_to_jsonld(frontmatter, schema=NOTES_SCHEMA, slug='hello')
  assert result['@type'] == 'Note'


def test_document_to_jsonld_prefers_type_field_over_config():
  frontmatter = {'title': 'Hi', 'status': 'draft', '@type': 'SpecialNote'}
  result = document_to_jsonld(frontmatter, schema=NOTES_SCHEMA, slug='hello')
  assert result['@type'] == 'SpecialNote'


def test_document_to_jsonld_omits_none_and_empty_values():
  frontmatter = {'title': 'Hi', 'status': 'draft', 'empty_field': None}
  result = document_to_jsonld(frontmatter, schema=NOTES_SCHEMA, slug='hello')
  assert 'empty_field' not in result
  assert 'tags' not in result  # never set at all


def test_document_to_jsonld_converts_dates_to_iso_strings():
  import datetime

  frontmatter = {
    'title': 'Hi',
    'status': 'draft',
    'date': datetime.date(2026, 10, 1),
  }
  result = document_to_jsonld(frontmatter, schema=NOTES_SCHEMA, slug='hello')
  assert result['date'] == '2026-10-01'


def test_document_to_jsonld_emits_body_only_with_content_term():
  frontmatter = {'title': 'Hi', 'status': 'draft'}
  result = document_to_jsonld(
    frontmatter, schema=NOTES_SCHEMA, slug='hello', content='Body text.'
  )
  assert result['content'] == 'Body text.'

  no_content_term_schema = FrontmatterSchema(
    fields=NOTES_SCHEMA.fields,
    jsonld=JsonLdConfig(type='Note'),  # no content_term
  )
  result2 = document_to_jsonld(
    frontmatter,
    schema=no_content_term_schema,
    slug='hello',
    content='Body text.',
  )
  assert 'content' not in result2


def test_document_to_jsonld_without_jsonld_config_still_works():
  schema = FrontmatterSchema(fields=(FieldSpec('title', required=True),))
  frontmatter = {'title': 'Hi'}
  result = document_to_jsonld(frontmatter, schema=schema, slug='hello')
  assert result == {'title': 'Hi'}


def test_document_to_jsonld_follows_schema_field_order():
  schema = FrontmatterSchema(
    fields=(
      FieldSpec('b', required=False, default='b-val'),
      FieldSpec('a', required=False, default='a-val'),
    )
  )
  frontmatter = {'b': 'b-val', 'a': 'a-val'}
  result = document_to_jsonld(frontmatter, schema=schema, slug='x')
  assert list(result.keys()) == ['b', 'a']


# --- collection_to_jsonld -----------------------------------------------------


def test_collection_to_jsonld_sorts_by_id_then_slug():
  documents = [
    ('c-post', {'@id': 'note:c', 'title': 'C', 'status': 'active'}, None),
    ('a-post', {'@id': 'note:a', 'title': 'A', 'status': 'active'}, None),
    ('b-post', {'@id': 'note:b', 'title': 'B', 'status': 'active'}, None),
  ]
  result = collection_to_jsonld(
    documents, schema=NOTES_SCHEMA, collection='notes'
  )
  assert [node['@id'] for node in result['@graph']] == [
    'note:a',
    'note:b',
    'note:c',
  ]


def test_collection_to_jsonld_sets_context_once_not_per_node():
  documents = [
    ('a', {'@id': 'note:a', 'title': 'A', 'status': 'active'}, None),
  ]
  result = collection_to_jsonld(
    documents, schema=NOTES_SCHEMA, collection='notes'
  )
  assert result['@context'] == {'@vocab': 'https://example.org/vocab#'}
  assert '@context' not in result['@graph'][0]


def test_collection_to_jsonld_context_argument_overrides_schema_default():
  documents = [
    ('a', {'@id': 'note:a', 'title': 'A', 'status': 'active'}, None),
  ]
  custom_context = {'@vocab': 'https://other.example/'}
  result = collection_to_jsonld(
    documents, schema=NOTES_SCHEMA, context=custom_context
  )
  assert result['@context'] == custom_context


def test_collection_to_jsonld_omits_context_when_none_configured():
  schema = FrontmatterSchema(fields=(FieldSpec('title', required=True),))
  documents = [('a', {'title': 'A'}, None)]
  result = collection_to_jsonld(documents, schema=schema)
  assert '@context' not in result


def test_collection_to_jsonld_is_deterministic_regardless_of_input_order():
  docs_order_1 = [
    ('b', {'@id': 'note:b', 'title': 'B', 'status': 'active'}, None),
    ('a', {'@id': 'note:a', 'title': 'A', 'status': 'active'}, None),
  ]
  docs_order_2 = list(reversed(docs_order_1))
  result1 = collection_to_jsonld(docs_order_1, schema=NOTES_SCHEMA)
  result2 = collection_to_jsonld(docs_order_2, schema=NOTES_SCHEMA)
  assert result1 == result2


# --- Lost terms ---------------------------------------------------


def test_uncovered_keys_reports_terms_the_context_drops():
  schema = FrontmatterSchema(
    fields=(
      FieldSpec('doc_id', alias='@id', type='str'),
      FieldSpec('title', required=True, role='title'),
      FieldSpec('note_status', alias='status'),
    ),
    jsonld=JsonLdConfig(context={'title': 'https://example.org/title'}),
  )
  assert jsonld_uncovered_keys(schema) == ['status']


def test_uncovered_keys_covers_compact_iris_through_the_prefix():
  schema = FrontmatterSchema(
    fields=(FieldSpec('state', alias='ex:state'),),
    jsonld=JsonLdConfig(context={'ex': 'https://example.org/'}),
  )
  assert jsonld_uncovered_keys(schema) == []


def test_uncovered_keys_vocab_covers_everything():
  schema = FrontmatterSchema(
    fields=(FieldSpec('title', required=True),),
    jsonld=JsonLdConfig(context={'@vocab': 'https://example.org/#'}),
  )
  assert jsonld_uncovered_keys(schema) == []


def test_uncovered_keys_counts_the_content_term():
  schema = FrontmatterSchema(
    fields=(FieldSpec('title', required=True),),
    jsonld=JsonLdConfig(
      context={'title': 'https://example.org/title'}, content_term='content'
    ),
  )
  assert jsonld_uncovered_keys(schema) == ['content']


def test_uncovered_keys_merges_a_list_of_contexts():
  schema = FrontmatterSchema(
    fields=(
      FieldSpec('title', required=True),
      FieldSpec('date', type='date'),
    ),
    jsonld=JsonLdConfig(
      context=[
        {'title': 'https://example.org/title'},
        {'date': 'https://example.org/date'},
      ]
    ),
  )
  assert jsonld_uncovered_keys(schema) == []


def test_uncovered_keys_skips_context_urls_without_loading_them():
  """A URL context item can't be inspected; it must not crash the check."""
  schema = FrontmatterSchema(
    fields=(FieldSpec('title', required=True),),
    jsonld=JsonLdConfig(context=['https://example.org/context.jsonld']),
  )
  assert jsonld_uncovered_keys(schema) == ['title']


def test_uncovered_keys_without_context_covers_nothing():
  schema = FrontmatterSchema(
    fields=(FieldSpec('title', required=True),),
  )
  assert jsonld_uncovered_keys(schema) == ['title']


# --- Contexts: files and remote URLs -------------------------------


def test_resolve_context_returns_none_without_a_config_or_context():
  assert resolve_context(FrontmatterSchema()) is None
  schema = FrontmatterSchema(jsonld=JsonLdConfig(type='Note'))
  assert resolve_context(schema) is None


def test_resolve_context_loads_a_file_inside_the_project(tmp_path):
  (tmp_path / 'ctx.yaml').write_text(
    '"@context":\n  title: https://example.org/t\n', encoding='utf-8'
  )
  schema = FrontmatterSchema(
    fields=(FieldSpec('title', required=True),),
    jsonld=JsonLdConfig(context='ctx.yaml'),
  )
  assert resolve_context(schema, project_root=tmp_path) == {
    'title': 'https://example.org/t'
  }


def test_resolve_context_refuses_a_file_outside_the_project(tmp_path):
  schema = FrontmatterSchema(
    fields=(FieldSpec('title', required=True),),
    jsonld=JsonLdConfig(context='../outside.yaml'),
  )
  with pytest.raises(ContextUnavailableError, match='outside the project'):
    resolve_context(schema, project_root=tmp_path)


def test_resolve_context_enforces_the_file_size_limit(tmp_path):
  (tmp_path / 'big.yaml').write_text(
    '"@context":\n  title: https://example.org/t\n', encoding='utf-8'
  )
  schema = FrontmatterSchema(
    fields=(FieldSpec('title', required=True),),
    jsonld=JsonLdConfig(context='big.yaml', max_context_bytes=4),
  )
  with pytest.raises(ContextUnavailableError, match='larger'):
    resolve_context(schema, project_root=tmp_path)


def test_resolve_context_refuses_a_url_not_in_the_allowlist(tmp_path):
  schema = FrontmatterSchema(
    fields=(FieldSpec('title', required=True),),
    jsonld=JsonLdConfig(context='https://evil.example/c.jsonld'),
  )
  with pytest.raises(ContextUnavailableError, match='allow_remote_contexts'):
    resolve_context(schema, project_root=tmp_path)


@pytest.mark.skipif(not pyld_available(), reason='Requires the jsonld extra')
def test_resolve_context_fetches_an_allowed_url(monkeypatch, tmp_path):
  """An allow-listed URL is fetched through a size-limited opener."""

  class _FakeResponse:
    def __init__(self, data):
      self._data = data

    def read(self, limit):
      return self._data[:limit]

    def __enter__(self):
      return self

    def __exit__(self, *args):
      return False

  class _FakeOpener:
    def __init__(self, data):
      self._data = data

    def open(self, request, timeout):
      return _FakeResponse(self._data)

  payload = b'{"@context": {"title": "https://example.org/t"}}'
  monkeypatch.setattr(
    urllib.request,
    'build_opener',
    lambda *handlers: _FakeOpener(payload),
  )
  schema = FrontmatterSchema(
    fields=(FieldSpec('title', required=True),),
    jsonld=JsonLdConfig(
      context='https://example.org/c.jsonld',
      allow_remote_contexts=['https://example.org/c.jsonld'],
    ),
  )
  assert resolve_context(schema, project_root=tmp_path) == {
    'title': 'https://example.org/t'
  }


@pytest.mark.skipif(not pyld_available(), reason='Requires the jsonld extra')
def test_resolve_context_reports_a_url_over_the_size_limit(
  monkeypatch, tmp_path
):
  class _FakeResponse:
    def read(self, limit):
      return b'x' * (limit + 1)

    def __enter__(self):
      return self

    def __exit__(self, *args):
      return False

  class _FakeOpener:
    def open(self, request, timeout):
      return _FakeResponse()

  monkeypatch.setattr(
    urllib.request, 'build_opener', lambda *handlers: _FakeOpener()
  )
  schema = FrontmatterSchema(
    fields=(FieldSpec('title', required=True),),
    jsonld=JsonLdConfig(
      context='https://example.org/c.jsonld',
      allow_remote_contexts=['https://example.org/c.jsonld'],
      max_context_bytes=8,
    ),
  )
  with pytest.raises(ContextUnavailableError, match='larger'):
    resolve_context(schema, project_root=tmp_path)


def test_remote_contexts_need_the_jsonld_extra(monkeypatch, tmp_path):
  monkeypatch.setattr('importlib.util.find_spec', lambda name: None)
  schema = FrontmatterSchema(
    fields=(FieldSpec('title', required=True),),
    jsonld=JsonLdConfig(
      context='https://example.org/c.jsonld',
      allow_remote_contexts=['https://example.org/c.jsonld'],
    ),
  )
  with pytest.raises(ContextUnavailableError, match='jsonld'):
    resolve_context(schema, project_root=tmp_path)


def test_jsonld_config_validates_the_allowlist_and_limits():
  with pytest.raises(ValueError, match=r'http\(s\) URLs'):
    JsonLdConfig(allow_remote_contexts=['ftp://example.org/c'])
  with pytest.raises(ValueError, match='positive integer'):
    JsonLdConfig(max_context_bytes=0)
  with pytest.raises(ValueError, match='positive integer'):
    JsonLdConfig(max_documents=True)
  config = JsonLdConfig.from_dict({'allow_remote_contexts': ['https://a/']})
  assert config.allow_remote_contexts == ('https://a/',)


def test_collection_export_respects_max_documents():
  schema = FrontmatterSchema(
    fields=(FieldSpec('title', required=True),),
    jsonld=JsonLdConfig(max_documents=1),
  )
  with pytest.raises(JsonLdError, match='max_documents'):
    collection_to_jsonld(
      [('a', {'title': 'A'}, None), ('b', {'title': 'B'}, None)],
      schema=schema,
    )


def test_document_export_accepts_a_resolved_context_override():
  schema = FrontmatterSchema(
    fields=(FieldSpec('title', required=True),),
    jsonld=JsonLdConfig(context={'title': 'x'}),
  )
  node = document_to_jsonld(
    {'title': 'Hi'}, schema=schema, slug='a', context={'title': 'y'}
  )
  assert node['@context'] == {'title': 'y'}


def test_uncovered_keys_resolves_a_local_context_file(tmp_path):
  (tmp_path / 'ctx.yaml').write_text(
    '"@context":\n  title: https://example.org/t\n', encoding='utf-8'
  )
  schema = FrontmatterSchema(
    fields=(
      FieldSpec('title', required=True),
      FieldSpec('pub_date', alias='date', type='date'),
    ),
    jsonld=JsonLdConfig(context='ctx.yaml'),
  )
  assert jsonld_uncovered_keys(schema, project_root=tmp_path) == ['date']
  # Without a project root the file can't be read: nothing is verified.
  assert jsonld_uncovered_keys(schema) == ['date', 'title']
