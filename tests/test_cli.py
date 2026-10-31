"""Tests for `python -m fastapi_blog` (TODO 5.4/5.7 CLI: export, schema)."""

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


# --- `schema --json-schema` (TODO 5.7) ---------------------------------------


def test_schema_json_schema_prints_the_built_in_fields(capsys):
  exit_code = main(['schema', '--json-schema'])
  assert exit_code == 0
  output = json.loads(capsys.readouterr().out)
  assert output['title'] == 'Frontmatter'
  assert 'title' in output['properties']


def test_schema_json_schema_shows_choices_as_enum(tmp_path, capsys):
  schema_file = tmp_path / 'schema.yaml'
  schema_file.write_text(
    'fields:\n'
    '  status:\n'
    '    required: true\n'
    '    choices: [draft, active, retired]\n',
    encoding='utf-8',
  )
  exit_code = main(['schema', '--json-schema', '--schema', str(schema_file)])
  assert exit_code == 0
  output = json.loads(capsys.readouterr().out)
  assert output['properties']['status']['enum'] == [
    'draft',
    'active',
    'retired',
  ]


def test_schema_json_schema_shows_pattern(tmp_path, capsys):
  schema_file = tmp_path / 'schema.yaml'
  schema_file.write_text(
    'fields:\n  code:\n    pattern: "[A-Z]{3}"\n', encoding='utf-8'
  )
  exit_code = main(['schema', '--json-schema', '--schema', str(schema_file)])
  assert exit_code == 0
  output = json.loads(capsys.readouterr().out)
  assert output['properties']['code']['pattern'] == '[A-Z]{3}'


def test_schema_without_json_schema_flag_is_a_usage_error(capsys):
  exit_code = main(['schema'])
  assert exit_code == 64
  assert '--json-schema' in capsys.readouterr().err


def test_schema_json_schema_reports_a_missing_schema_file(capsys):
  exit_code = main(
    ['schema', '--json-schema', '--schema', 'does-not-exist.yaml']
  )
  assert exit_code == 64
  assert 'does-not-exist.yaml' in capsys.readouterr().err


def test_schema_json_schema_writes_to_out_file(tmp_path):
  out_file = tmp_path / 'schema.json'
  exit_code = main(['schema', '--json-schema', '--out', str(out_file)])
  assert exit_code == 0
  output = json.loads(out_file.read_text(encoding='utf-8'))
  assert output['title'] == 'Frontmatter'


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


# --- Project file and the `check` command (TODO 6.1, phase D) ----------------


@pytest.fixture
def project_dir(tmp_path, monkeypatch):
  monkeypatch.chdir(tmp_path)
  return tmp_path


def _write_config(tmp_path, text):
  (tmp_path / 'fastapi_blog.yaml').write_text(text, encoding='utf-8')


def test_check_clean_default_collection_exits_zero(project_dir, capsys):
  (project_dir / 'posts').mkdir()
  (project_dir / 'posts' / 'a.md').write_text(
    '---\ntitle: A\ndate: "2024-01-01"\npublished: true\n---\nBody.\n',
    encoding='utf-8',
  )
  assert main(['check']) == 0
  assert 'no issues' in capsys.readouterr().out


def test_check_malformed_file_exits_one(project_dir, capsys):
  (project_dir / 'posts').mkdir()
  (project_dir / 'posts' / 'bad.md').write_text(
    '---\ntitle: [unterminated\n---\n', encoding='utf-8'
  )
  assert main(['check']) == 1
  assert 'file.malformed' in capsys.readouterr().out


def test_check_json_output_and_fail_on_warning(project_dir, capsys):
  (project_dir / 'posts').mkdir()
  (project_dir / 'posts' / 'a.md').write_text(
    '---\ntitle: A\n---\n', encoding='utf-8'
  )
  _write_config(
    project_dir,
    'collections:\n  posts:\n    dir: posts\n    schema: schema.yaml\n',
  )
  (project_dir / 'schema.yaml').write_text(
    'extra: allow\nfields:\n  title: {required: true}\n  gone:\n',
    encoding='utf-8',
  )
  assert main(['check', '--json']) == 0
  report = json.loads(capsys.readouterr().out)
  assert report['collections'][0]['documents'] == 1


def test_check_uses_the_project_file_and_collection_flag(project_dir, capsys):
  for name in ('posts', 'notes'):
    (project_dir / name).mkdir()
  (project_dir / 'notes' / 'bad.md').write_text(
    '---\ntitle: [unterminated\n---\n', encoding='utf-8'
  )
  _write_config(
    project_dir,
    'collections:\n  posts:\n    dir: posts\n  notes:\n    dir: notes\n',
  )
  # Default: the `posts` collection of the project file (clean).
  assert main(['check']) == 0
  # An explicit name checks that collection (findings).
  assert main(['check', '--collection', 'notes']) == 1
  assert main(['check', '--collection', 'missing']) == 64


def test_check_requires_collection_choice_for_many(project_dir, capsys):
  for name in ('a', 'b'):
    (project_dir / name).mkdir()
  _write_config(
    project_dir, 'collections:\n  one:\n    dir: a\n  two:\n    dir: b\n'
  )
  # No `posts` and several collections: asking for a name is a usage error.
  assert main(['check']) == 64
  assert main(['check', '--collection', 'one']) == 0


def test_export_uses_the_project_file_and_flag_overrides(project_dir, capsys):
  (project_dir / 'content').mkdir()
  (project_dir / 'content' / 'note.md').write_text(
    '---\ntitle: Note\ndate: "2024-01-01"\npublished: true\n---\nBody.\n',
    encoding='utf-8',
  )
  _write_config(
    project_dir,
    'collections:\n  notes:\n    dir: content\n',
  )
  # The project file names the directory; a single collection is the default.
  assert main(['export']) == 0
  graph = json.loads(capsys.readouterr().out)
  assert graph['@graph'][0]['title'] == 'Note'
  # A CLI flag beats the project file: --posts-dir points elsewhere.
  (project_dir / 'other').mkdir()
  (project_dir / 'other' / 'b.md').write_text(
    '---\ntitle: Other\ndate: "2024-01-02"\npublished: true\n---\nBody.\n',
    encoding='utf-8',
  )
  assert main(['export', '--posts-dir', 'other']) == 0
  graph = json.loads(capsys.readouterr().out)
  assert graph['@graph'][0]['title'] == 'Other'
  assert main(['export', '--collection', 'notes']) == 0


def test_check_runs_validators_from_the_project_file(project_dir, capsys):
  import sys

  (project_dir / 'posts').mkdir()
  (project_dir / 'posts' / 'a.md').write_text(
    '---\ntitle: A\ndate: "2024-01-01"\npublished: true\n---\nBody.\n',
    encoding='utf-8',
  )
  fail = f"['{sys.executable}', '-c', 'import sys; sys.exit(1)']"
  _write_config(
    project_dir,
    'collections:\n  posts:\n    dir: posts\n    validators:\n'
    f'      - name: gate\n        argv: {fail}\n',
  )
  assert main(['check']) == 1
  assert 'validator.gate' in capsys.readouterr().out
