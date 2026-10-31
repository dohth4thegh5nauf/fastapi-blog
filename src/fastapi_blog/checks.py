"""Integrity checks of a collection (TODO 6.1, first slice).

`check_collection` reads every document of a collection and reports what is
wrong as a list of `Issue` objects:

- `file.malformed` (error): a file can't be parsed;
- `schema.invalid` / `schema.missing` / `schema.extra` (error): the
  frontmatter doesn't match the schema;
- `context.lost_term` (warning): a schema key the JSON-LD context doesn't
  cover, so expansion would silently drop it (TODO 5.6);
- `collection.directory_missing` / `context.unavailable` (undefined):
  something could not be checked — never reported as fine (П4).

The report is deterministic: issues are sorted, no times or absolute paths.
Optional link/media integrity checks, JSON-LD context coverage and external
validators share the same `Issue` model and exit-code rules.
"""

import dataclasses
import json
import pathlib
import urllib.parse
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from . import jsonld, store
from .config import CollectionSpec
from .issues import Issue
from .validators import run_validator


# Exit codes of `python -m fastapi_blog check` (TODO 6.1).
EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_UNDEFINED = 2
EXIT_USAGE = 64


@dataclasses.dataclass
class Report:
  """The result of checking one collection.

  Attributes:
      collection: Collection name.
      documents: How many document files were found.
      issues: The findings, sorted.

  """

  collection: str
  documents: int = 0
  issues: list[Issue] = dataclasses.field(default_factory=list)
  summaries: dict[str, str] = dataclasses.field(default_factory=dict)

  def count(self, level: str) -> int:
    """Return how many issues have this level."""
    return sum(1 for issue in self.issues if issue.level == level)

  def to_dict(self) -> dict[str, Any]:
    """Return the report as a plain dict (for `--json`)."""
    return {
      'collection': self.collection,
      'documents': self.documents,
      'issues': [issue.to_dict() for issue in self.issues],
    }


def exit_code(reports: list[Report], fail_on: str = 'error') -> int:
  """Return the exit code for a set of reports.

  A finding at or above `fail_on` gives 1. Without findings, anything that
  couldn't be checked gives 2. Otherwise 0. A finding always wins over
  `undefined`, and `undefined` is never turned into 0.

  Args:
      reports: The reports.
      fail_on: `error` (only errors are findings) or `warning` (warnings too).

  Returns:
      0, 1 or 2.

  """
  failing = ('error',) if fail_on == 'error' else ('error', 'warning')
  issues = [issue for report in reports for issue in report.issues]
  if any(issue.level in failing for issue in issues):
    return EXIT_FINDINGS
  if any(issue.level == 'undefined' for issue in issues):
    return EXIT_UNDEFINED
  return EXIT_CLEAN


def _schema_code(kind: str) -> str:
  if kind == 'missing':
    return 'schema.missing'
  if kind == 'extra_forbidden':
    return 'schema.extra'
  return 'schema.invalid'


def _check_documents(
  spec: CollectionSpec, documents: store.DocumentStore, issues: list[Issue]
) -> None:
  schema = spec.schema
  model = schema.model() if schema is not None else None
  for slug in sorted(documents.list()):
    try:
      record = documents.read(slug)
    except store.ParseError as exc:
      issues.append(Issue('error', 'file.malformed', str(exc), slug))
      continue
    if model is None:
      continue
    try:
      model.model_validate(record.frontmatter)
    except ValidationError as exc:
      for error in exc.errors():
        field = '.'.join(str(part) for part in error['loc']) or None
        issues.append(
          Issue(
            'error',
            _schema_code(error['type']),
            str(error['msg']).removeprefix('Value error, '),
            slug,
            field,
          )
        )


def _check_context(spec: CollectionSpec, root: pathlib.Path, issues: list):
  schema = spec.schema
  if schema is None or schema.jsonld is None:
    return
  try:
    missing = jsonld.uncovered_keys(schema, project_root=root)
  except jsonld.ContextUnavailableError as exc:
    issues.append(Issue('undefined', 'context.unavailable', str(exc)))
  except jsonld.JsonLdError as exc:
    issues.append(Issue('error', 'context.invalid', str(exc)))
  else:
    for key in missing:
      issues.append(
        Issue(
          'warning',
          'context.lost_term',
          f'Key {key!r} is not defined by the context, '
          'so JSON-LD would drop it',
          None,
          key,
        )
      )


def _relative_document_path(
  spec: CollectionSpec,
  root: pathlib.Path,
  slug: str,
  documents: store.DocumentStore,
) -> pathlib.Path:
  """Return the document's path relative to the project root (for `{path}`)."""
  path = documents.path_for(slug)
  if path is None:
    return spec.dir / f'{slug}.md'
  try:
    return path.resolve().relative_to(root.resolve())
  except ValueError:
    return path


def _check_validators(
  spec: CollectionSpec, root: pathlib.Path, issues: list[Issue]
) -> None:
  if not spec.validators:
    return
  documents = store.DocumentStore(spec.to_collection())
  for slug in sorted(documents.list()):
    try:
      record = documents.read(slug)
    except (store.ParseError, store.NotFoundError):
      # Unparseable files are already findings; validators need parsed input.
      continue
    path = _relative_document_path(spec, root, slug, documents)
    for validator in spec.validators:
      issues.extend(
        run_validator(
          validator,
          collection_name=spec.name,
          slug=slug,
          path=path,
          frontmatter=record.frontmatter,
          cwd=root,
        )
      )


def _check_unique(
  spec: CollectionSpec,
  documents: store.DocumentStore,
  issues: list[Issue],
) -> None:
  """Report duplicate configured field values and sequence numbers."""
  if not spec.unique:
    return
  seen: dict[str, dict[str, str]] = {name: {} for name in spec.unique}
  seq_regex = spec.slug_template.slug_regex() if spec.slug_template else None
  for slug in sorted(documents.list()):
    try:
      record = documents.read(slug)
    except (store.ParseError, store.NotFoundError):
      continue
    for name in spec.unique:
      if name == 'seq':
        match = seq_regex.fullmatch(slug) if seq_regex else None
        value = (
          match.group('seq') if match and 'seq' in match.groupdict() else None
        )
        if value is None:
          issues.append(
            Issue(
              'error',
              'unique.sequence_missing',
              'Slug does not match the configured sequence template',
              slug,
              'seq',
            )
          )
          continue
      else:
        field = spec.schema.get(name) if spec.schema else None
        key = field.key if field else name
        value = record.frontmatter.get(key)
      if value is None or value == '':
        continue
      # Canonical JSON representation makes lists/maps comparable without
      # relying on insertion order.
      marker = json.dumps(
        value, sort_keys=True, ensure_ascii=False, default=str
      )
      previous = seen[name].get(marker)
      if previous is not None:
        issues.append(
          Issue(
            'error',
            'unique.duplicate',
            f'Value {value!r} of {name!r} is also used by {previous!r}',
            slug,
            name,
          )
        )
      else:
        seen[name][marker] = slug


def _target_field(spec: CollectionSpec, field_name: str):
  schema = spec.schema
  if schema is None:
    return None
  field = schema.get(field_name)
  if field is not None:
    return field
  return next((item for item in schema.fields if item.key == field_name), None)


def _link_values(value: Any) -> list[str]:
  if value is None or value == '':
    return []
  values = value if isinstance(value, list) else [value]
  return [str(item) for item in values if item is not None and str(item)]


def _link_index(
  spec: CollectionSpec,
  documents: store.DocumentStore,
  value_field: str | None = None,
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
  """Build value -> slug and slug -> frontmatter indexes for a target."""
  by_value: dict[str, str] = {}
  records: dict[str, dict[str, Any]] = {}
  schema = spec.schema
  id_field = (
    _target_field(spec, value_field)
    if value_field
    else (
      next((field for field in schema.fields if field.key == '@id'), None)
      if schema
      else None
    )
  )
  for slug in sorted(documents.list()):
    try:
      record = documents.read(slug)
    except (store.ParseError, store.NotFoundError):
      continue
    records[slug] = record.frontmatter
    value = record.frontmatter.get(id_field.key) if id_field else slug
    if value is not None:
      by_value[str(value)] = slug
    # Slugs are always valid link targets, even when @id is configured.
    by_value.setdefault(slug, slug)
  return by_value, records


def _check_links(
  spec: CollectionSpec,
  documents: store.DocumentStore,
  issues: list[Issue],
  collections: Mapping[str, CollectionSpec],
) -> None:
  if spec.check_links == 'off' or spec.schema is None:
    return
  level = 'warning' if spec.check_links == 'warn' else 'error'
  indexes: dict[str, tuple[dict[str, str], dict[str, dict[str, Any]]]] = {}
  for slug in sorted(documents.list()):
    try:
      record = documents.read(slug)
    except (store.ParseError, store.NotFoundError):
      continue
    for field in spec.schema.fields:
      if not field.is_link:
        continue
      target_name = field.collection or spec.name
      target_spec = collections.get(target_name)
      if target_spec is None:
        issues.append(
          Issue(
            'undefined',
            'link.collection_unavailable',
            f'Target collection {target_name!r} is not available',
            slug,
            field.name,
          )
        )
        continue
      target_field = (
        _target_field(target_spec, field.value_field)
        if field.value_field
        else None
      )
      if field.value_field and target_field is None:
        issues.append(
          Issue(
            'undefined',
            'link.value_field_unavailable',
            f'Target field {field.value_field!r} is not defined in '
            f'collection {target_name!r}',
            slug,
            field.name,
          )
        )
        continue
      # The default is @id when present, otherwise the target slug.
      index_key = field.value_field or '@id'
      cache_key = f'{target_name}:{index_key}'
      if cache_key not in indexes:
        target_store = store.DocumentStore(target_spec.to_collection())
        indexes[cache_key] = _link_index(
          target_spec, target_store, field.value_field
        )
      by_value, target_records = indexes[cache_key]
      for link in _link_values(record.frontmatter.get(field.key)):
        target_slug = by_value.get(link)
        if target_slug is None:
          parsed = urllib.parse.urlsplit(link)
          # Only skip an IRI when it did not resolve as a local @id/value.
          # This permits compact IDs such as `note:0007` when they are
          # explicitly present in the target collection.
          if parsed.scheme or link.startswith('//'):
            continue
          issues.append(
            Issue(
              level,
              'link.target_missing',
              f'Link target {link!r} does not exist in collection '
              f'{target_name!r}',
              slug,
              field.name,
            )
          )
          continue
        if field.filters:
          target_frontmatter = target_records[target_slug]
          failed = []
          for rule in field.filters:
            filter_field = _target_field(target_spec, rule['field'])
            filter_key = filter_field.key if filter_field else rule['field']
            if target_frontmatter.get(filter_key) not in rule['values']:
              failed.append(rule['field'])
          if failed:
            issues.append(
              Issue(
                level,
                'link.target_filtered',
                f'Link target {link!r} does not satisfy filter(s): '
                f'{", ".join(failed)}',
                slug,
                field.name,
              )
            )


def _check_files(
  spec: CollectionSpec,
  documents: store.DocumentStore,
  root: pathlib.Path,
  issues: list[Issue],
) -> None:
  if spec.check_files == 'off' or spec.schema is None:
    return
  level = 'warning' if spec.check_files == 'warn' else 'error'
  for slug in sorted(documents.list()):
    try:
      record = documents.read(slug)
    except (store.ParseError, store.NotFoundError):
      continue
    for field in spec.schema.fields:
      if field.type not in ('file', 'image'):
        continue
      value = record.frontmatter.get(field.key)
      if value is None or value == '':
        continue
      if not field.media_dir:
        issues.append(
          Issue(
            'undefined',
            'file.media_dir_unavailable',
            'Cannot check this field because it has no `media_dir`',
            slug,
            field.name,
          )
        )
        continue
      values = value if isinstance(value, list) else [value]
      project_root = root.resolve()
      media_dir = (project_root / field.media_dir).resolve()
      try:
        media_dir.relative_to(project_root)
      except ValueError:
        issues.append(
          Issue(
            level,
            'file.media_dir_unsafe',
            f'media_dir {field.media_dir!r} resolves outside the project root',
            slug,
            field.name,
          )
        )
        continue
      public_path = (field.public_path or field.media_dir).strip('/')
      for item in values:
        if not isinstance(item, str) or not item:
          continue
        parsed = urllib.parse.urlsplit(item)
        if parsed.scheme in ('http', 'https') or item.startswith('//'):
          continue
        public_value = urllib.parse.unquote(parsed.path).lstrip('/')
        if public_path:
          if public_value == public_path:
            relative = ''
          elif public_value.startswith(public_path + '/'):
            relative = public_value[len(public_path) + 1 :]
          else:
            issues.append(
              Issue(
                level,
                'file.public_path_mismatch',
                f'Path {item!r} is outside public_path {public_path!r}',
                slug,
                field.name,
              )
            )
            continue
        else:
          relative = public_value
        candidate = (media_dir / relative).resolve()
        try:
          candidate.relative_to(media_dir)
        except ValueError:
          issues.append(
            Issue(
              level,
              'file.path_unsafe',
              f'Path {item!r} escapes media_dir {field.media_dir!r}',
              slug,
              field.name,
            )
          )
          continue
        if not candidate.is_file():
          issues.append(
            Issue(
              level,
              'file.missing',
              f'File {item!r} does not exist in media_dir {field.media_dir!r}',
              slug,
              field.name,
            )
          )


def check_collection(
  spec: CollectionSpec,
  *,
  root: str | pathlib.Path | None = None,
  collections: Mapping[str, CollectionSpec] | None = None,
) -> Report:
  """Check one collection: parsing, schema, uniqueness, links, files, context.

  Args:
      spec: The collection to check.
      root: Project root, where context files are looked up (default: the
          current directory).
      collections: All collections of the project, keyed by name, used to
          resolve `link` fields that point at another collection.

  Returns:
      The report (deterministically sorted issues).

  """
  base = pathlib.Path.cwd() if root is None else pathlib.Path(root)
  report = Report(spec.name)
  issues = report.issues
  if not spec.dir.is_dir():
    issues.append(
      Issue(
        'undefined',
        'collection.directory_missing',
        f'The directory of collection {spec.name!r} does not exist, '
        'so nothing was checked',
      )
    )
    return report
  documents = store.DocumentStore(spec.to_collection())
  report.documents = len(documents.list())
  has_title = bool(spec.schema and spec.schema.field_for_role('title'))
  if spec.summary is not None or has_title:
    for slug in sorted(documents.list()):
      try:
        record = documents.read(slug)
      except (store.ParseError, store.NotFoundError):
        continue
      report.summaries[slug] = spec.summarize(slug, record.frontmatter)
  _check_documents(spec, documents, issues)
  _check_unique(spec, documents, issues)
  _check_links(spec, documents, issues, collections or {spec.name: spec})
  _check_files(spec, documents, base, issues)
  _check_context(spec, base, issues)
  _check_validators(spec, base, issues)
  issues.sort(key=Issue.sort_key)
  return report
