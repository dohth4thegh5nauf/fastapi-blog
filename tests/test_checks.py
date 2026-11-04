"""Tests for `check_collection` and the exit-code rules (TODO 6.1)."""

import pytest

from fastapi_blog import checks, jsonld
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


def test_lost_context_terms_are_errors_by_default(tmp_path):
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
    ('error', 'context.lost_term')
  ]
  assert report.issues[0].field == 'ex:state'
  assert checks.exit_code([report]) == checks.EXIT_FINDINGS


def test_lost_context_terms_follow_strict_context_warn(tmp_path):
  schema = FrontmatterSchema(
    fields=(
      FieldSpec('title', required=True),
      FieldSpec('state', alias='ex:state'),
    ),
    jsonld=JsonLdConfig(
      context={'title': 'https://example.org/title'}, strict_context='warn'
    ),
  )
  spec = _spec(tmp_path, schema)
  _write(spec.dir, 'a', '---\ntitle: A\nex:state: active\n---\n')
  report = checks.check_collection(spec, root=tmp_path)
  assert [(issue.level, issue.code) for issue in report.issues] == [
    ('warning', 'context.lost_term')
  ]
  # A warning doesn't fail `--fail-on error`, but fails `--fail-on warning`.
  assert checks.exit_code([report], 'error') == checks.EXIT_CLEAN
  assert checks.exit_code([report], 'warning') == checks.EXIT_FINDINGS


def test_strict_context_off_skips_the_coverage_check(tmp_path):
  schema = FrontmatterSchema(
    fields=(
      FieldSpec('title', required=True),
      FieldSpec('state', alias='ex:state'),
    ),
    jsonld=JsonLdConfig(
      context={'title': 'https://example.org/title'}, strict_context='off'
    ),
  )
  spec = _spec(tmp_path, schema)
  _write(spec.dir, 'a', '---\ntitle: A\nex:state: active\n---\n')
  assert checks.check_collection(spec, root=tmp_path).issues == []


def test_strict_context_off_skips_even_an_unloadable_context(tmp_path):
  schema = FrontmatterSchema(
    fields=(FieldSpec('title', required=True),),
    jsonld=JsonLdConfig(context='no-such-context.yaml', strict_context='off'),
  )
  spec = _spec(tmp_path, schema)
  _write(spec.dir, 'a', '---\ntitle: A\n---\n')
  assert checks.check_collection(spec, root=tmp_path).issues == []


def test_strict_context_rejects_an_unknown_level():
  with pytest.raises(ValueError, match='strict_context'):
    JsonLdConfig(strict_context='loud')


@pytest.mark.skipif(
  not jsonld.pyld_available(), reason='needs the jsonld extra'
)
def test_probe_expansion_decides_lost_keys_when_pyld_is_available(tmp_path):
  schema = FrontmatterSchema(
    fields=(
      FieldSpec('title', required=True),
      FieldSpec('state', alias='ex:state'),
    ),
    jsonld=JsonLdConfig(
      context={'title': 'https://example.org/title'}, content_term='text'
    ),
  )
  spec = _spec(tmp_path, schema)
  _write(spec.dir, 'a', '---\ntitle: A\nex:state: active\n---\nBody\n')
  report = checks.check_collection(spec, root=tmp_path)
  # `ex:state` and the `content_term` survive neither the static reading
  # nor the probe; `title` is covered by the context term.
  assert [issue.field for issue in report.issues] == ['ex:state', 'text']
  assert {issue.code for issue in report.issues} == {'context.lost_term'}


def test_static_check_is_the_fallback_without_pyld(tmp_path, monkeypatch):
  monkeypatch.setattr(jsonld, 'pyld_available', lambda: False)
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
    ('error', 'context.lost_term')
  ]


def test_an_invalid_context_from_the_probe_is_an_error(tmp_path, monkeypatch):
  def _raise(schema, **kwargs):
    raise jsonld.JsonLdError('bad context')

  monkeypatch.setattr(jsonld, 'pyld_available', lambda: True)
  monkeypatch.setattr(jsonld, 'probe_lost_keys', _raise)
  schema = FrontmatterSchema(
    fields=(FieldSpec('title', required=True),),
    jsonld=JsonLdConfig(context={'title': 'https://example.org/title'}),
  )
  spec = _spec(tmp_path, schema)
  _write(spec.dir, 'a', '---\ntitle: A\n---\n')
  report = checks.check_collection(spec, root=tmp_path)
  assert [(issue.level, issue.code) for issue in report.issues] == [
    ('error', 'context.invalid')
  ]


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


def test_check_reports_duplicate_unique_fields_and_sequence(tmp_path):
  spec = _spec(tmp_path, TITLE_SCHEMA)
  spec = CollectionSpec(
    name=spec.name,
    dir=spec.dir,
    schema=TITLE_SCHEMA,
    slug_template=__import__(
      'fastapi_blog.templates', fromlist=['parse_template']
    ).parse_template(
      '{seq|pad(4)}-{title_slug}',
      ('seq', 'title_slug'),
      {'title'},
    ),
    unique=('seq', 'title'),
  )
  _write(spec.dir, '0001-a', '---\ntitle: Same\n---\n')
  _write(spec.dir, '0001-b', '---\ntitle: Same\n---\n')
  report = checks.check_collection(spec, root=tmp_path)
  assert (
    len([issue for issue in report.issues if issue.code == 'unique.duplicate'])
    == 2
  )


# --- SEO integrity checks (TODO 5.9.7) --------------------------------------


def test_seo_check_reports_length_missing_and_invalid_values(tmp_path):
  from fastapi_blog.models import SeoCheckConfig, SeoConfig

  schema = FrontmatterSchema(
    fields=(
      FieldSpec('title', role='title'),
      FieldSpec('description', role='description'),
      FieldSpec('canonical', role='canonical'),
      FieldSpec('robots', type='list[str]', role='robots'),
      FieldSpec('image', role='image'),
      FieldSpec('image_alt', role='image_alt'),
    ),
    seo=SeoConfig(check=SeoCheckConfig(title_max=5, description_max=7)),
  )
  spec = _spec(tmp_path, schema)
  _write(
    spec.dir,
    'one',
    '---\ntitle: A very long title\ndescription: too long description\n'
    'canonical: javascript:alert(1)\nrobots: [unknown]\nimage: /missing.png\n---\n',
  )
  report = checks.check_collection(spec, root=tmp_path)
  assert {(issue.level, issue.code) for issue in report.issues} == {
    ('warning', 'seo.title_too_long'),
    ('warning', 'seo.description_too_long'),
    ('error', 'seo.canonical_invalid'),
    ('error', 'seo.robots_invalid'),
    ('error', 'seo.image_alt_required'),
  }


def test_seo_check_reports_duplicates_and_respects_levels(tmp_path):
  from fastapi_blog.models import SeoCheckConfig, SeoConfig

  schema = FrontmatterSchema(
    fields=(
      FieldSpec('title', role='title'),
      FieldSpec('description', role='description'),
    ),
    seo=SeoConfig(
      check=SeoCheckConfig(
        title_max=100,
        description_max=200,
        missing_description='off',
        duplicate_title='error',
        duplicate_description='warn',
      )
    ),
  )
  spec = _spec(tmp_path, schema)
  _write(spec.dir, 'a', '---\ntitle: Same\ndescription: Shared\n---\n')
  _write(spec.dir, 'b', '---\ntitle: Same\ndescription: Shared\n---\n')
  report = checks.check_collection(spec, root=tmp_path)
  assert [(issue.level, issue.code, issue.slug) for issue in report.issues] == [
    ('error', 'seo.duplicate_title', 'b'),
    ('warning', 'seo.duplicate_description', 'b'),
  ]


def test_seo_check_reports_redirect_collisions_chains_and_loops(tmp_path):
  from fastapi_blog.models import SeoConfig

  schema = FrontmatterSchema(
    fields=(
      FieldSpec('canonical', role='canonical'),
      FieldSpec('redirect_from', type='list[str]', role='redirect_from'),
    ),
    seo=SeoConfig(),
  )
  spec = _spec(tmp_path, schema)
  _write(
    spec.dir,
    'live',
    '---\nredirect_from: [legacy, /posts/current, //evil.example, '
    '../escape, https://evil.example/x]\n---\n',
  )
  _write(spec.dir, 'current', '---\nredirect_from: [legacy]\n---\n')
  # The canonical destinations form a two-node redirect cycle.
  _write(
    spec.dir,
    'cycle-a',
    '---\ncanonical: /posts/old-b\nredirect_from: [old-a]\n---\n',
  )
  _write(
    spec.dir,
    'cycle-b',
    '---\ncanonical: /posts/old-a\nredirect_from: [old-b]\n---\n',
  )
  report = checks.check_collection(spec, root=tmp_path)
  codes = [issue.code for issue in report.issues]
  assert 'seo.redirect_from_duplicate' in codes
  assert 'seo.redirect_from_live_conflict' in codes
  assert 'seo.redirect_from_chain' in codes
  assert 'seo.redirect_from_loop' in codes
  assert 'seo.redirect_from_invalid' in codes


def test_seo_check_reports_malformed_urls_without_crashing(tmp_path):
  from fastapi_blog.models import SeoConfig

  schema = FrontmatterSchema(
    fields=(
      FieldSpec('canonical', role='canonical'),
      FieldSpec('redirect_from', type='list[str]', role='redirect_from'),
    ),
    seo=SeoConfig(),
  )
  spec = _spec(tmp_path, schema)
  _write(
    spec.dir,
    'malformed',
    "---\ncanonical: 'https://['\nredirect_from: ['https://[', 'a//b']\n---\n",
  )

  report = checks.check_collection(spec, root=tmp_path)

  assert 'seo.canonical_invalid' in [issue.code for issue in report.issues]
  assert 'seo.redirect_from_invalid' in [issue.code for issue in report.issues]


def test_i18n_check_reports_missing_orphan_unknown_and_duplicate(tmp_path):
  from fastapi_blog.i18n_collections import I18nConfig

  spec = _spec(
    tmp_path,
    FrontmatterSchema(
      fields=(
        FieldSpec('title', required=True, i18n='translate'),
        FieldSpec('status', i18n='duplicate'),
      )
    ),
  )
  spec = __import__('dataclasses').replace(
    spec,
    i18n=I18nConfig(('en', 'ru'), 'en', translate_body=True),
    check_translations='warn',
  )
  _write(
    spec.dir,
    'hello',
    '---\ntitle: Hello\nstatus: accepted\n---\nEnglish\n',
  )
  (spec.dir / 'hello.ru.md').write_text(
    '---\ntitle: Привет\nstatus: proposed\n---\nРусский\n',
    encoding='utf-8',
  )
  (spec.dir / 'orphan.ru.md').write_text(
    '---\ntitle: Orphan\n---\n', encoding='utf-8'
  )
  (spec.dir / 'foreign.de.md').write_text(
    '---\ntitle: Foreign\n---\n', encoding='utf-8'
  )
  report = checks.check_collection(spec, root=tmp_path)
  codes = [issue.code for issue in report.issues]
  assert report.documents == 1
  assert 'translation.duplicate_mismatch' in codes
  assert 'translation.orphan' in codes
  assert 'translation.unknown_locale' in codes
  assert 'translation.missing' not in codes


def test_i18n_check_reports_missing_translation_by_configured_level(tmp_path):
  from dataclasses import replace

  from fastapi_blog.i18n_collections import I18nConfig

  spec = _spec(
    tmp_path,
    FrontmatterSchema(fields=(FieldSpec('title', required=True),)),
  )
  spec = replace(
    spec,
    i18n=I18nConfig(('en', 'ru'), 'en'),
    check_translations='error',
  )
  _write(spec.dir, 'hello', '---\ntitle: Hello\n---\nBody\n')
  report = checks.check_collection(spec, root=tmp_path)
  assert [(issue.level, issue.code) for issue in report.issues] == [
    ('error', 'translation.missing')
  ]


def test_i18n_check_supports_multiple_folders(tmp_path):
  from dataclasses import replace

  from fastapi_blog.i18n_collections import I18nConfig

  spec = _spec(
    tmp_path,
    FrontmatterSchema(fields=(FieldSpec('title', required=True),)),
  )
  spec = replace(
    spec,
    i18n=I18nConfig(('en', 'ru'), 'en', structure='multiple_folders'),
    check_translations='warn',
  )
  (spec.dir / 'en').mkdir()
  _write(spec.dir / 'en', 'hello', '---\ntitle: Hello\n---\n')
  report = checks.check_collection(spec, root=tmp_path)
  assert report.documents == 1
  assert [(issue.level, issue.code) for issue in report.issues] == [
    ('warning', 'translation.missing')
  ]


def test_i18n_check_supports_default_locale_at_root(tmp_path):
  from dataclasses import replace

  from fastapi_blog.i18n_collections import I18nConfig

  spec = _spec(
    tmp_path,
    FrontmatterSchema(fields=(FieldSpec('title', required=True),)),
  )
  spec = replace(
    spec,
    i18n=I18nConfig(
      ('en', 'ru'),
      'en',
      structure='multiple_folders',
      default_locale_in_root=True,
    ),
    check_translations='error',
  )
  _write(spec.dir, 'hello', '---\ntitle: Hello\n---\nEnglish\n')
  (spec.dir / 'ru').mkdir()
  _write(spec.dir / 'ru', 'hello', '---\ntitle: Привет\n---\nРусский\n')
  report = checks.check_collection(spec, root=tmp_path)
  assert report.documents == 1
  assert report.issues == []
