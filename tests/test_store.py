"""Frontmatter parsing/serialization and atomic writes (phase B, 4.2-4.4)."""

import re

import pytest

from fastapi_blog import store


def test_round_trip_preserves_a_table_and_a_dash_value(tmp_path):
  """A `---` inside a table or a YAML value must not be mistaken for a boundary."""
  frontmatter = {'title': 'Hi', 'note': 'a --- dash'}
  body = 'Intro\n\n|---|---|\n|a|b|\n\nMore text\n'
  path = tmp_path / 'post.md'
  store.write_document(path, frontmatter, body)

  parsed_fm, parsed_body = store.read_document(path)
  assert parsed_fm == frontmatter
  assert parsed_body == body

  # Re-serializing what we just parsed gives back the same bytes.
  store.write_document(path, parsed_fm, parsed_body)
  assert path.read_text(encoding='utf-8') == store.serialize_document(
    frontmatter, body
  )


def test_document_without_frontmatter_is_all_body():
  fm, body = store.parse_document('Just a plain file.\n')
  assert fm == {}
  assert body == 'Just a plain file.\n'


def test_bom_is_skipped_before_the_opening_marker():
  fm, body = store.parse_document('﻿---\ntitle: Hi\n---\nBody\n')
  assert fm == {'title': 'Hi'}
  assert body == 'Body\n'


def test_closing_marker_may_be_ellipsis():
  fm, body = store.parse_document('---\ntitle: Hi\n...\nBody\n')
  assert fm == {'title': 'Hi'}
  assert body == 'Body\n'


def test_unterminated_frontmatter_is_treated_as_plain_body():
  text = '---\ntitle: Hi\nno closing marker here\n'
  fm, body = store.parse_document(text)
  assert fm == {}
  assert body == text


def test_empty_frontmatter_block():
  fm, body = store.parse_document('---\n---\nBody\n')
  assert fm == {}
  assert body == 'Body\n'


def test_invalid_yaml_raises_value_error():
  with pytest.raises(ValueError, match='invalid YAML'):
    store.parse_document('---\nkey: [unterminated\n---\nBody\n')


def test_non_mapping_frontmatter_raises_value_error():
  with pytest.raises(ValueError, match='mapping'):
    store.parse_document('---\n- a\n- b\n---\nBody\n')


def test_atomic_write_leaves_no_temp_file_behind(tmp_path):
  path = tmp_path / 'post.md'
  store.atomic_write_text(path, 'content\n')
  assert path.read_text(encoding='utf-8') == 'content\n'
  leftovers = [p for p in tmp_path.iterdir() if p != path]
  assert leftovers == []


def test_atomic_write_replaces_existing_file(tmp_path):
  path = tmp_path / 'post.md'
  path.write_text('old', encoding='utf-8')
  store.atomic_write_text(path, 'new')
  assert path.read_text(encoding='utf-8') == 'new'


SLUG_PATTERN = re.compile(r'[a-z0-9][a-z0-9-]{0,99}')


def test_safe_document_path_rejects_bad_slug(tmp_path):
  with pytest.raises(ValueError, match='invalid slug'):
    store.safe_document_path(tmp_path, '../escape', pattern=SLUG_PATTERN)


def test_safe_document_path_rejects_symlink_escape(tmp_path):
  collection = tmp_path / 'posts'
  collection.mkdir()
  outside = tmp_path / 'outside.md'
  outside.write_text('secret', encoding='utf-8')
  (collection / 'leak.md').symlink_to(outside)
  with pytest.raises(ValueError, match='escapes'):
    store.safe_document_path(collection, 'leak', pattern=SLUG_PATTERN)


def test_safe_document_path_accepts_a_normal_slug(tmp_path):
  path = store.safe_document_path(tmp_path, 'hello-world', pattern=SLUG_PATTERN)
  assert path == tmp_path / 'hello-world.md'


def test_compute_etag_is_stable_and_content_sensitive():
  assert store.compute_etag('a') == store.compute_etag('a')
  assert store.compute_etag('a') != store.compute_etag('b')
