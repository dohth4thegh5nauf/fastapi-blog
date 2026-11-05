"""Shared template language and slug generation (TODO 6.4)."""

import datetime

import pytest

from fastapi_blog.templates import (
  SlugOptions,
  build_slug,
  make_slug_part,
  next_seq,
  parse_template,
)


TAGS = ('seq', 'title_slug', 'year', 'month', 'day', 'slug', 'collection')


def test_slug_template_renders_with_pad_and_title():
  template = parse_template('{seq|pad(4)}-{title_slug}', TAGS)
  slug = template.render(
    {'seq': 7, 'title_slug': make_slug_part('Use plain files!')}
  )
  assert slug == '0007-use-plain-files'


def test_slug_template_rejects_repeated_capture_tags():
  template = parse_template('{seq}-{seq}-{title_slug}', TAGS)
  with pytest.raises(ValueError, match='seq.*only once'):
    template.slug_regex()


def test_next_seq_is_highest_plus_one_and_ignores_other_names():
  template = parse_template('{seq|pad(4)}-{title_slug}', TAGS)
  assert next_seq(template, ['0001-a', '0009-b', 'junk', 'dir/0003-c']) == 10
  assert next_seq(template, []) == 1


def test_build_slug_uses_date_and_sequence():
  template = parse_template('{year}/{seq|pad(4)}-{title_slug}', TAGS)
  slug = build_slug(
    template,
    title='Café Déjà vu',
    existing_slugs=['2026/0003-old', '2026/0009-old'],
    date_value='2026-04-02',
  )
  assert slug == '2026/0010-café-déjà-vu'


def test_build_slug_accepts_allocated_sequence():
  template = parse_template('{seq|pad(4)}-{title_slug}', TAGS)
  slug = build_slug(template, title='Hello World', sequence=42)
  assert slug == '0042-hello-world'


def test_build_slug_rejects_invalid_allocated_sequence():
  template = parse_template('{seq|pad(4)}-{title_slug}', TAGS)
  for sequence in (0, -1, True, '42'):
    with pytest.raises(ValueError, match='positive integer'):
      build_slug(template, title='Hello World', sequence=sequence)


def test_build_slug_uses_first_save_utc_when_date_missing():
  template = parse_template('{year}-{month}-{day}-{title_slug}', TAGS)
  slug = build_slug(
    template,
    title='Hello',
    created_at=datetime.datetime(2024, 2, 3, 23, 30, tzinfo=datetime.UTC),
  )
  assert slug == '2024-02-03-hello'


def test_fields_filters_and_default():
  template = parse_template(
    '{status|upper} {fields.title|truncate(5)} {date|date(%Y)} {gone|default(none)}',
    TAGS,
    {'status', 'title', 'date', 'gone'},
  )
  text = template.render(
    {},
    {
      'status': 'live',
      'title': 'hello world',
      'date': '2026-10-01',
      'gone': None,
    },
  )
  assert text == 'LIVE hello 2026 none'


def test_fields_prefix_is_the_explicit_form_for_clashing_names():
  template = parse_template('{fields.year}', TAGS, {'year'})
  assert template.render({'year': '1999'}, {'year': 2026}) == '2026'


@pytest.mark.parametrize(
  'source',
  [
    '{nope}',
    '{seq|zzz}',
    '{seq|pad}',
    '{seq|pad(x)}',
    '{seq',
    'x}',
    '{fields.zzz}',
    '{slug|lower(1)}',
  ],
)
def test_bad_templates_fail_at_parse_time(source):
  with pytest.raises(ValueError):
    parse_template(source, TAGS, {'status'})


def test_nothing_is_evaluated():
  template = parse_template('{status}', TAGS, {'status'})
  assert template.render({}, {'status': '{seq}'}) == '{seq}'


def test_slug_options():
  assert make_slug_part('Café Déjà vu') == 'café-déjà-vu'
  assert (
    make_slug_part('Café Déjà vu', SlugOptions(clean_accents=True))
    == 'cafe-deja-vu'
  )
  assert make_slug_part('Привет мир') == 'привет-мир'
  assert make_slug_part('Привет', SlugOptions(encoding='ascii')) == 'untitled'
  assert make_slug_part('a  b', SlugOptions(sanitize_replacement='_')) == 'a_b'
  assert make_slug_part('!!!') == 'untitled'


def test_file_name_is_cut_to_200_bytes_on_a_character_boundary():
  assert len(make_slug_part('я' * 300).encode()) <= 200
