"""Tests for the configurable frontmatter schema."""

import datetime
import json

import pytest
from pydantic import ValidationError

from fastapi_blog.models import (
  DEFAULT_SCHEMA,
  LOOSE_DEFAULT_SCHEMA,
  FieldSpec,
  FrontmatterSchema,
  StrictFrontmatter,
  StrictPostPayload,
  frontmatter_model,
  payload_model,
)


# --- FieldSpec validation ---------------------------------------------------


@pytest.mark.parametrize(
  'name', ['', 'my-field', '1abc', '_private', 'model_x']
)
def test_field_spec_rejects_bad_names(name):
  with pytest.raises(ValueError, match='Invalid field name'):
    FieldSpec(name)


def test_field_spec_rejects_unknown_type():
  with pytest.raises(ValueError, match='Unknown type'):
    FieldSpec('x', type='uuid')


def test_field_spec_rejects_unknown_role():
  with pytest.raises(ValueError, match='Unknown role'):
    FieldSpec('x', role='author')


def test_field_spec_rejects_role_with_wrong_type():
  with pytest.raises(ValueError, match='needs type'):
    FieldSpec('flag', type='str', role='published')


def test_field_spec_rejects_required_with_default():
  with pytest.raises(ValueError, match='cannot have a default'):
    FieldSpec('x', required=True, default='a')


def test_field_spec_rejects_length_on_bool():
  with pytest.raises(ValueError, match='min_length'):
    FieldSpec('x', type='bool', max_length=3)


def test_field_spec_key_prefers_alias():
  assert FieldSpec('pub_date', alias='pubDate').key == 'pubDate'
  assert FieldSpec('title').key == 'title'


# --- FrontmatterSchema validation -------------------------------------------


def test_schema_rejects_unknown_extra_mode():
  with pytest.raises(ValueError, match='Unknown extra mode'):
    FrontmatterSchema(extra='maybe')


def test_schema_rejects_duplicate_names():
  with pytest.raises(ValueError, match='clashes'):
    FrontmatterSchema(fields=(FieldSpec('a'), FieldSpec('a')))


def test_schema_rejects_alias_clashing_with_other_name():
  with pytest.raises(ValueError, match='clashes'):
    FrontmatterSchema(fields=(FieldSpec('a'), FieldSpec('b', alias='a')))


def test_schema_rejects_role_bound_twice():
  with pytest.raises(ValueError, match='bound to both'):
    FrontmatterSchema(
      fields=(FieldSpec('a', role='title'), FieldSpec('b', role='title'))
    )


def test_schema_role_lookup():
  schema = FrontmatterSchema(
    fields=(FieldSpec('pub_date', alias='pubDate', role='date'),)
  )
  assert schema.name_for_role('date') == 'pub_date'
  assert schema.name_for_role('tags') is None
  assert schema.field_for_role('date').key == 'pubDate'
  assert schema.get('pub_date') is not None
  assert schema.get('missing') is None


# --- Loading from dict / file -----------------------------------------------


def test_from_dict_mapping_form():
  schema = FrontmatterSchema.from_dict(
    {
      'extra': 'allow',
      'fields': {
        'title': {'required': True, 'role': 'title'},
        'draft': {'type': 'bool', 'default': True},
        'author': None,
      },
    }
  )
  assert schema.extra == 'allow'
  assert [f.name for f in schema.fields] == ['title', 'draft', 'author']
  assert schema.get('draft').default is True


def test_from_dict_list_form():
  schema = FrontmatterSchema.from_dict(
    {'fields': [{'name': 'title', 'required': True}, {'name': 'tags'}]}
  )
  assert [f.name for f in schema.fields] == ['title', 'tags']


@pytest.mark.parametrize(
  'data',
  [
    {'unknown': 1},
    {'fields': {'x': {'typo': 1}}},
    {'fields': [{'required': True}]},
    {'fields': 'title'},
    {'fields': {'x': 'str'}},
  ],
)
def test_from_dict_rejects_malformed_input(data):
  with pytest.raises(ValueError):
    FrontmatterSchema.from_dict(data)


def test_from_file_yaml_and_json(tmp_path):
  description = {
    'extra': 'ignore',
    'fields': {'title': {'required': True}, 'n': {'type': 'int', 'default': 0}},
  }
  yaml_file = tmp_path / 'schema.yaml'
  yaml_file.write_text(
    'extra: ignore\nfields:\n  title: {required: true}\n  n: {type: int, default: 0}\n'
  )
  json_file = tmp_path / 'schema.json'
  json_file.write_text(json.dumps(description))

  for path in (yaml_file, json_file):
    schema = FrontmatterSchema.from_file(path)
    assert schema.extra == 'ignore'
    assert schema.get('n').default == 0


def test_to_dict_round_trip():
  schema = FrontmatterSchema.from_dict(DEFAULT_SCHEMA.to_dict())
  assert schema.to_dict() == DEFAULT_SCHEMA.to_dict()


# --- Generated Pydantic model -----------------------------------------------


def test_model_is_cached():
  assert DEFAULT_SCHEMA.model() is DEFAULT_SCHEMA.model()


def test_default_schema_matches_strict_frontmatter():
  """The default schema must behave exactly like the old hardcoded model."""
  valid = [
    {'title': 'T', 'date': '2024-01-01'},
    {'title': 'T', 'date': '2024-01-01', 'published': True, 'tags': ['a']},
    {'title': 'T', 'date': '2024-01-01', 'tags': None, 'description': 'd'},
  ]
  for data in valid:
    old = StrictFrontmatter(**data).model_dump()
    new = DEFAULT_SCHEMA.model()(**data).model_dump()
    assert new == old

  invalid = [
    {},
    {'title': '', 'date': '2024-01-01'},
    {'title': 'x' * 201, 'date': '2024-01-01'},
    {'title': 'T'},
    {'title': 'T', 'date': ''},
    {'title': 'T', 'date': '2024-01-01', 'unknown': 1},
    {'title': 'T', 'date': '2024-01-01', 'published': 'maybe'},
  ]
  for data in invalid:
    with pytest.raises(ValidationError):
      StrictFrontmatter(**data)
    with pytest.raises(ValidationError):
      DEFAULT_SCHEMA.model()(**data)


def test_loose_default_schema_keeps_unknown_keys():
  model = LOOSE_DEFAULT_SCHEMA.model()(title='T', date='d', custom=1)
  assert model.model_dump()['custom'] == 1


def test_extra_ignore_drops_unknown_keys():
  schema = FrontmatterSchema(fields=(FieldSpec('title'),), extra='ignore')
  assert schema.model()(title='T', other=1).model_dump() == {'title': 'T'}


def test_alias_accepted_by_key_and_by_name():
  schema = FrontmatterSchema(
    fields=(FieldSpec('pub_date', alias='pubDate', required=True),)
  )
  model = schema.model()
  by_alias = model(**{'pubDate': '2024-01-01'})
  by_name = model(pub_date='2024-01-01')
  assert by_alias.pub_date == by_name.pub_date == '2024-01-01'
  assert schema.dump(by_alias) == {'pub_date': '2024-01-01'}
  assert schema.dump(by_alias, by_alias=True) == {'pubDate': '2024-01-01'}


def test_custom_types_and_defaults():
  schema = FrontmatterSchema(
    fields=(
      FieldSpec('count', type='int', default=3),
      FieldSpec('draft', type='bool', default=True),
      FieldSpec('meta', type='dict'),
      FieldSpec('ratings', type='list[int]'),
      FieldSpec('note'),
    )
  )
  values = schema.model()().model_dump()
  assert values == {
    'count': 3,
    'draft': True,
    'meta': {},
    'ratings': [],
    'note': None,
  }


def test_null_container_becomes_empty():
  schema = FrontmatterSchema(fields=(FieldSpec('tags', type='list[str]'),))
  assert schema.model()(tags=None).tags == []


def test_mutable_defaults_are_not_shared():
  schema = FrontmatterSchema(fields=(FieldSpec('tags', type='list[str]'),))
  first = schema.model()()
  first.tags.append('x')
  assert schema.model()().tags == []


def test_length_constraints():
  schema = FrontmatterSchema(
    fields=(FieldSpec('code', required=True, min_length=2, max_length=3),)
  )
  model = schema.model()
  assert model(code='abc').code == 'abc'
  for bad in ('a', 'abcd'):
    with pytest.raises(ValidationError):
      model(code=bad)


def test_field_name_clashing_with_pydantic_attribute():
  schema = FrontmatterSchema(fields=(FieldSpec('json'),))
  with pytest.raises(ValueError, match='clashes with a Pydantic attribute'):
    schema.model()


# --- frontmatter_model integration ------------------------------------------


def test_frontmatter_model_without_schema_is_unchanged():
  assert frontmatter_model(True).__name__ == 'StrictFrontmatter'
  assert frontmatter_model(False).__name__ == 'LooseFrontmatter'
  assert frontmatter_model().__name__ == 'StrictFrontmatter'


def test_frontmatter_model_with_schema():
  schema = FrontmatterSchema(fields=(FieldSpec('title'),))
  assert frontmatter_model(schema=schema) is schema.model()


# --- Reserved names, role clashes, role map ---------------------------------


@pytest.mark.parametrize('name', ['slug', 'content'])
def test_field_spec_rejects_reserved_names(name):
  with pytest.raises(ValueError, match='reserved by the blog'):
    FieldSpec(name)


def test_reserved_name_can_be_used_as_alias():
  assert FieldSpec('post_slug', alias='slug').key == 'slug'


def test_schema_rejects_field_named_like_a_role_bound_elsewhere():
  with pytest.raises(ValueError, match='clashes with the role'):
    FrontmatterSchema(
      fields=(FieldSpec('pub_date', role='date'), FieldSpec('date'))
    )


def test_schema_allows_field_named_like_its_own_role():
  schema = FrontmatterSchema(fields=(FieldSpec('date', role='date'),))
  assert schema.role_map() == {'date': 'date'}


def test_role_map():
  assert DEFAULT_SCHEMA.role_map() == {
    'title': 'title',
    'date': 'date',
    'published': 'published',
    'tags': 'tags',
    'description': 'description',
  }
  assert FrontmatterSchema(fields=(FieldSpec('x'),)).role_map() == {}


# --- REST API payload model ---------------------------------------------------


def test_payload_model_is_cached():
  assert DEFAULT_SCHEMA.payload_model() is DEFAULT_SCHEMA.payload_model()


def test_payload_model_validates_frontmatter_and_content():
  schema = FrontmatterSchema(
    fields=(FieldSpec('pub_date', alias='pubDate', required=True),)
  )
  Payload = schema.payload_model()
  payload = Payload(frontmatter={'pubDate': '2024-01-01'}, content='Hi')
  assert payload.frontmatter.pub_date == '2024-01-01'
  assert payload.content == 'Hi'


@pytest.mark.parametrize(
  'data',
  [
    {'frontmatter': {}, 'content': 'Hi'},  # required field is missing
    {'frontmatter': {'pubDate': 'd'}, 'content': ''},  # empty content
    {'frontmatter': {'pubDate': 'd'}},  # no content
    {'frontmatter': {'pubDate': 'd', 'other': 1}, 'content': 'Hi'},  # extra key
    {'frontmatter': {'pubDate': 'd'}, 'content': 'Hi', 'slug': 'x'},  # extra
  ],
)
def test_payload_model_rejects_invalid_requests(data):
  schema = FrontmatterSchema(
    fields=(FieldSpec('pub_date', alias='pubDate', required=True),)
  )
  with pytest.raises(ValidationError):
    schema.payload_model()(**data)


def test_payload_model_function():
  assert payload_model(True) is StrictPostPayload
  assert payload_model() is StrictPostPayload
  assert payload_model(False).__name__ == 'LoosePostPayload'
  schema = FrontmatterSchema(fields=(FieldSpec('title'),))
  assert payload_model(True, schema) is schema.payload_model()


# --- on_create / read_only (TODO 4.5) ---------------------------------------


def test_field_spec_rejects_unknown_on_create():
  with pytest.raises(ValueError, match='Unknown on_create'):
    FieldSpec('x', type='str', on_create='never')


@pytest.mark.parametrize(
  ('on_create', 'wrong_type'),
  [('today', 'str'), ('now', 'date'), ('uuid', 'int')],
)
def test_field_spec_rejects_on_create_with_wrong_type(on_create, wrong_type):
  with pytest.raises(ValueError, match='needs type'):
    FieldSpec('x', type=wrong_type, on_create=on_create)


def test_field_spec_rejects_required_with_on_create():
  with pytest.raises(ValueError, match='required.*on_create'):
    FieldSpec('x', type='date', required=True, on_create='today')


def test_field_spec_rejects_on_create_prefix_without_uuid():
  with pytest.raises(ValueError, match='on_create_prefix'):
    FieldSpec('x', type='date', on_create='today', on_create_prefix='n-')


def test_on_create_today_fills_unset_date_field():
  schema = FrontmatterSchema(
    fields=(
      FieldSpec('title', required=True),
      FieldSpec('published_at', type='date', on_create='today'),
    )
  )
  instance = schema.model()(title='Hi')
  result = schema.dump_for_write(instance, is_create=True)
  assert result['published_at'] == datetime.date.today()


def test_on_create_does_not_override_a_provided_value():
  schema = FrontmatterSchema(
    fields=(FieldSpec('published_at', type='date', on_create='today'),)
  )
  given = datetime.date(2020, 1, 1)
  instance = schema.model()(published_at=given)
  result = schema.dump_for_write(instance, is_create=True)
  assert result['published_at'] == given


def test_on_create_uuid_is_stable_across_rewrites():
  """A `read_only` + `on_create='uuid'` field keeps its value on update."""
  schema = FrontmatterSchema(
    fields=(
      FieldSpec(
        'doc_id', alias='@id', type='str', on_create='uuid', read_only=True
      ),
    )
  )
  created = schema.dump_for_write(schema.model()(), is_create=True)
  assert created['@id']

  # Re-submitting the same value (as a full-replace payload naturally would)
  # is accepted.
  updated = schema.dump_for_write(
    schema.model()(**{'@id': created['@id']}),
    is_create=False,
    existing=created,
  )
  assert updated['@id'] == created['@id']


def test_on_create_uuid_with_prefix():
  schema = FrontmatterSchema(
    fields=(
      FieldSpec(
        'doc_id',
        alias='@id',
        type='str',
        on_create='uuid',
        on_create_prefix='note-',
      ),
    )
  )
  result = schema.dump_for_write(schema.model()(), is_create=True)
  assert result['@id'].startswith('note-')


def test_read_only_rejects_a_changed_value_on_update():
  schema = FrontmatterSchema(
    fields=(FieldSpec('doc_id', alias='@id', type='str', read_only=True),)
  )
  existing = {'@id': 'note-0001'}
  instance = schema.model()(**{'@id': 'note-9999'})
  with pytest.raises(ValueError, match='read-only'):
    schema.dump_for_write(instance, is_create=False, existing=existing)


def test_read_only_allows_an_update_that_leaves_it_untouched():
  schema = FrontmatterSchema(
    fields=(
      FieldSpec('title', required=True),
      FieldSpec('doc_id', alias='@id', type='str', read_only=True),
    )
  )
  existing = {'title': 'Old', '@id': 'note-0001'}
  instance = schema.model()(title='New')
  result = schema.dump_for_write(instance, is_create=False, existing=existing)
  assert result['title'] == 'New'
  assert '@id' not in result  # left unset, so dropped like any other field


def test_read_only_is_not_checked_on_create():
  schema = FrontmatterSchema(
    fields=(FieldSpec('doc_id', alias='@id', type='str', read_only=True),)
  )
  instance = schema.model()(**{'@id': 'anything'})
  result = schema.dump_for_write(instance, is_create=True)
  assert result['@id'] == 'anything'
