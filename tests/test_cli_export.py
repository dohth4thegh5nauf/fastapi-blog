"""Tests for `python -m fastapi_blog export` (TODO 5.4/5.7 CLI side)."""

import json

import pytest

from fastapi_blog.__main__ import main


@pytest.fixture
def posts_dir(tmp_path):
  posts = tmp_path / 'posts'
  posts.mkdir()
  (posts / 'hello.md').write_text(
    '---\ntitle: Hello World\ndate: "2024-01-01"\npublished: true\n---\nBody.\n',
    encoding='utf-8',
  )
  return posts


def test_export_jsonld_to_stdout(posts_dir, capsys):
  exit_code = main(['export', '--posts-dir', str(posts_dir)])
  assert exit_code == 0
  output = json.loads(capsys.readouterr().out)
  assert output['@graph'][0]['title'] == 'Hello World'


def test_export_jsonld_to_file(posts_dir, tmp_path):
  out_file = tmp_path / 'out.jsonld'
  exit_code = main(
    ['export', '--posts-dir', str(posts_dir), '--out', str(out_file)]
  )
  assert exit_code == 0
  output = json.loads(out_file.read_text(encoding='utf-8'))
  assert output['@graph'][0]['title'] == 'Hello World'


def test_export_output_is_deterministic_regardless_of_file_order(tmp_path):
  posts = tmp_path / 'posts'
  posts.mkdir()
  (posts / 'b.md').write_text(
    '---\ntitle: B\ndate: "2024-01-02"\npublished: true\n---\n'
  )
  (posts / 'a.md').write_text(
    '---\ntitle: A\ndate: "2024-01-01"\npublished: true\n---\n'
  )
  out1, out2 = tmp_path / 'out1.jsonld', tmp_path / 'out2.jsonld'
  main(['export', '--posts-dir', str(posts), '--out', str(out1)])
  main(['export', '--posts-dir', str(posts), '--out', str(out2)])
  assert out1.read_text(encoding='utf-8') == out2.read_text(encoding='utf-8')


def test_export_uses_schema_file_jsonld_section(tmp_path, posts_dir):
  schema_file = tmp_path / 'schema.yaml'
  schema_file.write_text(
    """
fields:
  title:
    required: true
    role: title
  date:
    required: true
    role: date
  published:
    type: bool
    role: published
jsonld:
  context:
    "@vocab": "https://example.org/vocab#"
  base: "https://example.org/"
  id_template: "{base}{collection}/{slug}"
  type: Note
""",
    encoding='utf-8',
  )
  exit_code = main(
    [
      'export',
      '--posts-dir',
      str(posts_dir),
      '--schema',
      str(schema_file),
      '--collection',
      'notes',
    ]
  )
  assert exit_code == 0


def test_export_reports_a_missing_schema_file_as_a_usage_error(
  posts_dir, capsys
):
  exit_code = main(
    ['export', '--posts-dir', str(posts_dir), '--schema', 'does-not-exist.yaml']
  )
  assert exit_code == 64
  assert 'does-not-exist.yaml' in capsys.readouterr().err


def test_export_expanded_format_needs_pyld(posts_dir, capsys, monkeypatch):
  import sys

  monkeypatch.setitem(sys.modules, 'pyld', None)
  exit_code = main(
    ['export', '--posts-dir', str(posts_dir), '--format', 'expanded']
  )
  assert exit_code == 64
  assert 'jsonld` extra' in capsys.readouterr().err


def test_export_nquads_format_is_sorted(tmp_path):
  pytest.importorskip('pyld')
  posts = tmp_path / 'posts'
  posts.mkdir()
  (posts / 'hello.md').write_text(
    '---\ntitle: Hello\nstatus: active\n---\n', encoding='utf-8'
  )
  schema_file = tmp_path / 'schema.yaml'
  schema_file.write_text(
    """
fields:
  title: {required: true, role: title}
  status: {required: true}
jsonld:
  context: {"@vocab": "https://example.org/vocab#"}
  base: "https://example.org/"
  id_template: "{base}{collection}/{slug}"
  type: Note
""",
    encoding='utf-8',
  )
  out1, out2 = tmp_path / 'o1.nq', tmp_path / 'o2.nq'
  main(
    [
      'export',
      '--posts-dir',
      str(posts),
      '--schema',
      str(schema_file),
      '--format',
      'nquads',
      '--out',
      str(out1),
    ]
  )
  main(
    [
      'export',
      '--posts-dir',
      str(posts),
      '--schema',
      str(schema_file),
      '--format',
      'nquads',
      '--out',
      str(out2),
    ]
  )
  text1 = out1.read_text(encoding='utf-8')
  text2 = out2.read_text(encoding='utf-8')
  assert text1 == text2
  lines = [line for line in text1.splitlines() if line]
  assert lines == sorted(lines)
  assert len(lines) >= 2
