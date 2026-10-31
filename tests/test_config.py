"""Tests for the project file (`fastapi_blog.yaml`, TODO phase D)."""

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
