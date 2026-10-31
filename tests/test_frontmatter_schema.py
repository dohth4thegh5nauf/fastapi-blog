"""Tests for the configurable frontmatter schema."""

import datetime
import json
import re

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
    FieldSpec('x', role='nonexistent')


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


# --- `status` role / `published_values` (TODO 5.7) --------------------------


def test_status_role_needs_published_values():
  with pytest.raises(ValueError, match='published_values'):
    FrontmatterSchema(fields=(FieldSpec('status', role='status'),))


def test_published_values_needs_a_status_role():
  with pytest.raises(ValueError, match='status'):
    FrontmatterSchema(
      fields=(FieldSpec('title'),), published_values=('active',)
    )


def test_status_and_published_roles_are_mutually_exclusive():
  with pytest.raises(
    ValueError, match="'published'.*'status'|'status'.*'published'"
  ):
    FrontmatterSchema(
      fields=(
        FieldSpec('published', type='bool', role='published'),
        FieldSpec('status', role='status'),
      ),
      published_values=('active',),
    )


def test_status_role_rejects_wrong_type():
  with pytest.raises(ValueError, match="role 'status'"):
    FieldSpec('status', type='bool', role='status')


def test_status_role_configures_cleanly():
  schema = FrontmatterSchema(
    fields=(
      FieldSpec('title', required=True, role='title'),
      FieldSpec(
        'status',
        required=True,
        choices=('draft', 'active', 'retired'),
        role='status',
      ),
    ),
    published_values=('active',),
  )
  assert schema.role_map()['status'] == 'status'
  assert schema.published_values == ('active',)


def test_published_values_round_trips_through_to_dict():
  schema = FrontmatterSchema(
    fields=(FieldSpec('status', required=True, role='status'),),
    published_values=['active', 'featured'],
  )
  data = schema.to_dict()
  assert data['published_values'] == ['active', 'featured']
  rebuilt = FrontmatterSchema.from_dict(data)
  assert rebuilt.published_values == ('active', 'featured')


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


# --- choices / pattern / min / max / min_items / max_items (TODO 5.1) ------


def test_field_spec_rejects_empty_choices():
  with pytest.raises(ValueError, match='choices.*empty'):
    FieldSpec('status', choices=())


def test_field_spec_rejects_choices_on_unsupported_type():
  with pytest.raises(ValueError, match='choices'):
    FieldSpec('x', type='bool', choices=('a', 'b'))


def test_field_spec_rejects_choices_mapping_without_value():
  with pytest.raises(ValueError, match="no 'value' key"):
    FieldSpec('status', choices=({'label': 'Draft'},))


def test_choices_accepts_an_allowed_scalar_value():
  schema = FrontmatterSchema(
    fields=(FieldSpec('status', choices=('draft', 'active', 'retired')),)
  )
  instance = schema.model()(status='active')
  assert instance.status == 'active'


def test_choices_rejects_a_disallowed_value():
  schema = FrontmatterSchema(
    fields=(FieldSpec('status', choices=('draft', 'active')),)
  )
  with pytest.raises(ValidationError, match='invalid choice'):
    schema.model()(status='bogus')


def test_choices_with_value_label_mapping_validates_against_value():
  schema = FrontmatterSchema(
    fields=(
      FieldSpec(
        'status',
        choices=({'value': 'draft', 'label': 'Draft'}, {'value': 'active'}),
      ),
    )
  )
  instance = schema.model()(status='draft')
  assert instance.status == 'draft'
  with pytest.raises(ValidationError):
    schema.model()(status='Draft')  # the label itself is not a valid value


def test_choices_on_a_list_checks_every_element():
  schema = FrontmatterSchema(
    fields=(FieldSpec('tags', type='list[str]', choices=('a', 'b', 'c')),)
  )
  instance = schema.model()(tags=['a', 'c'])
  assert instance.tags == ['a', 'c']
  with pytest.raises(ValidationError, match='invalid choice'):
    schema.model()(tags=['a', 'nope'])


def test_field_spec_rejects_pattern_on_non_str_type():
  with pytest.raises(ValueError, match='pattern'):
    FieldSpec('x', type='int', pattern=r'\d+')


def test_field_spec_rejects_item_pattern_except_on_list_str():
  with pytest.raises(ValueError, match='item_pattern'):
    FieldSpec('x', type='str', item_pattern=r'\d+')


def test_field_spec_rejects_an_invalid_regex():
  with pytest.raises(re.error):
    FieldSpec('x', pattern='(unterminated')


def test_pattern_accepts_a_matching_value():
  schema = FrontmatterSchema(fields=(FieldSpec('code', pattern=r'[A-Z]{3}'),))
  instance = schema.model()(code='ABC')
  assert instance.code == 'ABC'


def test_pattern_rejects_a_non_matching_value_with_default_message():
  schema = FrontmatterSchema(fields=(FieldSpec('code', pattern=r'[A-Z]{3}'),))
  with pytest.raises(ValidationError, match='does not match'):
    schema.model()(code='abc')


def test_pattern_with_custom_message_surfaces_it():
  schema = FrontmatterSchema(
    fields=(
      FieldSpec('code', pattern=(r'[A-Z]{3}', 'Expected ABC-style code')),
    )
  )
  with pytest.raises(ValidationError, match='Expected ABC-style code'):
    schema.model()(code='abc')


def test_pattern_from_a_yaml_list_pair_works():
  schema = FrontmatterSchema.from_dict(
    {'fields': {'code': {'pattern': ['[A-Z]{3}', 'Bad code']}}}
  )
  with pytest.raises(ValidationError, match='Bad code'):
    schema.model()(code='abc')


def test_item_pattern_checks_every_list_element():
  schema = FrontmatterSchema(
    fields=(FieldSpec('tags', type='list[str]', item_pattern=r'[a-z]+'),)
  )
  instance = schema.model()(tags=['abc', 'def'])
  assert instance.tags == ['abc', 'def']
  with pytest.raises(ValidationError):
    schema.model()(tags=['abc', 'DEF'])


def test_field_spec_rejects_min_max_on_unsupported_type():
  with pytest.raises(ValueError, match='min.*max'):
    FieldSpec('x', type='str', min=1)


def test_min_max_enforced_on_int_field():
  schema = FrontmatterSchema(
    fields=(FieldSpec('rating', type='int', min=1, max=5),)
  )
  assert schema.model()(rating=3).rating == 3
  with pytest.raises(ValidationError):
    schema.model()(rating=0)
  with pytest.raises(ValidationError):
    schema.model()(rating=6)


def test_field_spec_rejects_min_items_on_unsupported_type():
  with pytest.raises(ValueError, match='min_items'):
    FieldSpec('x', type='str', min_items=1)


def test_field_spec_rejects_min_items_combined_with_min_length():
  with pytest.raises(ValueError, match='min_items.*min_length'):
    FieldSpec('tags', type='list[str]', min_items=1, min_length=1)


def test_min_items_max_items_enforced_independently():
  schema = FrontmatterSchema(
    fields=(FieldSpec('tags', type='list[str]', min_items=1),)
  )
  assert schema.model()(tags=['a']).tags == ['a']
  with pytest.raises(ValidationError):
    schema.model()(tags=[])


def test_label_hint_hidden_round_trip_through_to_dict():
  spec = FieldSpec(
    'status', label='Status', hint='Lifecycle state', hidden=True
  )
  data = spec.to_dict()
  assert data['label'] == 'Status'
  assert data['hint'] == 'Lifecycle state'
  assert data['hidden'] is True

  schema = FrontmatterSchema(fields=(spec,))
  field_info = schema.model().model_fields['status']
  assert field_info.title == 'Status'
  assert field_info.json_schema_extra == {
    'hint': 'Lifecycle state',
    'hidden': True,
  }


# --- Merge on rewrite (TODO 4.5) ---------------------------------------------


def _loose_title_schema(extra='allow'):
  return FrontmatterSchema(
    fields=(FieldSpec('title', required=True),), extra=extra
  )


def test_update_preserves_unknown_keys_and_file_order():
  schema = _loose_title_schema()
  existing = {'zeta': 1, 'title': 'Old', 'alpha': 2}
  instance = schema.model()(title='New')
  result = schema.dump_for_write(instance, is_create=False, existing=existing)
  assert result == {'zeta': 1, 'title': 'New', 'alpha': 2}
  assert list(result) == ['zeta', 'title', 'alpha']


def test_update_with_extra_ignore_drops_unknown_keys():
  schema = _loose_title_schema(extra='ignore')
  existing = {'title': 'Old', 'legacy': True}
  instance = schema.model()(title='New')
  result = schema.dump_for_write(instance, is_create=False, existing=existing)
  assert result == {'title': 'New'}


def test_update_drops_a_known_field_emptied_to_none():
  schema = FrontmatterSchema(
    fields=(
      FieldSpec('title', required=True),
      FieldSpec('subtitle'),
    ),
    extra='allow',
  )
  existing = {'title': 'Old', 'subtitle': 'S', 'other': 1}
  instance = schema.model()(title='New')
  result = schema.dump_for_write(instance, is_create=False, existing=existing)
  assert result == {'title': 'New', 'other': 1}


def test_update_appends_schema_fields_the_file_did_not_have():
  schema = FrontmatterSchema(
    fields=(
      FieldSpec('title', required=True),
      FieldSpec('tags', type='list[str]'),
    ),
    extra='allow',
  )
  existing = {'title': 'Old', 'other': 1}
  instance = schema.model()(title='New', tags=['a'])
  result = schema.dump_for_write(instance, is_create=False, existing=existing)
  assert result == {'title': 'New', 'other': 1, 'tags': ['a']}


def test_create_does_not_merge():
  schema = _loose_title_schema()
  instance = schema.model()(title='New')
  result = schema.dump_for_write(
    instance, is_create=True, existing={'legacy': 1}
  )
  assert result == {'title': 'New'}


# --- link / file / image field types (TODO 5.1) -------------------------------


def test_link_type_validates_as_a_string():
  schema = FrontmatterSchema(fields=(FieldSpec('related', type='link'),))
  instance = schema.model()(related='some-post')
  assert schema.dump(instance) == {'related': 'some-post'}


def test_link_options_require_a_link_field():
  with pytest.raises(ValueError, match='needs a `link`'):
    FieldSpec('title', collection='posts')
  with pytest.raises(ValueError, match='needs a `link`'):
    FieldSpec('tags', type='list[str]', filters=[{'field': 'x', 'values': [1]}])


def test_link_filters_are_cleaned_to_tuples():
  spec = FieldSpec(
    'related',
    type='link',
    collection='posts',
    value_field='title',
    filters=[{'field': 'kind', 'values': ['a', 'b']}],
  )
  assert spec.filters == ({'field': 'kind', 'values': ['a', 'b']},)


def test_link_filters_must_have_field_and_values():
  with pytest.raises(ValueError, match='must be a list'):
    FieldSpec('related', type='link', filters='nope')
  with pytest.raises(ValueError, match='Each filter'):
    FieldSpec('related', type='link', filters=[{'field': 'kind'}])


def test_file_and_image_types_validate_their_options():
  spec = FieldSpec('cover', type='image', media_dir='media', public_path='m/')
  assert spec.media_dir == 'media'
  with pytest.raises(ValueError, match='needs a `file` or `image`'):
    FieldSpec('title', media_dir='media')
  with pytest.raises(ValueError, match='needs `media_dir`'):
    FieldSpec('cover', type='image', public_path='m/')
  with pytest.raises(ValueError, match='relative path'):
    FieldSpec('cover', type='image', media_dir='/etc')
  with pytest.raises(ValueError, match='relative path'):
    FieldSpec('cover', type='file', media_dir='a/../b')


def test_pattern_applies_to_link_file_image():
  for type_name in ('link', 'file', 'image'):
    spec = FieldSpec('x', type=type_name, pattern=r'[a-z]+')
    assert spec.pattern == r'[a-z]+'


def test_item_pattern_applies_to_list_link():
  spec = FieldSpec('tags', type='list[link]', item_pattern=r'[a-z]+')
  assert spec.item_pattern == r'[a-z]+'
  with pytest.raises(ValueError, match='item_pattern'):
    FieldSpec('tags', type='list[str]', pattern=r'[a-z]+')


def test_schema_round_trip_with_link_and_file_fields():
  schema = FrontmatterSchema(
    fields=(
      FieldSpec(
        'related',
        type='link',
        collection='posts',
        filters=[{'field': 'kind', 'values': ['a']}],
      ),
      FieldSpec('cover', type='image', media_dir='media/img'),
    ),
  )
  restored = FrontmatterSchema.from_dict(schema.to_dict())
  assert restored.to_dict() == schema.to_dict()
  assert restored.fields[0].filters == ({'field': 'kind', 'values': ['a']},)


# --- Nested object fields (TODO 5.1.2) ---------------------------------------


def test_nested_object_and_list_object_validate_and_dump_aliases():
  schema = FrontmatterSchema.from_dict({
    'fields': {
      'metadata': {
        'type': 'object',
        'fields': {
          'identifier': {'alias': '@id', 'type': 'str'},
          'rating': {'type': 'int'},
        },
      },
      'offers': {
        'type': 'list[object]',
        'min_items': 1,
        'fields': {
          'name': {'type': 'str', 'required': True},
          'price': {'type': 'float'},
        },
      },
    },
  })
  instance = schema.model().model_validate({
    'metadata': {'@id': 'note:1', 'rating': 5},
    'offers': [{'name': 'Standard', 'price': 12.5}],
  })
  assert schema.dump(instance, by_alias=True) == {
    'metadata': {'@id': 'note:1', 'rating': 5},
    'offers': [{'name': 'Standard', 'price': 12.5}],
  }
  assert schema.to_dict()['fields']['metadata']['fields']['identifier']['alias'] == '@id'


def test_nested_object_rejects_depth_greater_than_three():
  with pytest.raises(ValueError, match='maximum depth of 3'):
    FieldSpec(
      'one', type='object', fields=(
        FieldSpec('two', type='object', fields=(
          FieldSpec('three', type='object', fields=(
            FieldSpec('four'),
          )),
        )),
      ),
    )


def test_nested_object_rejects_semantic_roles_and_alias_collisions():
  with pytest.raises(ValueError, match='cannot bind a semantic role'):
    FieldSpec('meta', type='object', fields=(FieldSpec('title', role='title'),))
  with pytest.raises(ValueError, match='clashes'):
    FieldSpec('meta', type='object', fields=(
      FieldSpec('one', alias='same'), FieldSpec('two', alias='same'),
    ))


def test_nested_read_only_values_are_preserved_or_rejected():
  schema = FrontmatterSchema(fields=(
    FieldSpec('meta', type='object', fields=(
      FieldSpec('identifier', read_only=True),
      FieldSpec('label'),
    )),
  ))
  model = schema.model()
  original = {'meta': {'identifier': 'fixed', 'label': 'Before'}}
  unchanged = model.model_validate({'meta': {'label': 'After'}})
  dumped = schema.dump_for_write(unchanged, is_create=False, existing=original)
  assert dumped['meta']['identifier'] == 'fixed'
  changed = model.model_validate({'meta': {'identifier': 'other', 'label': 'After'}})
  with pytest.raises(ValueError, match='read-only'):
    schema.dump_for_write(changed, is_create=False, existing=original)

  list_schema = FrontmatterSchema(fields=(
    FieldSpec('items', type='list[object]', fields=(
      FieldSpec('identifier', read_only=True),
      FieldSpec('label'),
    )),
  ))
  list_model = list_schema.model()
  list_existing = {'items': [
    {'identifier': 'fixed-1', 'label': 'First'},
    {'identifier': 'fixed-2', 'label': 'Second'},
  ]}
  omitted = list_model.model_validate({})
  assert list_schema.dump_for_write(
    omitted, is_create=False, existing=list_existing
  )['items'] == list_existing['items']
  partial = list_model.model_validate({'items': [{'label': 'Changed'}]})
  assert list_schema.dump_for_write(
    partial, is_create=False, existing=list_existing
  )['items'] == [{'identifier': 'fixed-1', 'label': 'Changed'}]
