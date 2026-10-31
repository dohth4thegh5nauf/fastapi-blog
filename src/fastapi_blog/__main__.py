"""Command-line interface: `python -m fastapi_blog <command>`.

`export` (TODO 5.4) and `schema --json-schema` (TODO 5.7) so far; `check`
(TODO 6.1) isn't built yet. Operates directly on the filesystem and a
schema file — it never starts a FastAPI app.

This CLI takes `--posts-dir`/`--schema`/`--collection` directly rather than
TODO's literal `--collection NAME` (which presupposes a project-level
registry of named collections, each with their own directory and schema;
that registry doesn't exist in this codebase — `Collection`s are built ad
hoc per call everywhere else too, see `store.Collection`'s docstring).
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import jsonld as jsonld_module
from . import store
from .models import DEFAULT_SCHEMA, FrontmatterSchema


# Exit codes, matching the convention TODO 6.1 sets for `check` (reused here
# since `export` is the same CLI): 0 clean, 64 usage/configuration error.
EXIT_OK = 0
EXIT_USAGE_ERROR = 64


def _build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(prog='python -m fastapi_blog')
  subparsers = parser.add_subparsers(dest='command', required=True)

  export_parser = subparsers.add_parser(
    'export', help='Export a collection to JSON-LD'
  )
  export_parser.add_argument(
    '--posts-dir',
    default='posts',
    help="Directory of the collection to export (default: 'posts')",
  )
  export_parser.add_argument(
    '--schema',
    help='Path to a YAML/JSON schema file (default: the built-in fields)',
  )
  export_parser.add_argument(
    '--collection',
    default='posts',
    help="Collection name, used by the schema's @id template (default: 'posts')",
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


def _export_graph(args: argparse.Namespace) -> dict[str, Any]:
  schema = _load_schema(args.schema)
  collection = store.Collection(args.collection, Path(args.posts_dir))
  docs_store = store.DocumentStore(collection)

  documents = []
  for slug in docs_store.list():
    record = docs_store.read(slug)
    documents.append((slug, record.frontmatter, record.body.strip()))

  return jsonld_module.collection_to_jsonld(
    documents,
    schema=schema,
    collection=args.collection,
    context=jsonld_module.resolve_context(schema),
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
  except (ValueError, OSError, jsonld_module.JsonLdError) as exc:
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
  if args.command == 'export':
    return _cmd_export(args)
  if args.command == 'schema':
    return _cmd_schema(args)
  parser.error(f'Unknown command: {args.command}')  # pragma: no cover
  return EXIT_USAGE_ERROR  # pragma: no cover


if __name__ == '__main__':
  raise SystemExit(main())
