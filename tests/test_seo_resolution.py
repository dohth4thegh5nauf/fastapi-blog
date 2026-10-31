"""One test group per row of the TODO 5.9.3 substitution table."""

import pytest

from fastapi_blog.models import SeoConfig
from fastapi_blog.seo import build_head


URL = 'https://example.test/blog/posts/x?utm=1'


def head(doc=None, page_type='article', body='', **config):
  return build_head(
    doc,
    config=SeoConfig(**config),
    request_url=URL,
    page_type=page_type,
    body=body,
    locale='en',
  )


def test_title_order_template_and_site_name_fallback():
  assert head({'title': 'T'})['title'] == 'T'
  assert head({'title': 'T', 'seo_title': 'S'})['title'] == 'S'
  templated = head(
    {'title': 'T'}, site_name='Site', title_template='{title} - {site_name}'
  )
  assert templated['title'] == 'T - Site'
  assert head({}, site_name='Site')['title'] == 'Site'
  assert head({})['title'] is None


def test_description_order():
  assert (
    head(
      {'description': 'D'}, description_fallback='excerpt', body='Body text'
    )['description']
    == 'D'
  )
  assert (
    head({}, description_fallback='excerpt', body='Body text')['description']
    == 'Body text'
  )
  assert (
    head({}, page_type='index', index_description='Idx')['description'] == 'Idx'
  )
  assert head({}, index_description='Idx')['description'] is None
  assert head({}, body='Body text')['description'] is None


def test_excerpt_strips_markup_and_cuts_on_a_word_boundary():
  body = '# Title\n\n<p>Hello <b>big</b> [link](http://x) `code` world</p>'
  text = head({}, description_fallback='excerpt', body=body)['description']
  assert '<' not in text and '](' not in text and '`' not in text
  cut = head(
    {},
    description_fallback='excerpt',
    description_length=14,
    body='alpha beta gamma delta',
  )['description']
  assert cut == 'alpha beta'
  assert head({}, description_fallback='excerpt', body=body) == head(
    {}, description_fallback='excerpt', body=body
  )


def test_canonical_order():
  assert head({})['canonical_url'] == 'https://example.test/blog/posts/x'
  assert (
    head({'canonical': 'https://other.test/a'})['canonical_url']
    == 'https://other.test/a'
  )
  assert (
    head({'canonical': '/moved'}, site_url='https://site.test')['canonical_url']
    == 'https://site.test/moved'
  )
  # Anything but http(s) or a root path is dropped
  assert (
    head({'canonical': 'javascript:alert(1)'})['canonical_url']
    == 'https://example.test/blog/posts/x'
  )


def test_image_order():
  assert (
    head({'image': 'https://i.test/a.png'}, default_image='/d.png')['og_image']
    == 'https://i.test/a.png'
  )
  assert (
    head({}, default_image='/d.png', site_url='https://s.test')['og_image']
    == 'https://s.test/d.png'
  )
  assert head({'image': 'data:image/png;base64,AAAA'})['og_image'] is None


def test_modified_time_order():
  assert (
    head({'date': '2026-01-01', 'updated': '2026-02-02'})['og_modified_time']
    == '2026-02-02'
  )
  assert head({'date': '2026-01-01'})['og_modified_time'] == '2026-01-01'
  assert head({})['og_modified_time'] is None


def test_author_order():
  assert head({'author': 'Ann'}, default_author='Def')['author'] == 'Ann'
  assert head({}, default_author='Def')['author'] == 'Def'
  assert head({'author': ['Ann', 'Bob']})['author'] == 'Ann, Bob'
  assert head({})['author'] is None


def test_robots_union_without_duplicates_in_stable_order():
  result = head(
    {'robots': ['noindex', 'nofollow']},
    default_robots=('nofollow', 'noarchive'),
  )['robots']
  assert result == ['noindex', 'nofollow', 'noarchive']


@pytest.mark.parametrize(
  ('doc', 'expected'), [({'lang': 'de'}, 'de'), ({}, 'en')]
)
def test_language_order(doc, expected):
  assert head(doc)['lang'] == expected
