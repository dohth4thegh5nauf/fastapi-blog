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
Link checks, external validators, slug numbering and `check` config options
(TODO 6.1/6.2/6.4) come on top of this base.
"""

import dataclasses
import pathlib
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


def check_collection(
  spec: CollectionSpec, *, root: str | pathlib.Path | None = None
) -> Report:
  """Check one collection: parsing, schema match, context coverage.

  Args:
      spec: The collection to check.
      root: Project root, where context files are looked up (default: the
          current directory).

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
  _check_documents(spec, documents, issues)
  _check_context(spec, base, issues)
  _check_validators(spec, base, issues)
  issues.sort(key=Issue.sort_key)
  return report
