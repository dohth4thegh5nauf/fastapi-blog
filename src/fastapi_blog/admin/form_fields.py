"""Build the admin post form from a frontmatter schema.

The helpers in this module are framework independent. They describe both
simple and recursively nested schema fields for the Markdown editor.
"""

import datetime
import json
import re
from collections.abc import Mapping
from typing import Any

from ..models import MISSING, FieldSpec, FrontmatterSchema


_HALF_WIDTH_KINDS = ('date', 'datetime', 'bool', 'number')
_REQUIRABLE_KINDS = ('text', 'textarea', 'date', 'datetime', 'number')
_ISO_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}')
_SEO_ROLES = frozenset(
  {
    'title',
    'description',
    'seo_title',
    'canonical',
    'robots',
    'image',
    'image_alt',
    'updated',
    'author',
    'lang',
    'redirect_from',
  }
)


def get_field_value(
  frontmatter: Mapping[str, Any], spec: FieldSpec | None, default: Any = None
) -> Any:
  """Read a field by its public alias or its internal name."""
  if spec is None:
    return default
  for key in (spec.key, spec.name):
    value = frontmatter.get(key)
    if value is not None:
      return value
  return default


def field_kind(spec: FieldSpec) -> str:
  """Return the kind of input used to edit a schema field."""
  if spec.hidden:
    return 'hidden'
  if spec.type == 'bool':
    return 'bool'
  if spec.type in ('object', 'list[object]', 'dict', 'any'):
    return 'json'
  if spec.type == 'date' or (spec.role == 'date' and spec.type == 'str'):
    return 'date'
  if spec.type == 'datetime':
    return 'datetime'
  if spec.type in ('int', 'float'):
    return 'number'
  if spec.type == 'list[str]' or spec.type == 'list[link]':
    return 'list'
  if spec.type == 'list[int]':
    return 'int_list'
  if spec.role == 'description' or (spec.max_length and spec.max_length > 200):
    return 'textarea'
  return 'text'


def format_value(kind: str, value: Any) -> str:
  """Convert a YAML value to the string displayed in the form."""
  if value is None:
    return ''
  if kind in ('hidden',):
    return json.dumps(value, ensure_ascii=False, default=str)
  if kind == 'bool':
    return 'true' if value else 'false'
  if kind == 'date':
    text = str(value)
    match = _ISO_DATE.match(text)
    return match.group(0) if match else text
  if kind == 'datetime':
    if isinstance(value, datetime.datetime):
      return value.replace(tzinfo=None).isoformat(timespec='minutes')
    return str(value).replace(' ', 'T')[:16]
  if kind in ('list', 'int_list'):
    if isinstance(value, list | tuple):
      return ', '.join(str(item) for item in value)
    return str(value)
  if kind == 'json':
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)
  return str(value)


def new_value(spec: FieldSpec, kind: str) -> Any:
  """Return the value used to prefill a newly created document."""
  if spec.default is not MISSING:
    return spec.default
  if kind == 'bool':
    return False
  if spec.role == 'date':
    now = datetime.datetime.now()
    return now if kind == 'datetime' else now.strftime('%Y-%m-%d')
  if kind == 'json' and spec.type in ('object', 'dict'):
    return {}
  if kind == 'json' and spec.type == 'list[object]':
    return []
  return None


def _flatten(
  specs: tuple[FieldSpec, ...], prefix: tuple[FieldSpec, ...] = ()
) -> list[tuple[tuple[FieldSpec, ...], FieldSpec]]:
  """Return parent paths and editable fields; object fields become children."""
  result: list[tuple[tuple[FieldSpec, ...], FieldSpec]] = []
  for spec in specs:
    if spec.type == 'object' and not spec.hidden:
      result.extend(_flatten(spec.fields or (), (*prefix, spec)))
    else:
      result.append((prefix, spec))
  return result


def _nested(
  frontmatter: Mapping[str, Any], parents: tuple[FieldSpec, ...]
) -> Mapping[str, Any]:
  """Walk a nested object using each parent's external key."""
  current: Any = frontmatter
  for parent in parents:
    current = (
      get_field_value(current, parent, {})
      if isinstance(current, Mapping)
      else {}
    )
  return current if isinstance(current, Mapping) else {}


def _group(spec: FieldSpec, parents: tuple[FieldSpec, ...]) -> str:
  if spec.group:
    return spec.group
  for parent in reversed(parents):
    if parent.group:
      return parent.group
  if parents:
    return ' / '.join(p.label or p.description or p.name for p in parents)
  if spec.role in _SEO_ROLES:
    return 'SEO'
  return ''


def build_form_fields(
  schema: FrontmatterSchema,
  frontmatter: Mapping[str, Any],
  labels: Mapping[str, str],
  *,
  is_new: bool = False,
) -> list[dict[str, Any]]:
  """Describe every form input in schema order, including nested fields."""
  result: list[dict[str, Any]] = []
  seo_check = schema.seo.check if schema.seo and schema.seo.check else None
  for parents, spec in _flatten(schema.fields):
    kind = field_kind(spec)
    source = {} if is_new else _nested(frontmatter, parents)
    value = new_value(spec, kind) if is_new else get_field_value(source, spec)
    if value is None and kind == 'bool':
      value = spec.default is True
    if value is None and spec.default is not MISSING and kind == 'hidden':
      value = spec.default

    label = spec.label or (labels.get(spec.role) if spec.role else None)
    path = [parent.key for parent in parents] + [spec.key]
    name = '__'.join([parent.name for parent in parents] + [spec.name])
    counter_max = None
    if seo_check is not None:
      if spec.role in ('title', 'seo_title'):
        counter_max = seo_check.title_max
      elif spec.role == 'description':
        counter_max = seo_check.description_max
    result.append(
      {
        'name': name,
        'key': spec.key,
        'path': path,
        'type': spec.type,
        'kind': kind,
        'group': _group(spec, parents),
        'label': label or spec.description or spec.name,
        'value': format_value(kind, value),
        'required': spec.required,
        'html_required': spec.required and kind in _REQUIRABLE_KINDS,
        'max_length': spec.max_length,
        'counter_max': counter_max,
        'min': spec.min,
        'max': spec.max,
        'read_only': (
          not is_new and (spec.read_only or any(p.read_only for p in parents))
        ),
        'col': 'col-md-6' if kind in _HALF_WIDTH_KINDS else 'col-12',
        'hint': spec.hint
        or (labels.get('tags_hint', '') if kind == 'list' else ''),
      }
    )
  return result


def form_fields_meta(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
  """Return the field metadata needed to reconstruct frontmatter on save."""
  return [
    {
      'name': field['name'],
      'key': field['key'],
      'path': field['path'],
      'kind': field['kind'],
      'type': field['type'],
      **({'value': field['value']} if field['kind'] == 'hidden' else {}),
    }
    for field in fields
  ]
