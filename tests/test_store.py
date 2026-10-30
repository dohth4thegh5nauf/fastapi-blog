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


# --- Collection / DocumentStore (4.1, 4.6, 4.7) -----------------------------


def test_collection_rejects_nested_depth(tmp_path):
  with pytest.raises(NotImplementedError, match='depth'):
    store.Collection('posts', tmp_path, depth=1)


def test_collection_normalizes_extensions(tmp_path):
  one = store.Collection('posts', tmp_path, extension='.md')
  many = store.Collection('posts', tmp_path, extension=('md', '.markdown'))
  assert one.extensions == ('md',)
  assert many.extensions == ('md', 'markdown')


def test_document_store_round_trip(tmp_path):
  docs = store.DocumentStore(store.Collection('posts', tmp_path))
  etag = docs.write('hello-world', {'title': 'Hi'}, 'Body\n')

  assert docs.exists('hello-world')
  record = docs.read('hello-world')
  assert record.frontmatter == {'title': 'Hi'}
  assert record.body == 'Body\n'
  assert record.etag == etag


def test_document_store_list(tmp_path):
  docs = store.DocumentStore(store.Collection('posts', tmp_path))
  assert docs.list() == []
  docs.write('a', {}, '')
  docs.write('b', {}, '')
  assert sorted(docs.list()) == ['a', 'b']


def test_document_store_list_on_missing_directory(tmp_path):
  docs = store.DocumentStore(store.Collection('posts', tmp_path / 'nope'))
  assert docs.list() == []


def test_document_store_only_creates_the_directory_on_write(tmp_path):
  collection_dir = tmp_path / 'posts'
  docs = store.DocumentStore(store.Collection('posts', collection_dir))
  assert not docs.exists('x')
  assert not collection_dir.exists()
  docs.write('x', {}, '')
  assert collection_dir.is_dir()


def test_document_store_read_missing_raises(tmp_path):
  docs = store.DocumentStore(store.Collection('posts', tmp_path))
  with pytest.raises(FileNotFoundError):
    docs.read('missing')


def test_document_store_rejects_path_traversal(tmp_path):
  docs = store.DocumentStore(store.Collection('posts', tmp_path))
  with pytest.raises(ValueError, match='invalid slug'):
    docs.write('../escape', {}, '')
  assert not docs.exists('../escape')


def test_document_store_delete(tmp_path):
  docs = store.DocumentStore(store.Collection('posts', tmp_path))
  docs.write('x', {}, '')
  docs.delete('x')
  assert not docs.exists('x')


def test_document_store_delete_missing_raises(tmp_path):
  docs = store.DocumentStore(store.Collection('posts', tmp_path))
  with pytest.raises(FileNotFoundError):
    docs.delete('missing')


def test_document_store_create_false_blocks_new_documents(tmp_path):
  collection = store.Collection('posts', tmp_path, create=False)
  docs = store.DocumentStore(collection)
  with pytest.raises(PermissionError):
    docs.write('new', {}, '')


def test_document_store_create_false_still_allows_rewriting(tmp_path):
  collection_dir = tmp_path
  store.write_document(collection_dir / 'existing.md', {'title': 'Old'}, '')
  docs = store.DocumentStore(
    store.Collection('posts', collection_dir, create=False)
  )
  docs.write('existing', {'title': 'New'}, '')
  assert docs.read('existing').frontmatter == {'title': 'New'}


def test_document_store_delete_false_blocks_delete(tmp_path):
  collection = store.Collection('posts', tmp_path, delete=False)
  docs = store.DocumentStore(collection)
  docs.write('x', {}, '')
  with pytest.raises(PermissionError):
    docs.delete('x')
  assert docs.exists('x')


def test_document_store_write_preserves_a_non_primary_extension(tmp_path):
  """Rewriting a `.markdown` file keeps it `.markdown`, not `.md`."""
  collection = store.Collection('posts', tmp_path, extension=('md', 'markdown'))
  (tmp_path / 'legacy.markdown').write_text('---\ntitle: Old\n---\n')
  docs = store.DocumentStore(collection)
  docs.write('legacy', {'title': 'New'}, '')
  assert not (tmp_path / 'legacy.md').exists()
  assert (tmp_path / 'legacy.markdown').exists()


def test_document_store_write_if_match_succeeds_with_current_etag(tmp_path):
  docs = store.DocumentStore(store.Collection('posts', tmp_path))
  etag = docs.write('x', {'v': 1}, '')
  docs.write('x', {'v': 2}, '', if_match=etag)
  assert docs.read('x').frontmatter == {'v': 2}


def test_document_store_write_if_match_rejects_stale_etag(tmp_path):
  docs = store.DocumentStore(store.Collection('posts', tmp_path))
  etag = docs.write('x', {'v': 1}, '')
  docs.write('x', {'v': 2}, '')  # a concurrent writer moves it on
  with pytest.raises(store.ConflictError) as exc_info:
    docs.write('x', {'v': 3}, '', if_match=etag)
  assert exc_info.value.status_code == 412
  assert docs.read('x').frontmatter == {'v': 2}  # rejected write didn't land


def test_document_store_write_if_match_on_missing_document_is_409(tmp_path):
  docs = store.DocumentStore(store.Collection('posts', tmp_path))
  with pytest.raises(store.ConflictError) as exc_info:
    docs.write('missing', {}, '', if_match='whatever')
  assert exc_info.value.status_code == 409


def test_document_store_delete_if_match_rejects_stale_etag(tmp_path):
  docs = store.DocumentStore(store.Collection('posts', tmp_path))
  etag = docs.write('x', {'v': 1}, '')
  docs.write('x', {'v': 2}, '')
  with pytest.raises(store.ConflictError) as exc_info:
    docs.delete('x', if_match=etag)
  assert exc_info.value.status_code == 412
  assert docs.exists('x')


def test_document_store_delete_if_match_succeeds_with_current_etag(tmp_path):
  docs = store.DocumentStore(store.Collection('posts', tmp_path))
  etag = docs.write('x', {}, '')
  docs.delete('x', if_match=etag)
  assert not docs.exists('x')
