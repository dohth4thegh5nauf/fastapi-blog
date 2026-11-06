"""JSON-LD emission for frontmatter documents.

An optional projection of validated documents into JSON-LD, built on the same
`FrontmatterSchema`/`alias` mechanism already used for frontmatter keys: a
field aliased `'@id'`/`'@type'`/`'@context'` supplies that key directly, and
every other field is emitted under its own alias, in schema order.

This module works without the `jsonld` extra (`pyld`); that extra is only
needed for `--format expanded`/`nquads` CLI output and for fetching remote
contexts. `resolve_context` loads contexts from inline mappings, files
inside the project root and allow-listed URLs. The HTTP routes
(`GET {prefix}/{slug}.jsonld`) and the `export` CLI command live in
`router.py` and `__main__.py`; they call the pure projection functions
here, passing a resolved `context=` when they need one.
"""

import datetime
import importlib.util
import pathlib
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from typing import Any

import yaml

from .models import FrontmatterSchema, JsonLdConfig
from .templates import parse_template


_RESERVED_ALIASES = ('@id', '@type', '@context')


class JsonLdError(Exception):
  """The JSON-LD export can't be built (bad context, too many documents)."""


class ContextUnavailableError(JsonLdError):
  """A context can't be loaded; the outcome is `undefined`, never "ok"."""


# --- Contexts ------------------------------------------------------


class _NoCrossHostRedirect(urllib.request.HTTPRedirectHandler):
  """Refuse redirects that would take the fetch to another host."""

  def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
    old_netloc = urllib.parse.urlsplit(req.full_url).netloc
    if urllib.parse.urlsplit(newurl).netloc != old_netloc:
      raise urllib.error.URLError('redirect to another host refused')
    return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_remote_context(url: str, limit: int, timeout: float = 10.0) -> Any:
  """Fetch an allowed remote context (size-limited, no cross-host redirect).

  Raises:
      ContextUnavailableError: The `jsonld` extra isn't installed, the
          fetch failed or the context is larger than `limit`.

  """
  if importlib.util.find_spec('pyld') is None:
    raise ContextUnavailableError(
      f'Remote context {url} needs the `jsonld` extra: '
      'pip install "fastapi-blog[jsonld]"'
    )
  opener = urllib.request.build_opener(_NoCrossHostRedirect)
  request = urllib.request.Request(
    url, headers={'Accept': 'application/ld+json'}
  )
  try:
    with opener.open(request, timeout=timeout) as response:  # noqa: S310
      data = response.read(limit + 1)
  except (urllib.error.URLError, TimeoutError, OSError) as exc:
    raise ContextUnavailableError(f"Can't fetch context {url}: {exc}") from exc
  if len(data) > limit:
    raise ContextUnavailableError(f'Context {url} is larger than {limit} bytes')
  return _parse_context_text(data.decode('utf-8', 'replace'), url)


def _parse_context_text(text: str, where: str) -> Any:
  """Parse a context file's text; a whole document's `@context` is extracted."""
  try:
    loaded = yaml.safe_load(text)
  except yaml.YAMLError as exc:
    raise ContextUnavailableError(
      f"Context {where} isn't valid: {exc}"
    ) from exc
  if isinstance(loaded, Mapping) and '@context' in loaded:
    return loaded['@context']
  return loaded


def _load_context_item(
  item: Any, config: JsonLdConfig, project_root: pathlib.Path
) -> Any:
  """Resolve one context item: mapping as-is, file path or allowed URL."""
  if isinstance(item, Mapping) or item is None:
    return item
  if not isinstance(item, str):
    raise JsonLdError(f'A context must be a mapping or a string, got {item!r}')
  if item.startswith(('http://', 'https://')):
    if item not in config.allow_remote_contexts:
      raise ContextUnavailableError(
        f"Remote context {item} isn't in `jsonld.allow_remote_contexts`"
      )
    return fetch_remote_context(item, config.max_context_bytes)
  root = project_root.resolve()
  path = (root / item).resolve()
  if not path.is_relative_to(root):
    raise ContextUnavailableError(f'Context file {item} is outside the project')
  try:
    if path.stat().st_size > config.max_context_bytes:
      raise ContextUnavailableError(
        f'Context file {item} is larger than {config.max_context_bytes} bytes'
      )
    return _parse_context_text(path.read_text(encoding='utf-8'), item)
  except OSError as exc:
    raise ContextUnavailableError(
      f"Can't read context file {item}: {exc}"
    ) from exc


def resolve_context(
  schema: FrontmatterSchema, *, project_root: pathlib.Path | None = None
) -> Any:
  """Load the schema's `jsonld.context`, resolving files and allowed URLs.

  Args:
      schema: The schema whose `jsonld` section holds the context.
      project_root: Project root that file paths in the context are
          resolved against (default: the current working directory).

  Returns:
      The inline context, or the loaded `@context` of a file/document.
          `None` when the schema has no `jsonld` section or no context.

  Raises:
      JsonLdError: A context item has an unsupported shape.
      ContextUnavailableError: A file or an allowed URL can't be loaded.

  """
  config = schema.jsonld
  if config is None or config.context is None:
    return None
  root = pathlib.Path.cwd() if project_root is None else project_root
  raw = config.context
  if isinstance(raw, list):
    return [_load_context_item(item, config, root) for item in raw]
  return _load_context_item(raw, config, root)


def document_to_jsonld(
  frontmatter: Mapping[str, Any],
  *,
  schema: FrontmatterSchema,
  slug: str,
  collection: str = '',
  content: str | None = None,
  context: Any = None,
) -> dict[str, Any]:
  """Project one document into a JSON-LD object.

  Args:
      frontmatter: The document's frontmatter, by external key (alias) —
          e.g. from `DocumentStore.read(...).frontmatter`, or
          `FrontmatterSchema.dump_for_write`'s return value.
      schema: The schema `frontmatter` was validated against. Its `jsonld`
          config (if any) supplies the default `@context`/`@type` and the
          `@id` template.
      slug: The document's slug, used by the default `@id` template.
      collection: The collection's name, used by the default `@id` template.
      content: The document body. Included under `schema.jsonld.content_term`
          when that's set; otherwise ignored.
      context: `@context` to emit, already resolved by `resolve_context`;
          overrides `schema.jsonld.context` when given.

  Returns:
      A plain dict ready for `json.dumps`: `@context` (when configured),
      `@id`/`@type` (when available from a field or the schema's `jsonld`
      config), then the schema's own fields in schema order, by alias.
      `None` and empty values (`''`, `[]`, `{}`) are omitted. `date`/
      `datetime` values become ISO 8601 strings.

  """
  config = schema.jsonld or JsonLdConfig()
  result: dict[str, Any] = {}

  effective_context = config.context if context is None else context
  if effective_context is not None:
    result['@context'] = effective_context

  doc_id = frontmatter.get('@id')
  if not _is_empty(doc_id):
    result['@id'] = doc_id
  elif config.id_template is not None:
    field_values = {
      spec.name: frontmatter.get(spec.key) for spec in schema.fields
    }
    tags: dict[str, Any] = {
      'base': config.base or '',
      'collection': collection,
      'slug': slug,
      'dirname': slug.rsplit('/', 1)[0] if '/' in slug else '',
      'filename': slug.rsplit('/', 1)[-1],
    }
    date_spec = schema.field_for_role('date')
    date_value = frontmatter.get(date_spec.key) if date_spec else None
    if date_value:
      if isinstance(date_value, str):
        try:
          date_value = datetime.date.fromisoformat(date_value[:10])
        except ValueError:
          date_value = None
      if isinstance(date_value, datetime.datetime | datetime.date):
        tags.update(
          year=date_value.year,
          month=f'{date_value.month:02d}',
          day=f'{date_value.day:02d}',
        )
    template = parse_template(
      config.id_template,
      (
        'base',
        'collection',
        'slug',
        'title_slug',
        'seq',
        'year',
        'month',
        'day',
        'dirname',
        'filename',
      ),
      field_values.keys(),
    )
    result['@id'] = template.render(tags, field_values)

  doc_type = frontmatter.get('@type')
  if not _is_empty(doc_type):
    result['@type'] = doc_type
  elif config.type is not None:
    result['@type'] = config.type

  for spec in schema.fields:
    if spec.key in _RESERVED_ALIASES:
      continue
    if spec.key not in frontmatter:
      continue
    value = _jsonld_value(frontmatter[spec.key])
    if _is_empty(value):
      continue
    result[spec.key] = value

  if config.content_term and content:
    result[config.content_term] = content

  return result


def collection_to_jsonld(
  documents: Sequence[tuple[str, Mapping[str, Any], str | None]],
  *,
  schema: FrontmatterSchema,
  collection: str = '',
  context: Any = None,
) -> dict[str, Any]:
  """Project a whole collection into one JSON-LD graph.

  Args:
      documents: `(slug, frontmatter, content)` triples, e.g. built from
          `DocumentStore.list()` + `.read(slug)` for each slug.
      schema: Schema shared by every document (see `document_to_jsonld`).
      collection: Collection name, used by the default `@id` template.
      context: `@context` for the graph as a whole; overrides
          `schema.jsonld.context` when given.

  Returns:
      `{'@context': ..., '@graph': [...]}` (no top-level `@context` when
      neither `context` nor `schema.jsonld.context` is set). `@graph` is
      sorted by `@id`, then slug, so the output is deterministic regardless
      of filesystem iteration order — two runs produce identical bytes.

  Raises:
      JsonLdError: There are more documents than `jsonld.max_documents`.

  """
  config = schema.jsonld or JsonLdConfig()
  if len(documents) > config.max_documents:
    raise JsonLdError(
      f'{len(documents)} documents exceed `jsonld.max_documents` '
      f'({config.max_documents})'
    )
  nodes: list[tuple[str, str, dict[str, Any]]] = []
  for slug, frontmatter, content in documents:
    node = document_to_jsonld(
      frontmatter,
      schema=schema,
      slug=slug,
      collection=collection,
      content=content,
    )
    node.pop('@context', None)  # once on the graph, not on every node
    nodes.append((str(node.get('@id', '')), slug, node))
  nodes.sort(key=lambda item: (item[0], item[1]))

  result: dict[str, Any] = {}
  effective_context = context if context is not None else config.context
  if effective_context is not None:
    result['@context'] = effective_context
  result['@graph'] = [node for _, _, node in nodes]
  return result


def _is_empty(value: Any) -> bool:
  return value is None or value == '' or value == [] or value == {}


def _jsonld_value(value: Any) -> Any:
  if isinstance(value, datetime.datetime | datetime.date):
    return value.isoformat()
  if isinstance(value, list | tuple):
    return [_jsonld_value(item) for item in value]
  if isinstance(value, Mapping):
    return {key: _jsonld_value(item) for key, item in value.items()}
  return value


def pyld_available() -> bool:
  """Return whether the optional `jsonld` extra (`pyld`) is installed."""
  return importlib.util.find_spec('pyld') is not None


def _schema_keys(schema: FrontmatterSchema) -> list[str]:
  """Return the checkable schema keys: field keys plus `content_term`."""
  config = schema.jsonld
  keys = [spec.key for spec in schema.fields if not spec.key.startswith('@')]
  if config and config.content_term:
    keys.append(config.content_term)
  return keys


def uncovered_keys(
  schema: FrontmatterSchema, *, project_root: pathlib.Path | None = None
) -> list[str]:
  """Return the schema keys the JSON-LD `@context` doesn't cover.

  A key is covered by a context term of the same name, by a prefix
  (`prefix:name`) or by `@vocab`. The `content_term` counts as a key too.
  By default only the inline context (`jsonld.context`, a mapping or a list
  of mappings) is inspected; pass `project_root` to resolve file paths and
  allowed URLs first. URL context items without `project_root`
  are skipped, not loaded — "can't check" is its own outcome, never "ok".

  Args:
      schema: The schema whose `jsonld` section holds the context and whose
          fields supply the keys.
      project_root: When given, the context is loaded through
          `resolve_context` against this project root first.

  Returns:
      The sorted schema keys (by alias, `@`-keys excluded) that expansion
      would drop, including `content_term` when it isn't covered.

  Raises:
      ContextUnavailableError: With `project_root`, a context file or URL
          can't be loaded.

  """
  config = schema.jsonld
  raw_context = config.context if config else None
  if project_root is not None and raw_context is not None:
    raw_context = resolve_context(schema, project_root=project_root)
  terms, has_vocab = _covered_terms(raw_context)
  missing = []
  for key in _schema_keys(schema):
    prefix = key.split(':', 1)[0] if ':' in key else None
    if key in terms or has_vocab or (prefix is not None and prefix in terms):
      continue
    missing.append(key)
  return sorted(missing)


def probe_lost_keys(
  schema: FrontmatterSchema, *, project_root: pathlib.Path | None = None
) -> list[str]:
  """Expand a probe document per schema key through `pyld`.

  The dynamic counterpart of `uncovered_keys`: rather than reading the
  context statically, every key is expanded on its own in a minimal probe
  document; a key `pyld` drops from the expansion is lost. This catches
  what static reading can't judge — for example terms remapped through
  `@id` definitions or nested contexts.

  Args:
      schema: The schema whose `jsonld` section holds the context and whose
          fields supply the keys.
      project_root: When given, the context is loaded through
          `resolve_context` against this project root first.

  Returns:
      The sorted schema keys (by alias, `@`-keys excluded) that expansion
      drops, including `content_term` when it isn't covered.

  Raises:
      ContextUnavailableError: The `jsonld` extra isn't installed, or a
          context file or URL can't be loaded.
      JsonLdError: The resolved context itself is invalid for expansion.

  """
  if not pyld_available():
    raise ContextUnavailableError(
      'The context probe needs the `jsonld` extra: '
      'pip install "fastapi-blog[jsonld]"'
    )
  from pyld import jsonld as pyld_jsonld  # type: ignore[import-untyped]

  config = schema.jsonld
  raw_context = config.context if config else None
  if project_root is not None and raw_context is not None:
    raw_context = resolve_context(schema, project_root=project_root)
  lost = []
  for key in _schema_keys(schema):
    probe = {'@context': raw_context, key: 'probe'}
    try:
      expanded = pyld_jsonld.expand(probe)
    except pyld_jsonld.JsonLdError as exc:
      raise JsonLdError(f"Can't expand the probe document: {exc}") from exc
    # Covered means the context maps the key somewhere: to an absolute IRI
    # (term, `@vocab`) or through a defined prefix. A key surviving only
    # under its own name — dropped outright, or kept as a literal "IRI"
    # because an undefined `prefix:` looks like a scheme — isn't covered,
    # matching the static reading in `uncovered_keys`.
    covered = any(any(prop != key for prop in node) for node in expanded)
    if not covered:
      lost.append(key)
  return sorted(lost)


def _covered_terms(context: Any) -> tuple[set[str], bool]:
  """Collect the terms of an inline context and whether it sets `@vocab`."""
  terms: set[str] = set()
  has_vocab = False
  items = context if isinstance(context, list) else [context]
  for item in items:
    if not isinstance(item, Mapping):
      continue  # A string item is a context URL: not loaded here.
    for key, value in item.items():
      if key == '@vocab' and value:
        has_vocab = True
      elif not str(key).startswith('@') and value is not None:
        terms.add(str(key))
  return terms, has_vocab
