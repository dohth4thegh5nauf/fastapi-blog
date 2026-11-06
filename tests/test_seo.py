"""Tests for `seo_fields()` and `build_head()`."""

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
  """The `author` role allows `str` or `list[str]`."""
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


def test_build_head_resolves_fallback_order_and_jsonld():
  import json

  from fastapi_blog.models import SeoConfig
  from fastapi_blog.seo import build_head

  head = build_head(
    {
      'seo_title': 'SEO title',
      'title': 'Ordinary title',
      'date': '2026-01-02',
      'updated': '2026-01-03',
      'robots': ['noindex'],
      'tags': ['python'],
      'image': '/cover.png',
    },
    config=SeoConfig(
      site_url='https://example.test',
      site_name='Example',
      title_template='{title} - {site_name}',
      default_image='/fallback.png',
      default_author='Editor',
      default_robots=('nofollow',),
      og=True,
      twitter_card='summary_large_image',
      structured_data='blogposting',
    ),
    request_url='https://example.test/blog/post?utm=1',
    locale='ru',
  )
  assert head['title'] == 'SEO title - Example'
  assert head['canonical_url'] == 'https://example.test/blog/post'
  assert head['og_image'] == 'https://example.test/cover.png'
  assert head['robots'] == ['noindex', 'nofollow']
  assert head['author'] == 'Editor'
  assert json.loads(head['structured_data_json'])['keywords'] == ['python']


def test_build_head_excerpt_is_plain_text_and_word_bounded():
  from fastapi_blog.models import SeoConfig
  from fastapi_blog.seo import build_head

  head = build_head(
    {},
    config=SeoConfig(description_fallback='excerpt', description_length=12),
    body='<p>Hello <strong>world</strong>, this is a <em>test</em>.</p>',
  )
  assert head['description'] == 'Hello world'


def test_build_head_jsonld_escapes_html_and_round_trips():
  import json

  from fastapi_blog.models import SeoConfig
  from fastapi_blog.seo import build_head

  title = 'A & <b>B</b> </script><script>alert(1)</script>'
  head = build_head(
    {'title': title, 'tags': ['a&b']},
    config=SeoConfig(structured_data='blogposting'),
    request_url='https://example.test/blog/posts/x',
  )
  raw = head['structured_data_json']
  assert '<' not in raw
  assert '>' not in raw
  assert '&' not in raw
  # One backslash: a JSON parser gets the original characters back
  data = json.loads(raw)
  assert data['headline'] == title
  assert data['keywords'] == ['a&b']


def test_build_head_noindex_tags_only_touches_tag_pages():
  from fastapi_blog.models import SeoConfig
  from fastapi_blog.seo import build_head

  config = SeoConfig(noindex_tags=True, default_robots=('nofollow',))
  assert build_head({}, config=config, page_type='tag')['robots'] == [
    'nofollow',
    'noindex',
  ]
  assert 'noindex' in build_head({}, config=config, page_type='tags')['robots']
  assert build_head({}, config=config, page_type='list')['robots'] == [
    'nofollow'
  ]
  doc = {'robots': ['noindex']}
  assert build_head(doc, config=config, page_type='tag')['robots'] == [
    'noindex',
    'nofollow',
  ]
  off = SeoConfig()
  assert build_head({}, config=off, page_type='tag')['robots'] == []


def test_build_head_index_description_is_for_indexes_not_static_pages():
  from fastapi_blog.models import SeoConfig
  from fastapi_blog.seo import build_head

  config = SeoConfig(index_description='About the site')
  for page_type in ('index', 'list', 'tags', 'tag'):
    head = build_head({}, config=config, page_type=page_type)
    assert head['description'] == 'About the site'
  for page_type in ('page', 'article'):
    assert (
      build_head({}, config=config, page_type=page_type)['description'] is None
    )
