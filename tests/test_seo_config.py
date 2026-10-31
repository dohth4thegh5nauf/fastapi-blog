"""Tests for `SeoConfig` and the `seo:` schema section (TODO 5.9.2)."""

import jinja2
import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fastapi_blog
from fastapi_blog.models import (
  DEFAULT_SCHEMA,
  FieldSpec,
  FrontmatterSchema,
  SeoConfig,
)
from fastapi_blog.seo import resolve_seo_config


FULL_SECTION = yaml.safe_load(
  """
  site_url: "https://example.org"
  site_name: "Example Notes"
  title_template: "{title} - {site_name}"
  default_image: "/static/social.png"
  default_author: "Ann"
  default_robots: [noarchive]
  index_description: "Short site description"
  og: true
  twitter_card: summary_large_image
  structured_data: blogposting
  description_fallback: excerpt
  description_length: 120
  noindex_tags: true
  """
)


# --- Defaults and the section's shape ---------------------------------------


def test_defaults_switch_everything_off():
  config = SeoConfig()
  assert config.site_url is None
  assert config.default_robots == ()
  assert config.og is False
  assert config.twitter_card is None
  assert config.structured_data == 'none'
  assert config.description_fallback == 'none'
  assert config.description_length == 160
  assert config.noindex_tags is False


def test_full_section_from_the_todo_example_loads():
  config = SeoConfig.from_dict(FULL_SECTION)
  assert config.site_url == 'https://example.org'
  assert config.site_name == 'Example Notes'
  assert config.default_robots == ('noarchive',)
  assert config.twitter_card == 'summary_large_image'
  assert config.structured_data == 'blogposting'
  assert config.description_length == 120
  assert config.noindex_tags is True


def test_empty_section_is_a_config_with_all_defaults():
  assert SeoConfig.from_dict({}) == SeoConfig()


def test_to_dict_round_trips_and_omits_defaults():
  config = SeoConfig.from_dict(FULL_SECTION)
  assert SeoConfig.from_dict(config.to_dict()) == config
  assert SeoConfig().to_dict() == {}


def test_default_robots_null_means_none():
  assert SeoConfig.from_dict({'default_robots': None}).default_robots == ()


# --- Errors name the offending key ------------------------------------------


@pytest.mark.parametrize(
  ('section', 'key'),
  [
    ({'site_url': 'example.org'}, 'seo.site_url'),
    ({'site_url': 'ftp://example.org'}, 'seo.site_url'),
    ({'site_url': 'https://'}, 'seo.site_url'),
    ({'site_url': 'https://example.org/?q=1'}, 'seo.site_url'),
    ({'site_url': 'https://example.org/#top'}, 'seo.site_url'),
    ({'site_name': ''}, 'seo.site_name'),
    ({'site_name': 5}, 'seo.site_name'),
    ({'default_author': ''}, 'seo.default_author'),
    ({'index_description': ''}, 'seo.index_description'),
    ({'default_image': 'social.png'}, 'seo.default_image'),
    ({'default_image': '//cdn.example.org/a.png'}, 'seo.default_image'),
    ({'default_image': 'javascript:alert(1)'}, 'seo.default_image'),
    ({'default_image': 'data:image/png;base64,AAAA'}, 'seo.default_image'),
    ({'default_robots': 'noindex'}, 'seo.default_robots'),
    ({'default_robots': ['bogus']}, 'seo.default_robots'),
    ({'twitter_card': 'player'}, 'seo.twitter_card'),
    ({'structured_data': 'product'}, 'seo.structured_data'),
    ({'description_fallback': 'body'}, 'seo.description_fallback'),
    ({'description_length': 0}, 'seo.description_length'),
    ({'description_length': True}, 'seo.description_length'),
    ({'description_length': '160'}, 'seo.description_length'),
    ({'og': 'yes'}, 'seo.og'),
    ({'noindex_tags': 1}, 'seo.noindex_tags'),
  ],
)
def test_bad_values_are_rejected_with_the_key_name(section, key):
  with pytest.raises(ValueError, match=key.replace('.', r'\.')):
    SeoConfig.from_dict(section)


def test_unknown_option_is_rejected():
  with pytest.raises(ValueError, match='Unknown seo option'):
    SeoConfig.from_dict({'keywords': ['a']})


def test_section_must_be_a_mapping():
  with pytest.raises(ValueError, match='must be a mapping'):
    SeoConfig.from_dict(['site_name'])  # type: ignore[arg-type]


# --- Normalizing and the title template -------------------------------------


def test_site_url_trailing_slash_is_dropped():
  assert SeoConfig(site_url='https://example.org/').site_url == (
    'https://example.org'
  )
  assert SeoConfig(site_url='https://example.org/blog/').site_url == (
    'https://example.org/blog'
  )


@pytest.mark.parametrize(
  'image',
  ['/static/social.png', 'https://example.org/a.png', 'http://example.org/a'],
)
def test_default_image_accepts_http_urls_and_root_paths(image):
  assert SeoConfig(default_image=image).default_image == image


@pytest.mark.parametrize(
  'template',
  [
    '{title}',
    '{title} - {site_name}',
    '{site_name}: {title}',
    'Notes | {title}',
    'Plain text, no placeholders',
    '{{literal braces}} {title}',
  ],
)
def test_title_template_accepts_known_placeholders(template):
  assert SeoConfig(title_template=template).title_template == template


@pytest.mark.parametrize(
  'template',
  [
    '{title} - {author}',
    '{}',
    '{0}',
    '{title.__class__}',
    '{title[0]}',
    '{title!r}',
    '{title:>10}',
    '{title',
    'title}',
  ],
)
def test_title_template_rejects_everything_else(template):
  with pytest.raises(ValueError, match=r'seo\.title_template'):
    SeoConfig(title_template=template)


def test_config_is_immutable():
  with pytest.raises(AttributeError):
    SeoConfig().site_name = 'x'  # type: ignore[misc]


# --- The `seo:` section of a schema file ------------------------------------


def _schema_dict(**extra):
  return {'fields': {'title': {'required': True, 'role': 'title'}}, **extra}


def test_schema_without_a_section_has_no_seo():
  assert FrontmatterSchema.from_dict(_schema_dict()).seo is None
  assert DEFAULT_SCHEMA.seo is None


def test_schema_with_an_empty_section_has_default_seo():
  """`seo: {}` turns the SEO output on with all defaults (TODO 5.9.2)."""
  schema = FrontmatterSchema.from_dict(_schema_dict(seo={}))
  assert schema.seo == SeoConfig()


def test_schema_loads_the_section():
  schema = FrontmatterSchema.from_dict(_schema_dict(seo=FULL_SECTION))
  assert schema.seo is not None
  assert schema.seo.site_name == 'Example Notes'


def test_schema_section_round_trips_through_to_dict():
  schema = FrontmatterSchema.from_dict(_schema_dict(seo=FULL_SECTION))
  again = FrontmatterSchema.from_dict(schema.to_dict())
  assert again.seo == schema.seo


def test_schema_file_with_a_seo_section(tmp_path):
  path = tmp_path / 'schema.yaml'
  path.write_text(
    'fields:\n  title: {required: true, role: title}\n'
    'seo:\n  site_name: Example Notes\n  og: true\n',
    encoding='utf-8',
  )
  schema = FrontmatterSchema.from_file(path)
  assert schema.seo == SeoConfig(site_name='Example Notes', og=True)


def test_bad_value_in_a_schema_file_fails_at_load_with_the_key(tmp_path):
  path = tmp_path / 'schema.yaml'
  path.write_text('seo:\n  twitter_card: player\n', encoding='utf-8')
  with pytest.raises(ValueError, match=r'seo\.twitter_card'):
    FrontmatterSchema.from_file(path)


def test_schema_section_that_is_not_a_mapping_fails_at_load():
  with pytest.raises(ValueError, match='must be a mapping'):
    FrontmatterSchema.from_dict(_schema_dict(seo=['site_name']))


def test_with_extra_keeps_seo_and_published_values():
  """`with_extra` used to drop every section but `jsonld`."""
  schema = FrontmatterSchema(
    fields=(
      FieldSpec('state', role='status', required=True),
      FieldSpec('title', role='title'),
    ),
    published_values=('live',),
    seo=SeoConfig(site_name='Example Notes'),
  )
  copy = schema.with_extra('allow')
  assert copy.extra == 'allow'
  assert copy.seo == SeoConfig(site_name='Example Notes')
  assert copy.published_values == ('live',)


# --- The effective settings: the argument beats the section -----------------


def test_resolve_prefers_the_argument_over_the_section():
  argument = SeoConfig(site_name='From argument')
  schema = FrontmatterSchema(seo=SeoConfig(site_name='From section'))
  assert resolve_seo_config(argument, schema) is argument


def test_resolve_replaces_the_section_as_a_whole():
  """Settings aren't merged key by key: the argument stands alone."""
  argument = SeoConfig(site_name='From argument')
  schema = FrontmatterSchema(
    seo=SeoConfig(site_name='From section', default_author='Ann')
  )
  assert resolve_seo_config(argument, schema).default_author is None


def test_resolve_falls_back_to_the_section():
  schema = FrontmatterSchema(seo=SeoConfig(site_name='From section'))
  assert resolve_seo_config(None, schema).site_name == 'From section'


def test_resolve_without_either_is_none():
  assert resolve_seo_config(None, None) is None
  assert resolve_seo_config(None, FrontmatterSchema()) is None


# --- Wiring into the blog ---------------------------------------------------


def _blog(**kwargs):
  app = fastapi_blog.add_blog_to_fastapi(
    FastAPI(),
    posts_dirname='tests/examples/posts',
    strict_frontmatter=False,
    jinja2_loader=jinja2.FileSystemLoader('src/fastapi_blog/templates'),
    **kwargs,
  )
  return TestClient(app)


def _header(html: str, name: str) -> bool:
  return f'>{name}</a></h1>' in html


def test_no_seo_means_no_site_name():
  with _blog() as client:
    assert not _header(client.get('/blog').text, 'Example Notes')


def test_seo_argument_reaches_the_page():
  with _blog(seo=SeoConfig(site_name='Example Notes')) as client:
    assert _header(client.get('/blog').text, 'Example Notes')


def test_schema_section_reaches_the_page():
  schema = FrontmatterSchema(
    fields=(FieldSpec('title', role='title'),),
    extra='allow',
    seo=SeoConfig(site_name='Example Notes'),
  )
  with _blog(frontmatter_schema=schema) as client:
    assert _header(client.get('/blog').text, 'Example Notes')


def test_argument_overrides_the_schema_section_on_the_page():
  schema = FrontmatterSchema(
    fields=(FieldSpec('title', role='title'),),
    extra='allow',
    seo=SeoConfig(site_name='From section'),
  )
  with _blog(
    frontmatter_schema=schema, seo=SeoConfig(site_name='From argument')
  ) as client:
    html = client.get('/blog').text
  assert _header(html, 'From argument')
  assert not _header(html, 'From section')


def test_empty_seo_keeps_the_page_as_it_was():
  """`seo: {}` alone has no `site_name`, so the header stays empty."""
  with _blog(seo=SeoConfig()) as client:
    assert '<h1><a href="/blog/"></a></h1>' in client.get('/blog').text


def test_site_name_reaches_non_default_locale_pages_too():
  """The routers of the other locales used to be built without `seo=`."""
  with _blog(
    seo=SeoConfig(site_name='Example Notes'),
    locales=['en', 'ru'],
    default_locale='en',
  ) as client:
    assert _header(client.get('/blog/').text, 'Example Notes')
    assert _header(client.get('/ru/blog/').text, 'Example Notes')
