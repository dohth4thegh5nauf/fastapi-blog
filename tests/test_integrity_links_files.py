"""Integrity checks for links and media paths (TODO 6.1)."""

import pytest

from fastapi_blog import checks, config, store


def _write(path, text):
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(text, encoding='utf-8')


def _project(tmp_path, yaml_text):
  _write(tmp_path / 'fastapi_blog.yaml', yaml_text)
  return config.load_project(tmp_path / 'fastapi_blog.yaml')


def _doc(spec, slug, **fields):
  documents = store.DocumentStore(spec.to_collection())
  documents.write(slug, fields, '')


def test_check_links_resolves_slug_and_custom_value_and_filters(tmp_path):
  _write(
    tmp_path / 'fastapi_blog.yaml',
    """collections:
  notes:
    dir: notes
    schema: notes.yaml
  pages:
    dir: pages
    schema: pages.yaml
    check: {links: error}
""",
  )
  _write(
    tmp_path / 'notes.yaml',
    """fields:
  title: {role: title}
  identifier: {alias: "@id"}
  state: {type: str}
""",
  )
  _write(
    tmp_path / 'pages.yaml',
    """fields:
  related: {type: "list[link]", collection: notes, value_field: identifier,
            filters: [{field: state, values: [active]}]}
""",
  )
  # Reload after schemas have been written.
  project = config.load_project(tmp_path / 'fastapi_blog.yaml')
  _doc(
    project.collections['notes'],
    'one',
    title='One',
    **{'@id': 'note:one', 'state': 'active'},
  )
  _doc(
    project.collections['notes'],
    'two',
    title='Two',
    **{'@id': 'note:two', 'state': 'draft'},
  )
  _doc(
    project.collections['pages'],
    'page',
    related=['note:one', 'note:two', 'missing'],
  )

  report = checks.check_collection(
    project.collections['pages'],
    root=project.root,
    collections=project.collections,
  )
  assert [(issue.code, issue.field) for issue in report.issues] == [
    ('link.target_filtered', 'related'),
    ('link.target_missing', 'related'),
  ]


def test_check_links_defaults_to_slug_and_skips_external_iris(tmp_path):
  _write(
    tmp_path / 'fastapi_blog.yaml',
    """collections:
  notes:
    dir: notes
    schema: notes.yaml
    check: {links: warn}
""",
  )
  _write(tmp_path / 'notes.yaml', 'fields:\n  related: {type: "list[link]"}\n')
  project = config.load_project(tmp_path / 'fastapi_blog.yaml')
  _doc(project.collections['notes'], 'target')
  _doc(
    project.collections['notes'],
    'source',
    related=['target', 'https://example.org/x', 'missing'],
  )
  report = checks.check_collection(
    project.collections['notes'],
    root=project.root,
    collections=project.collections,
  )
  assert [(issue.level, issue.code) for issue in report.issues] == [
    ('warning', 'link.target_missing'),
  ]


def test_check_files_maps_public_path_to_media_dir(tmp_path):
  _write(
    tmp_path / 'fastapi_blog.yaml',
    """collections:
  notes:
    dir: notes
    schema: notes.yaml
    check: {files: error}
""",
  )
  _write(
    tmp_path / 'notes.yaml',
    """fields:
  cover: {type: image, media_dir: uploads, public_path: /media}
""",
  )
  project = config.load_project(tmp_path / 'fastapi_blog.yaml')
  _write(tmp_path / 'uploads' / 'exists.png', 'image')
  _doc(
    project.collections['notes'],
    'source',
    cover='/media/exists.png',
  )
  report = checks.check_collection(
    project.collections['notes'],
    root=project.root,
    collections=project.collections,
  )
  assert report.issues == []


def test_check_files_reports_missing_and_rejects_traversal(tmp_path):
  _write(
    tmp_path / 'fastapi_blog.yaml',
    """collections:
  notes:
    dir: notes
    schema: notes.yaml
    check: {files: warn}
""",
  )
  _write(
    tmp_path / 'notes.yaml',
    """fields:
  attachment: {type: file, media_dir: uploads}
""",
  )
  project = config.load_project(tmp_path / 'fastapi_blog.yaml')
  _doc(
    project.collections['notes'],
    'missing',
    attachment='uploads/missing.pdf',
  )
  _doc(
    project.collections['notes'],
    'unsafe',
    attachment='uploads/../../secret.txt',
  )
  report = checks.check_collection(
    project.collections['notes'],
    root=project.root,
    collections=project.collections,
  )
  assert [(issue.level, issue.code) for issue in report.issues] == [
    ('warning', 'file.missing'),
    ('warning', 'file.path_unsafe'),
  ]


@pytest.mark.parametrize('level', ['broken', 'true', 1])
def test_project_rejects_invalid_integrity_level(tmp_path, level):
  _write(
    tmp_path / 'fastapi_blog.yaml',
    f'collections:\n  notes:\n    dir: notes\n    check: {{links: {level}}}\n',
  )
  with pytest.raises(config.ConfigError, match='check.links'):
    config.load_project(tmp_path / 'fastapi_blog.yaml')


def test_project_rejects_unknown_link_collection(tmp_path):
  _write(
    tmp_path / 'notes.yaml',
    'fields:\n  ref: {type: link, collection: absent}\n',
  )
  _write(
    tmp_path / 'fastapi_blog.yaml',
    'collections:\n  notes:\n    dir: notes\n    schema: notes.yaml\n',
  )
  with pytest.raises(config.ConfigError, match='target collection'):
    config.load_project(tmp_path / 'fastapi_blog.yaml')


def test_check_files_is_undefined_without_media_dir(tmp_path):
  _write(
    tmp_path / 'fastapi_blog.yaml',
    """collections:
  notes:
    dir: notes
    schema: notes.yaml
    check: {files: error}
""",
  )
  _write(
    tmp_path / 'notes.yaml',
    """fields:
  attachment: {type: file}
""",
  )
  project = config.load_project(tmp_path / 'fastapi_blog.yaml')
  _doc(project.collections['notes'], 'source', attachment='files/report.pdf')
  report = checks.check_collection(
    project.collections['notes'],
    root=project.root,
    collections=project.collections,
  )
  assert [(issue.level, issue.code) for issue in report.issues] == [
    ('undefined', 'file.media_dir_unavailable'),
  ]


def test_check_files_rejects_media_dir_symlink_outside_project(tmp_path):
  project_root = tmp_path / 'project'
  outside = tmp_path / 'outside'
  outside.mkdir()
  _write(outside / 'secret.txt', 'secret')
  project_root.mkdir()
  (project_root / 'uploads').symlink_to(outside, target_is_directory=True)
  _write(
    project_root / 'fastapi_blog.yaml',
    """collections:
  notes:
    dir: notes
    schema: notes.yaml
    check: {files: error}
""",
  )
  _write(
    project_root / 'notes.yaml',
    """fields:
  attachment: {type: file, media_dir: uploads}
""",
  )
  project = config.load_project(project_root / 'fastapi_blog.yaml')
  _doc(
    project.collections['notes'],
    'source',
    attachment='uploads/secret.txt',
  )
  report = checks.check_collection(
    project.collections['notes'],
    root=project.root,
    collections=project.collections,
  )
  assert [(issue.level, issue.code) for issue in report.issues] == [
    ('error', 'file.media_dir_unsafe'),
  ]
