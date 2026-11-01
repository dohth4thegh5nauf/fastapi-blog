"""Tests for the admin post form built from a frontmatter schema."""

import datetime
import json

import pytest

from fastapi_blog import DEFAULT_SCHEMA, FieldSpec, FrontmatterSchema
from fastapi_blog.admin.form_fields import (
  build_form_fields,
  field_kind,
  form_fields_meta,
  format_value,
  get_field_value,
)


LABELS = {
  'title': 'Title',
  'date': 'Date',
  'published': 'Published',
  'tags': 'Tags',
  'description': 'Description',
  'tags_hint': 'Comma-separated tags',
}

EXTERNAL_SCHEMA = FrontmatterSchema(
  fields=(
    FieldSpec('headline', alias='title', required=True, role='title'),
    FieldSpec('pub_date', alias='pubDate', required=True, role='date'),
    FieldSpec('is_public', alias='isPublic', type='bool', default=True),
    FieldSpec('labels', type='list[str]', role='tags'),
    FieldSpec('author', description='Written by'),
    FieldSpec('meta', type='dict'),
    FieldSpec('rating', type='int'),
  ),
)


@pytest.mark.parametrize(
  ('spec', 'kind'),
  [
    (FieldSpec('a', type='bool'), 'bool'),
    (FieldSpec('a', type='date'), 'date'),
    (FieldSpec('a', role='date'), 'date'),
    (FieldSpec('a', type='datetime'), 'datetime'),
    (FieldSpec('a', type='int'), 'number'),
    (FieldSpec('a', type='float'), 'number'),
    (FieldSpec('a', type='list[str]'), 'list'),
    (FieldSpec('a', type='list[int]'), 'int_list'),
    (FieldSpec('a', type='dict'), 'json'),
    (FieldSpec('a', type='any'), 'json'),
    (FieldSpec('a', role='description'), 'textarea'),
    (FieldSpec('a', max_length=500), 'textarea'),
    (FieldSpec('a', max_length=200), 'text'),
    (FieldSpec('a'), 'text'),
  ],
)
def test_field_kind(spec, kind):
  assert field_kind(spec) == kind


def test_format_value():
  assert format_value('text', None) == ''
  assert format_value('bool', True) == 'true'
  assert format_value('bool', False) == 'false'
  assert format_value('date', datetime.date(2024, 1, 5)) == '2024-01-05'
  assert (
    format_value('date', datetime.datetime(2024, 1, 5, 10, 0)) == '2024-01-05'
  )
  assert format_value('date', '2024-01-05T10:00:00') == '2024-01-05'
  assert format_value('date', 'not a date') == 'not a date'
  dt = datetime.datetime(2024, 1, 5, 10, 30, 45)
  assert format_value('datetime', dt) == '2024-01-05T10:30'
  assert format_value('datetime', '2024-01-05 10:30:00') == '2024-01-05T10:30'
  assert format_value('list', ['a', 'b']) == 'a, b'
  assert format_value('int_list', [1, 2]) == '1, 2'
  assert format_value('number', 3) == '3'


def test_format_value_json_keeps_unicode_and_dates():
  text = format_value(
    'json', {'name': 'Привет', 'd': datetime.date(2024, 1, 1)}
  )
  assert 'Привет' in text
  assert json.loads(text) == {'name': 'Привет', 'd': '2024-01-01'}


def test_get_field_value():
  frontmatter = {'pubDate': '2024-01-01', 'title': None, 'n': 1}
  pub_date = FieldSpec('pub_date', alias='pubDate')
  assert get_field_value(frontmatter, pub_date) == '2024-01-01'
  assert get_field_value({'pub_date': 'x'}, pub_date) == 'x'  # internal name
  assert get_field_value(frontmatter, FieldSpec('n')) == 1
  assert get_field_value(frontmatter, FieldSpec('title'), 'dflt') == 'dflt'
  assert get_field_value(frontmatter, None, 'dflt') == 'dflt'


def test_default_schema_form_for_an_existing_post():
  frontmatter = {
    'title': 'Hi',
    'date': '2024-01-01',
    'published': True,
    'tags': ['a', 'b'],
    'description': 'd',
  }
  fields = build_form_fields(DEFAULT_SCHEMA, frontmatter, LABELS)
  assert [f['name'] for f in fields] == [
    'title',
    'date',
    'published',
    'tags',
    'description',
  ]
  # Same layout as the old hardcoded form
  assert [f['col'] for f in fields] == [
    'col-12',
    'col-md-6',
    'col-md-6',
    'col-12',
    'col-12',
  ]
  assert [f['value'] for f in fields] == [
    'Hi',
    '2024-01-01',
    'true',
    'a, b',
    'd',
  ]
  assert [f['label'] for f in fields] == list(LABELS.values())[:5]
  assert [f['html_required'] for f in fields] == [
    True,
    True,
    False,
    False,
    False,
  ]
  assert fields[3]['hint'] == LABELS['tags_hint']
  assert fields[0]['hint'] == ''
  assert fields[4]['kind'] == 'textarea'


def test_default_schema_form_for_a_new_post():
  fields = build_form_fields(DEFAULT_SCHEMA, {}, LABELS, is_new=True)
  values = {f['name']: f['value'] for f in fields}
  assert values == {
    'title': '',
    'date': datetime.date.today().isoformat(),
    'published': 'false',
    'tags': '',
    'description': '',
  }


def test_external_schema_form_for_an_existing_post():
  frontmatter = {
    'title': 'T',
    'pubDate': '2024-02-02',
    'labels': ['x'],
    'meta': {'k': 1},
  }
  fields = {
    f['name']: f
    for f in build_form_fields(EXTERNAL_SCHEMA, frontmatter, LABELS)
  }
  assert fields['headline']['value'] == 'T'
  assert fields['headline']['key'] == 'title'  # the key written to the file
  assert fields['headline']['label'] == LABELS['title']
  assert fields['pub_date']['value'] == '2024-02-02'
  assert fields['is_public']['value'] == 'true'  # absent: the field default
  assert fields['author']['label'] == 'Written by'  # no role: the description
  assert fields['rating']['label'] == 'rating'  # no description: the name
  assert fields['rating']['col'] == 'col-md-6'
  assert json.loads(fields['meta']['value']) == {'k': 1}


def test_external_schema_form_for_a_new_post():
  fields = {
    f['name']: f
    for f in build_form_fields(EXTERNAL_SCHEMA, {}, LABELS, is_new=True)
  }
  assert fields['is_public']['value'] == 'true'
  assert fields['pub_date']['value'] == datetime.date.today().isoformat()


def test_form_fields_meta():
  fields = build_form_fields(EXTERNAL_SCHEMA, {}, LABELS)
  meta = form_fields_meta(fields)
  assert (meta[0]['name'], meta[0]['key'], meta[0]['kind']) == (
    'headline',
    'title',
    'text',
  )
  assert (meta[1]['name'], meta[1]['key'], meta[1]['kind']) == (
    'pub_date',
    'pubDate',
    'date',
  )
