"""Command-line interface: `python -m fastapi_blog <command>`.

Commands:

- `check`: integrity checks of the collections (exit codes 0, 1, 2, 64);
- `export`: JSON-LD of a collection (`jsonld`, and with the `jsonld` extra
  `expanded` and `nquads`);
- `schema --json-schema`: JSON Schema of the frontmatter.

The collections come from the project file (`fastapi_blog.yaml`, see
`fastapi_blog.config`), from explicit flags or from the built-in defaults,
in this order of precedence: a CLI flag beats the project file, the project
file beats the defaults. Operates directly on the filesystem — it never
starts a FastAPI app.
"""

import argparse
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any

from . import checks, config, store
from . import jsonld as jsonld_module
from .config import CollectionSpec, ConfigError
from .models import DEFAULT_SCHEMA, FrontmatterSchema


# Exit codes, per TODO 6.1: 0 clean, 1 findings, 2 "couldn't check",
# 64 usage/configuration error.
EXIT_OK = checks.EXIT_CLEAN
EXIT_FINDINGS = checks.EXIT_FINDINGS
EXIT_UNDEFINED = checks.EXIT_UNDEFINED
EXIT_USAGE_ERROR = checks.EXIT_USAGE


def _build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(prog='python -m fastapi_blog')
  subparsers = parser.add_subparsers(dest='command', required=True)

  check_parser = subparsers.add_parser(
    'check', help='Check the collections for integrity problems'
  )
  check_parser.add_argument(
    '--collection',
    help='Check only this collection (default: all of the project file, '
    'else the default posts collection)',
  )
  check_parser.add_argument(
    '--json', action='store_true', help='Machine-readable report'
  )
  check_parser.add_argument(
    '--fail-on',
    choices=('error', 'warning'),
    default='error',
    help='Lowest level that fails the run (default: error)',
  )

  export_parser = subparsers.add_parser(
    'export', help='Export a collection to JSON-LD'
  )
  export_parser.add_argument(
    '--posts-dir',
    help="Directory of the collection (default: the project file's, else "
    "'posts')",
  )
  export_parser.add_argument(
    '--schema',
    help="Path to a YAML/JSON schema file (default: the project file's, "
    'else the built-in fields)',
  )
  export_parser.add_argument(
    '--collection',
    help='Collection name from the project file (default: the project '
    "file's, else 'posts')",
  )
  export_parser.add_argument(
    '--format',
    choices=('jsonld', 'expanded', 'nquads'),
    default='jsonld',
    help="Output format ('expanded'/'nquads' need the `jsonld` extra)",
  )
  export_parser.add_argument('--out', help='Output file (default: stdout)')

  schema_parser = subparsers.add_parser(
    'schema', help='Inspect a frontmatter schema'
  )
  schema_parser.add_argument(
    '--schema',
    help='Path to a YAML/JSON schema file (default: the built-in fields)',
  )
  schema_parser.add_argument(
    '--json-schema',
    action='store_true',
    help='Print the JSON Schema of the frontmatter (TODO 5.7)',
  )
  schema_parser.add_argument('--out', help='Output file (default: stdout)')

  return parser


def _load_schema(schema_path: str | None) -> FrontmatterSchema:
  if schema_path is None:
    return DEFAULT_SCHEMA
  return FrontmatterSchema.from_file(schema_path)


def _resolve_specs(
  collection: str | None,
  posts_dir: str | None = None,
  schema_path: str | None = None,
) -> tuple[list[CollectionSpec], Path]:
  """Apply the precedence: CLI flag > project file > built-in defaults.

  Returns:
      The specs to work on and the project root (for context files and
      relative `dir` entries).

  Raises:
      ConfigError: The project file or an explicit name/schema is wrong.

  """
  project = config.find_project()
  if project is not None:
    if collection:
      spec = project.collections.get(collection)
      if spec is None:
        raise ConfigError(
          f'Collection {collection!r} is not in {config.DEFAULT_CONFIG_NAME}'
        )
      specs = [spec]
    elif 'posts' in project.collections:
      specs = [project.collections['posts']]
    elif len(project.collections) == 1:
      specs = list(project.collections.values())
    else:
      raise ConfigError(
        f'{config.DEFAULT_CONFIG_NAME} lists several collections; '
        'pass --collection NAME'
      )
    root = project.root
  else:
    specs = [
      CollectionSpec(
        name=collection or 'posts',
        dir=Path(posts_dir or 'posts'),
        schema=_load_schema(schema_path),
      )
    ]
    root = Path.cwd()

  def _with_overrides(spec: CollectionSpec) -> CollectionSpec:
    # An explicit flag beats the project file.
    if posts_dir is None and schema_path is None:
      return spec
    return dataclasses.replace(
      spec,
      dir=Path(posts_dir) if posts_dir else spec.dir,
      schema=_load_schema(schema_path) if schema_path else spec.schema,
    )

  return [_with_overrides(spec) for spec in specs], root


def _export_graph(args: argparse.Namespace) -> dict[str, Any]:
  specs, root = _resolve_specs(args.collection, args.posts_dir, args.schema)
  spec = specs[0]
  documents_store = store.DocumentStore(spec.to_collection())
  documents = []
  for slug in documents_store.list():
    record = documents_store.read(slug)
    documents.append((slug, record.frontmatter, record.body.strip()))
  return jsonld_module.collection_to_jsonld(
    documents,
    schema=spec.schema or DEFAULT_SCHEMA,
    collection=spec.name,
    context=jsonld_module.resolve_context(
      spec.schema or DEFAULT_SCHEMA, project_root=root
    ),
  )


def _render(graph: dict[str, Any], fmt: str) -> str | None:
  """Render `graph` as `fmt`.

  Returns `None` if `fmt` needs the `jsonld` extra and it isn't installed
  (the caller prints the error and exits 64).
  """
  if fmt == 'jsonld':
    return json.dumps(graph, indent=2, ensure_ascii=False) + '\n'

  try:
    from pyld import jsonld as pyld_jsonld  # type: ignore[import-untyped]
  except ImportError:
    return None

  if fmt == 'expanded':
    expanded = pyld_jsonld.expand(graph)
    return json.dumps(expanded, indent=2, ensure_ascii=False) + '\n'

  # 'nquads': RDF statements have no inherent order, so lines are sorted
  # for deterministic, `git diff`-friendly output (TODO 5.4).
  quads = pyld_jsonld.to_rdf(graph, {'format': 'application/n-quads'})
  lines = sorted(line for line in quads.splitlines() if line)
  return '\n'.join(lines) + '\n'


def _cmd_export(args: argparse.Namespace) -> int:
  try:
    graph = _export_graph(args)
  except (ValueError, OSError, ConfigError, jsonld_module.JsonLdError) as exc:
    print(f'error: {exc}', file=sys.stderr)
    return EXIT_USAGE_ERROR

  output = _render(graph, args.format)
  if output is None:
    print(
      f'error: --format {args.format} needs the `jsonld` extra '
      "(pip install 'fastapi-blog[jsonld]')",
      file=sys.stderr,
    )
    return EXIT_USAGE_ERROR

  if args.out:
    Path(args.out).write_text(output, encoding='utf-8')
  else:
    sys.stdout.write(output)
  return EXIT_OK


def _format_report(report: checks.Report) -> list[str]:
  if not report.issues:
    return [f'{report.collection}: {report.documents} documents, no issues']
  counts = ', '.join(
    f'{report.count(level)} {level}{"" if report.count(level) == 1 else "s"}'
    for level in ('error', 'warning', 'undefined')
    if report.count(level)
  )
  lines = [f'{report.collection}: {report.documents} documents, {counts}']
  for issue in report.issues:
    where = issue.slug or report.collection
    field = f' {issue.field}:' if issue.field else ''
    lines.append(
      f'  [{issue.level}] {issue.code} ({where}){field} {issue.message}'
    )
  return lines


def _cmd_check(args: argparse.Namespace) -> int:
  try:
    specs, root = _resolve_specs(args.collection)
  except (ConfigError, ValueError, OSError) as exc:
    print(f'error: {exc}', file=sys.stderr)
    return EXIT_USAGE_ERROR
  reports = [checks.check_collection(spec, root=root) for spec in specs]

  if args.json:
    output = (
      json.dumps(
        {'collections': [report.to_dict() for report in reports]},
        indent=2,
        ensure_ascii=False,
      )
      + '\n'
    )
  else:
    output = (
      '\n'.join(line for report in reports for line in _format_report(report))
      + '\n'
    )
  sys.stdout.write(output)
  return checks.exit_code(reports, args.fail_on)


def _cmd_schema(args: argparse.Namespace) -> int:
  if not args.json_schema:
    print(
      'error: schema needs --json-schema (nothing else to do yet)',
      file=sys.stderr,
    )
    return EXIT_USAGE_ERROR

  try:
    schema = _load_schema(args.schema)
  except (ValueError, OSError) as exc:
    print(f'error: {exc}', file=sys.stderr)
    return EXIT_USAGE_ERROR

  output = json.dumps(schema.model().model_json_schema(), indent=2) + '\n'
  if args.out:
    Path(args.out).write_text(output, encoding='utf-8')
  else:
    sys.stdout.write(output)
  return EXIT_OK


def main(argv: list[str] | None = None) -> int:
  parser = _build_parser()
  args = parser.parse_args(argv)
  if args.command == 'check':
    return _cmd_check(args)
  if args.command == 'export':
    return _cmd_export(args)
  if args.command == 'schema':
    return _cmd_schema(args)
  parser.error(f'Unknown command: {args.command}')  # pragma: no cover
  return EXIT_USAGE_ERROR  # pragma: no cover


if __name__ == '__main__':
  raise SystemExit(main())
