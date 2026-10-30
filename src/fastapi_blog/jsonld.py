"""JSON-LD emission for frontmatter documents (TODO phase C, 5.2-5.4).

An optional projection of validated documents into JSON-LD, built on the same
`FrontmatterSchema`/`alias` mechanism already used for frontmatter keys: a
field aliased `'@id'`/`'@type'`/`'@context'` supplies that key directly, and
every other field is emitted under its own alias, in schema order.

This module works without the `jsonld` extra (`pyld`); that extra is only
needed for `--format expanded`/`nquads` output and strict external-context
validation (TODO 5.5, 5.6), neither built yet. Loading `context` from a local
file, the HTTP routes (`GET {prefix}/{slug}.jsonld`) and the `export` CLI
command (TODO 5.4) aren't built yet either — this module only has the pure
`dict`-in, `dict`-out projection functions.
"""

import datetime
from collections.abc import Mapping, Sequence
from typing import Any

from .models import FrontmatterSchema, JsonLdConfig


_RESERVED_ALIASES = ('@id', '@type', '@context')


def document_to_jsonld(
  frontmatter: Mapping[str, Any],
  *,
  schema: FrontmatterSchema,
  slug: str,
  collection: str = '',
  content: str | None = None,
) -> dict[str, Any]:
  """Project one document into a JSON-LD object (TODO 5.4).

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

  Returns:
      A plain dict ready for `json.dumps`: `@context` (when configured),
      `@id`/`@type` (when available from a field or the schema's `jsonld`
      config), then the schema's own fields in schema order, by alias.
      `None` and empty values (`''`, `[]`, `{}`) are omitted. `date`/
      `datetime` values become ISO 8601 strings.

  """
  config = schema.jsonld or JsonLdConfig()
  result: dict[str, Any] = {}

  if config.context is not None:
    result['@context'] = config.context

  doc_id = frontmatter.get('@id')
  if not _is_empty(doc_id):
    result['@id'] = doc_id
  elif config.id_template is not None:
    result['@id'] = config.id_template.format(
      base=config.base or '', collection=collection, slug=slug
    )

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
  """Project a whole collection into one JSON-LD graph (TODO 5.4).

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

  """
  config = schema.jsonld or JsonLdConfig()
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
