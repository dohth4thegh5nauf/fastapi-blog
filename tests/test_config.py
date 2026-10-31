"""Tests for the project file (`fastapi_blog.yaml`, TODO phase D)."""

import datetime

import pytest

from fastapi_blog import config
from fastapi_blog.models import FieldSpec, FrontmatterSchema


@pytest.fixture
def project_dir(tmp_path, monkeypatch):
  monkeypatch.chdir(tmp_path)
  return tmp_path


def _write(project_dir, text):
  (project_dir / 'fastapi_blog.yaml').write_text(text, encoding='utf-8')


def test_load_project_reads_collections_in_file_order(project_dir):
  (project_dir / 'a').mkdir()
  (project_dir / 'b').mkdir()
  _write(
    project_dir,
    'collections:\n  notes:\n    dir: a\n  pages:\n    dir: b\n',
  )
  project = config.load_project(project_dir / 'fastapi_blog.yaml')
  assert project.root == project_dir
  assert list(project.collections) == ['notes', 'pages']
  assert project.collections['notes'].dir == project_dir / 'a'
  assert project.collections['pages'].dir == project_dir / 'b'


def test_load_project_reads_schema_slug_pattern_and_extension(project_dir):
  (project_dir / 'content').mkdir()
  (project_dir / 'content' / 'schema.yaml').write_text(
    'fields:\n  title: {required: true}\n', encoding='utf-8'
  )
  _write(
    project_dir,
    'collections:\n  notes:\n'
    '    dir: content\n'
    '    schema: content/schema.yaml\n'
    "    slug_pattern: '[0-9]{4}-[a-z0-9-]+'\n"
    '    extension: [md, markdown]\n',
  )
  spec = config.load_project(project_dir / 'fastapi_blog.yaml').collections[
    'notes'
  ]
  assert spec.schema is not None
  assert spec.schema.fields[0].name == 'title'
  collection = spec.to_collection()
  assert collection.extensions == ('md', 'markdown')
  assert collection.slug_pattern.fullmatch('2024-hello')
  assert not collection.slug_pattern.fullmatch('hello')


def test_find_project_returns_none_without_a_file(project_dir):
  assert config.find_project() is None


def test_find_project_does_not_search_parent_directories(
  project_dir, monkeypatch
):
  _write(project_dir, 'collections:\n  notes:\n    dir: posts\n')
  nested = project_dir / 'nested'
  nested.mkdir()
  monkeypatch.chdir(nested)
  assert config.find_project() is None


@pytest.mark.parametrize(
  'text',
  [
    'not a mapping\n',
    'other: true\n',
    'collections: []\n',
    'collections: {}\n',
    'collections:\n  notes: just-a-string\n',
    'collections:\n  notes:\n    schema: x.yaml\n',
    'collections:\n  notes:\n    dir: posts\n    bogus: 1\n',
    'collections:\n  notes:\n    dir: posts\n    extension: 42\n',
  ],
)
def test_load_project_rejects_bad_files(project_dir, text):
  _write(project_dir, text)
  with pytest.raises(config.ConfigError):
    config.load_project(project_dir / 'fastapi_blog.yaml')


def test_load_project_wraps_a_bad_schema_file(project_dir):
  (project_dir / 'schema.yaml').write_text(
    'fields:\n  bad-name: {}\n', encoding='utf-8'
  )
  _write(
    project_dir,
    'collections:\n  notes:\n    dir: posts\n    schema: schema.yaml\n',
  )
  with pytest.raises(config.ConfigError, match='notes'):
    config.load_project(project_dir / 'fastapi_blog.yaml')


def test_collection_spec_defaults_to_the_standard_collection(project_dir):
  spec = config.CollectionSpec(name='posts', dir=project_dir / 'posts')
  collection = spec.to_collection()
  assert collection.name == 'posts'
  assert collection.slug_pattern == config.store.DEFAULT_SLUG_PATTERN
  assert collection.extensions == ('md',)


def test_collection_spec_carries_an_inline_schema():
  schema = FrontmatterSchema(
    fields=(FieldSpec('title', required=True),), extra='allow'
  )
  spec = config.CollectionSpec(name='notes', dir='x', schema=schema)
  assert spec.to_collection().name == 'notes'
  assert spec.schema is schema


def test_slug_template_and_unique_seq_are_loaded(project_dir):
  (project_dir / 'posts').mkdir()
  (project_dir / 'schema.yaml').write_text(
    'fields:\n  title: {role: title}\n', encoding='utf-8'
  )
  _write(
    project_dir,
    'collections:\n  posts:\n    dir: posts\n    schema: schema.yaml\n'
    '    slug_template: "{seq|pad(4)}-{title_slug}"\n'
    '    unique: [seq]\n'
    '    summary: "{title}"\n',
  )
  spec = config.load_project(project_dir / 'fastapi_blog.yaml').collections[
    'posts'
  ]
  assert spec.slug_template is not None
  assert spec.unique == ('seq',)
  assert spec.make_slug({'title': 'Hello World'}, []) == '0001-hello-world'
  store = config.store.DocumentStore(spec.to_collection())
  slug, _etag = spec.create_document(store, {'title': 'Hello World'}, 'Body')
  assert slug == '0001-hello-world'
  slug2, _etag2 = spec.create_document(store, {'title': 'Another'}, 'Body')
  assert slug2 == '0002-another'
  assert spec.summarize('0001-hello-world', {'title': 'Hello'}) == 'Hello'


def test_default_schema_fields_are_available_to_collection_templates(
  project_dir,
):
  (project_dir / 'posts').mkdir()
  _write(
    project_dir,
    'collections:\n  posts:\n    dir: posts\n'
    '    slug_template: "{year}-{title_slug}"\n'
    '    summary: "{title}"\n',
  )
  spec = config.load_project(project_dir / 'fastapi_blog.yaml').collections[
    'posts'
  ]
  assert spec.slug_template is not None
  assert spec.summarize('2026-hello', {'title': 'Hello'}) == 'Hello'


def test_collection_slug_uses_first_save_utc_when_date_is_missing(project_dir):
  (project_dir / 'posts').mkdir()
  _write(
    project_dir,
    'collections:\n  posts:\n    dir: posts\n'
    '    slug_template: "{year}-{month}-{day}-{title_slug}"\n',
  )
  spec = config.load_project(project_dir / 'fastapi_blog.yaml').collections[
    'posts'
  ]
  created_at = datetime.datetime(2024, 2, 3, 23, 30, tzinfo=datetime.UTC)
  store = config.store.DocumentStore(spec.to_collection())
  slug, _etag = spec.create_document(
    store, {'title': 'Hello'}, 'Body', created_at=created_at
  )
  assert slug == '2024-02-03-hello'


def test_unique_seq_requires_sequence_tag(project_dir):
  _write(
    project_dir,
    'collections:\n  posts:\n    dir: posts\n'
    '    slug_template: "{title_slug}"\n    unique: [seq]\n',
  )
  with pytest.raises(config.ConfigError, match='slug_template'):
    config.load_project(project_dir / 'fastapi_blog.yaml')


def test_load_project_reads_create_and_delete_flags(project_dir):
  (project_dir / 'posts').mkdir()
  (project_dir / 'pages').mkdir()
  _write(
    project_dir,
    'collections:\n  posts:\n    dir: posts\n    create: false\n'
    '  pages:\n    dir: pages\n    delete: false\n',
  )
  project = config.load_project(project_dir / 'fastapi_blog.yaml')
  posts = project.collections['posts'].to_collection()
  pages = project.collections['pages'].to_collection()
  assert posts.create is False
  assert posts.delete is True
  assert pages.create is True
  assert pages.delete is False


def test_load_project_rejects_non_boolean_create_delete(project_dir):
  _write(
    project_dir,
    "collections:\n  posts:\n    dir: posts\n    create: 'sometimes'\n",
  )
  with pytest.raises(config.ConfigError, match='`create`'):
    config.load_project(project_dir / 'fastapi_blog.yaml')
