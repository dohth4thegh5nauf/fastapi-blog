"""Tests for `check_collection` and the exit-code rules (TODO 6.1)."""

import pytest

from fastapi_blog import checks
from fastapi_blog.config import CollectionSpec
from fastapi_blog.models import FieldSpec, FrontmatterSchema, JsonLdConfig


def _spec(tmp_path, schema=None, name='posts'):
  directory = tmp_path / name
  directory.mkdir(exist_ok=True)
  return CollectionSpec(name=name, dir=directory, schema=schema)


def _write(directory, slug, text):
  (directory / f'{slug}.md').write_text(text, encoding='utf-8')


TITLE_SCHEMA = FrontmatterSchema(fields=(FieldSpec('title', required=True),))


def test_clean_collection_reports_no_issues(tmp_path):
  spec = _spec(tmp_path, TITLE_SCHEMA)
  _write(spec.dir, 'a', '---\ntitle: A\n---\nBody\n')
  _write(spec.dir, 'b', '---\ntitle: B\n---\nBody\n')
  report = checks.check_collection(spec, root=tmp_path)
  assert report.documents == 2
  assert report.issues == []


def test_malformed_file_is_an_error(tmp_path):
  spec = _spec(tmp_path, TITLE_SCHEMA)
  _write(spec.dir, 'good', '---\ntitle: A\n---\n')
  _write(spec.dir, 'bad', '---\ntitle: [unterminated\n---\n')
  report = checks.check_collection(spec, root=tmp_path)
  assert [issue.code for issue in report.issues] == ['file.malformed']
  assert report.issues[0].slug == 'bad'


def test_schema_mismatch_reports_missing_and_extra(tmp_path):
  spec = _spec(tmp_path, TITLE_SCHEMA)  # extra defaults to 'forbid'
  _write(spec.dir, 'missing', '---\nbody: x\n---\n')
  _write(spec.dir, 'extra', '---\ntitle: A\nother: 1\n---\n')
  report = checks.check_collection(spec, root=tmp_path)
  codes = {issue.code for issue in report.issues}
  assert codes == {'schema.missing', 'schema.extra'}
  assert checks.exit_code([report]) == checks.EXIT_FINDINGS


def test_missing_directory_is_undefined_not_clean(tmp_path):
  spec = CollectionSpec(name='posts', dir=tmp_path / 'nope')
  report = checks.check_collection(spec, root=tmp_path)
  assert [issue.level for issue in report.issues] == ['undefined']
  assert report.issues[0].code == 'collection.directory_missing'
  assert checks.exit_code([report]) == checks.EXIT_UNDEFINED


def test_lost_context_terms_are_warnings(tmp_path):
  schema = FrontmatterSchema(
    fields=(
      FieldSpec('title', required=True),
      FieldSpec('state', alias='ex:state'),
    ),
    jsonld=JsonLdConfig(context={'title': 'https://example.org/title'}),
  )
  spec = _spec(tmp_path, schema)
  _write(spec.dir, 'a', '---\ntitle: A\nex:state: active\n---\n')
  report = checks.check_collection(spec, root=tmp_path)
  assert [(issue.level, issue.code) for issue in report.issues] == [
    ('warning', 'context.lost_term')
  ]
  assert report.issues[0].field == 'ex:state'
  # A warning doesn't fail `--fail-on error`, but fails `--fail-on warning`.
  assert checks.exit_code([report], 'error') == checks.EXIT_CLEAN
  assert checks.exit_code([report], 'warning') == checks.EXIT_FINDINGS


def test_unavailable_context_is_undefined(tmp_path):
  schema = FrontmatterSchema(
    fields=(FieldSpec('title', required=True),),
    jsonld=JsonLdConfig(context='no-such-context.yaml'),
  )
  spec = _spec(tmp_path, schema)
  _write(spec.dir, 'a', '---\ntitle: A\n---\n')
  report = checks.check_collection(spec, root=tmp_path)
  assert [(issue.level, issue.code) for issue in report.issues] == [
    ('undefined', 'context.unavailable')
  ]
  assert checks.exit_code([report]) == checks.EXIT_UNDEFINED


def test_findings_win_over_undefined(tmp_path):
  schema = FrontmatterSchema(
    fields=(FieldSpec('title', required=True),),
    jsonld=JsonLdConfig(context='missing.yaml'),
  )
  spec = _spec(tmp_path, schema)
  _write(spec.dir, 'bad', '---\nother: 1\n---\n')
  report = checks.check_collection(spec, root=tmp_path)
  levels = {issue.level for issue in report.issues}
  assert levels == {'error', 'undefined'}
  assert checks.exit_code([report]) == checks.EXIT_FINDINGS


def test_issues_are_sorted_deterministically(tmp_path):
  spec = _spec(tmp_path, TITLE_SCHEMA)
  for slug in ('z', 'a', 'm'):
    _write(spec.dir, slug, '---\nother: 1\n---\n')
  first = checks.check_collection(spec, root=tmp_path)
  second = checks.check_collection(spec, root=tmp_path)
  # Each file misses `title` and carries a forbidden key: two findings each.
  assert [issue.slug for issue in first.issues] == [
    'a',
    'a',
    'm',
    'm',
    'z',
    'z',
  ]
  assert first.issues == second.issues


def test_report_to_dict_round_trips_through_json(tmp_path):
  spec = _spec(tmp_path, TITLE_SCHEMA)
  _write(spec.dir, 'a', '---\ntitle: A\n---\n')
  report = checks.check_collection(spec, root=tmp_path)
  assert report.to_dict() == {
    'collection': 'posts',
    'documents': 1,
    'issues': [],
  }
  with pytest.raises(ValueError):
    checks.Issue('bogus', 'x', 'y')


# --- Validators (TODO 6.2) ----------------------------------------------------


def test_check_runs_the_validators_of_the_spec(tmp_path):
  import sys

  from fastapi_blog.validators import Validator

  validator = Validator.from_dict(
    {'name': 'gate', 'argv': [sys.executable, '-c', 'import sys; sys.exit(1)']}
  )
  spec = CollectionSpec(
    name='posts', dir=tmp_path / 'posts', schema=TITLE_SCHEMA
  )
  spec.dir.mkdir()
  (spec.dir / 'a.md').write_text('---\ntitle: A\n---\n', encoding='utf-8')
  spec = CollectionSpec(
    name='posts',
    dir=spec.dir,
    schema=TITLE_SCHEMA,
    validators=(validator,),
  )
  report = checks.check_collection(spec, root=tmp_path)
  assert [(issue.level, issue.code) for issue in report.issues] == [
    ('error', 'validator.gate')
  ]
  assert checks.exit_code([report]) == checks.EXIT_FINDINGS
