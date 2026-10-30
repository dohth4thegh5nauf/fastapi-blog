"""Tests for JSON-LD emission (TODO phase C, 5.2-5.4)."""

import pytest

from fastapi_blog.jsonld import collection_to_jsonld, document_to_jsonld
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
