"""Integrity diagnostics for multi-locale collections."""

from fastapi_blog import store
from fastapi_blog.checks import check_collection
from fastapi_blog.config import CollectionSpec, load_project
from fastapi_blog.i18n_collections import I18nCollection, I18nConfig
from fastapi_blog.models import FieldSpec, FrontmatterSchema


def _spec(tmp_path, *, structure='multiple_files', check='error'):
  schema = FrontmatterSchema(
    fields=(
      FieldSpec('title', required=True, i18n='translate'),
      FieldSpec('site', i18n='duplicate'),
    )
  )
  return CollectionSpec(
    'articles',
    tmp_path / 'articles',
    schema=schema,
    i18n=I18nConfig(('en', 'ru', 'fr'), 'en', structure=structure),
    check_translations=check,
  )


def test_check_reports_missing_orphan_unknown_and_duplicate_mismatch(tmp_path):
  spec = _spec(tmp_path, structure='multiple_folders')
  spec.dir.mkdir()
  adapter = I18nCollection(spec.to_collection(), spec.i18n)
  adapter.save_entry(
    'hello',
    {
      'en': ({'title': 'Hello', 'site': 'main'}, 'English'),
      'ru': ({'title': 'Привет', 'site': 'mirror'}, 'Russian'),
    },
  )
  orphan_path = adapter.path_for('orphan', 'ru')
  orphan_path.parent.mkdir(parents=True, exist_ok=True)
  store.atomic_write_text(
    orphan_path,
    store.serialize_document({'title': 'Orphan'}, 'No canonical'),
  )
  unknown_path = spec.dir / 'de' / 'unknown.md'
  unknown_path.parent.mkdir(parents=True)
  store.atomic_write_text(
    unknown_path,
    store.serialize_document({'title': 'Unknown'}, 'Unknown locale'),
  )

  report = check_collection(spec, root=tmp_path)
  issues = {(item.code, item.slug, item.field) for item in report.issues}
  assert report.documents == 1
  assert ('translation.missing', 'hello', 'fr') in issues
  assert ('translation.orphan', 'orphan', 'ru') in issues
  assert ('translation.unknown_locale', 'unknown', 'de') in issues
  assert ('translation.duplicate_mismatch', 'hello', 'site') in issues
  missing = next(
    issue for issue in report.issues if issue.code == 'translation.missing'
  )
  assert missing.level == 'error'


def test_translation_missing_severity_can_be_disabled(tmp_path):
  spec = _spec(tmp_path, check='off')
  spec.dir.mkdir()
  I18nCollection(spec.to_collection(), spec.i18n).save_entry(
    'hello', {'en': ({'title': 'Hello'}, 'English')}
  )
  report = check_collection(spec, root=tmp_path)
  assert not any(issue.code == 'translation.missing' for issue in report.issues)


def test_multiple_files_orphan_is_found(tmp_path):
  spec = _spec(tmp_path, structure='multiple_files')
  spec.dir.mkdir()
  orphan_path = spec.dir / 'orphan.ru.md'
  store.atomic_write_text(
    orphan_path,
    store.serialize_document({'title': 'Orphan'}, 'No canonical'),
  )
  report = check_collection(spec, root=tmp_path)
  assert any(
    issue.code == 'translation.orphan' and issue.slug == 'orphan'
    for issue in report.issues
  )


def test_check_translations_option_is_parsed_from_project(tmp_path):
  (tmp_path / 'articles').mkdir()
  project_file = tmp_path / 'fastapi_blog.yaml'
  project_file.write_text(
    """collections:
  articles:
    dir: articles
    i18n:
      locales: [en, ru]
      default_locale: en
    check:
      translations: warn
""",
    encoding='utf-8',
  )
  project = load_project(project_file)
  assert project.collections['articles'].check_translations == 'warn'
