"""Tests for `fastapi_blog.seo.seo_fields()` (TODO 5.9.1)."""

import pytest

from fastapi_blog.models import FieldSpec, FrontmatterSchema
from fastapi_blog.seo import ROBOTS_DIRECTIVES, seo_fields


SEO_ROLES = (
  'seo_title',
  'canonical',
  'robots',
  'image',
  'image_alt',
  'updated',
  'author',
  'lang',
  'redirect_from',
)


def test_seo_fields_returns_one_field_per_role():
  fields = seo_fields()
  assert len(fields) == len(SEO_ROLES)
  assert {spec.role for spec in fields} == set(SEO_ROLES)


def test_seo_fields_field_names_match_role_names():
  for spec in seo_fields():
    assert spec.name == spec.role


def test_seo_fields_none_are_required():
  assert all(not spec.required for spec in seo_fields())


def test_seo_fields_every_field_has_a_label_and_hint():
  for spec in seo_fields():
    assert spec.label
    assert spec.hint


def test_seo_fields_robots_has_choices():
  robots = next(spec for spec in seo_fields() if spec.role == 'robots')
  assert robots.type == 'list[str]'
  assert robots.choices == ROBOTS_DIRECTIVES


def test_seo_fields_subset_selects_only_those_roles():
  fields = seo_fields(('canonical', 'robots'))
  assert {spec.role for spec in fields} == {'canonical', 'robots'}


def test_seo_fields_rejects_an_unknown_role():
  with pytest.raises(ValueError, match='Unknown SEO role'):
    seo_fields(('not_a_role',))


def test_seo_fields_plug_into_a_real_schema():
  schema = FrontmatterSchema(
    fields=(FieldSpec('title', required=True, role='title'), *seo_fields())
  )
  instance = schema.model()(
    title='Hi',
    canonical='/custom',
    robots=['noindex', 'nofollow'],
    author='Ann',
  )
  assert instance.canonical == '/custom'
  assert instance.robots == ['noindex', 'nofollow']
  assert instance.author == 'Ann'


def test_seo_fields_robots_rejects_an_unknown_directive():
  schema = FrontmatterSchema(fields=seo_fields(('robots',)))
  from pydantic import ValidationError

  with pytest.raises(ValidationError):
    schema.model()(robots=['bogus'])


def test_seo_fields_author_accepts_a_list_too():
  """The `author` role allows `str` or `list[str]` (TODO 5.9.1's table)."""
  schema = FrontmatterSchema(
    fields=(FieldSpec('authors', type='list[str]', role='author'),)
  )
  instance = schema.model()(authors=['Ann', 'Bob'])
  assert instance.authors == ['Ann', 'Bob']


def test_seo_fields_schema_author_can_rename_fields():
  renamed = FieldSpec('social_image', alias='image', type='str', role='image')
  schema = FrontmatterSchema(fields=(renamed,))
  instance = schema.model()(image='/pic.png')
  assert instance.social_image == '/pic.png'
