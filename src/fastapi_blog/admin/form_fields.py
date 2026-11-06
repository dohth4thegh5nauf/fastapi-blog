"""Build the admin post form from a frontmatter schema.

The helpers in this module are framework independent. They describe both
simple and recursively nested schema fields for the Markdown editor.
"""

import datetime
import json
import re
from collections.abc import Mapping
from typing import Any

from ..i18n import resolve_localized
from ..models import MISSING, FieldSpec, FrontmatterSchema


_HALF_WIDTH_KINDS = ('date', 'datetime', 'bool', 'number')
_REQUIRABLE_KINDS = (
  'text',
  'textarea',
  'date',
  'datetime',
  'number',
  'select',
  'multi_select',
  'link',
  'link_list',
)
_ISO_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}')
_POST_ROLES = frozenset(
  {'title', 'date', 'published', 'status', 'tags', 'description'}
)
_SEO_ROLES = frozenset(
  {
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
  if spec.choices is not None:
    return 'multi_select' if spec.type.startswith('list[') else 'select'
  if spec.type == 'bool':
    return 'bool'
  if spec.type == 'list[object]':
    return 'object_list'
  if spec.type in ('object', 'dict', 'any'):
    return 'json'
  if spec.type == 'date' or (spec.role == 'date' and spec.type == 'str'):
    return 'date'
  if spec.type == 'datetime':
    return 'datetime'
  if spec.type in ('int', 'float'):
    return 'number'
  if spec.type == 'link':
    return 'link'
  if spec.type == 'list[str]' or spec.type == 'list[link]':
    return 'link_list' if spec.type == 'list[link]' else 'list'
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
  if kind in ('list', 'int_list', 'link_list', 'multi_select'):
    if isinstance(value, list | tuple):
      return ', '.join(str(item) for item in value)
    return str(value)
  if kind == 'json':
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)
  if kind == 'object_list':
    return ''
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
  if kind == 'object_list' and spec.type == 'list[object]':
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


def _group(
  spec: FieldSpec,
  parents: tuple[FieldSpec, ...],
  *,
  locale: str | None,
  default_locale: str | None,
) -> str:
  if spec.group:
    return spec.group
  for parent in reversed(parents):
    if parent.group:
      return parent.group
  if parents:
    return ' / '.join(
      resolve_localized(p.label, locale, default_locale)
      or p.description
      or p.name
      for p in parents
    )
  if spec.role in _POST_ROLES:
    return 'Post metadata'
  if spec.role in _SEO_ROLES:
    return 'SEO'
  return 'Additional metadata'


def _choices_for(
  spec: FieldSpec, *, locale: str | None, default_locale: str | None
) -> list[dict[str, str]]:
  """Return normalized option labels and values for a schema field."""
  if spec.choices is None:
    return []
  result = []
  for item in spec.choices:
    if isinstance(item, Mapping):
      value = item.get('value')
      label = resolve_localized(item.get('label'), locale, default_locale)
      result.append({'value': str(value), 'label': str(label or value)})
    else:
      result.append({'value': str(item), 'label': str(item)})
  return result


def _pattern_for(spec: FieldSpec) -> tuple[str | None, str]:
  """Return a regular expression and its user-facing validation message."""
  pattern = spec.pattern if spec.pattern is not None else spec.item_pattern
  if isinstance(pattern, tuple):
    return pattern[0], pattern[1]
  if isinstance(pattern, list):
    return pattern[0], pattern[1]
  return pattern, ''


def _object_child_fields(
  spec: FieldSpec,
  *,
  is_new: bool,
  parent_read_only: bool,
  link_choices: Mapping[str, list[dict[str, str]]],
  parent_name: str,
  locale: str | None,
  default_locale: str | None,
) -> list[dict[str, Any]]:
  """Describe the controls rendered inside one list[object] row."""
  children: list[dict[str, Any]] = []
  for child in spec.fields or ():
    kind = field_kind(child)
    # Deep object values remain an explicit JSON editor inside a row. The
    # top-level list itself is rendered as repeatable nested field groups.
    if kind == 'object_list':
      kind = 'json'
    pattern, pattern_message = _pattern_for(child)
    child_name = f'{parent_name}__{child.name}'
    default_value = new_value(child, kind)
    selected_values = (
      [str(item) for item in default_value]
      if isinstance(default_value, (list, tuple))
      else ([str(default_value)] if default_value is not None else [])
    )
    children.append(
      {
        'name': child.name,
        'key': child.key,
        'kind': kind,
        'type': child.type,
        'label': resolve_localized(child.label, locale, default_locale)
        or child.description
        or child.name,
        'value': format_value(kind, default_value),
        'required': child.required,
        'read_only': not is_new and (parent_read_only or child.read_only),
        'choices': _choices_for(
          child, locale=locale, default_locale=default_locale
        ),
        'selected_values': selected_values,
        'multiple': kind == 'multi_select',
        'pattern': pattern,
        'pattern_message': pattern_message,
        'datalist_id': (
          f'link-options-{child_name}' if kind in ('link', 'link_list') else ''
        ),
        'link_suggestions': link_choices.get(child_name, []),
        'hint': resolve_localized(child.hint, locale, default_locale) or '',
        'min': child.min,
        'max': child.max,
        'max_length': child.max_length,
      }
    )
  return children


def _object_item_fields(
  spec: FieldSpec,
  item: Mapping[str, Any],
  children: list[dict[str, Any]],
) -> list[dict[str, Any]]:
  """Return row-specific child values while retaining schema metadata."""
  result: list[dict[str, Any]] = []
  child_specs = {child.name: child for child in spec.fields or ()}
  for child in children:
    field = child_specs[child['name']]
    value = get_field_value(item, field, new_value(field, child['kind']))
    selected_values = (
      [str(item) for item in value]
      if isinstance(value, (list, tuple))
      else ([str(value)] if value is not None else [])
    )
    result.append(
      {
        **child,
        'value': format_value(child['kind'], value),
        'selected_values': selected_values,
      }
    )
  return result


def build_form_fields(
  schema: FrontmatterSchema,
  frontmatter: Mapping[str, Any],
  labels: Mapping[str, str],
  *,
  is_new: bool = False,
  link_choices: Mapping[str, list[dict[str, str]]] | None = None,
  locale: str | None = None,
  default_locale: str | None = None,
) -> list[dict[str, Any]]:
  """Describe every form input in schema order, including nested fields."""
  result: list[dict[str, Any]] = []
  link_choices = link_choices or {}
  seo_check = schema.seo.check if schema.seo and schema.seo.check else None
  for parents, spec in _flatten(schema.fields):
    kind = field_kind(spec)
    source = {} if is_new else _nested(frontmatter, parents)
    value = new_value(spec, kind) if is_new else get_field_value(source, spec)
    if value is None and kind == 'bool':
      value = spec.default is True
    if value is None and spec.default is not MISSING and kind == 'hidden':
      value = spec.default

    label = resolve_localized(spec.label, locale, default_locale) or (
      labels.get(spec.role) if spec.role else None
    )
    path = [parent.key for parent in parents] + [spec.key]
    name = '__'.join([parent.name for parent in parents] + [spec.name])
    counter_max = None
    if seo_check is not None:
      if spec.role in ('title', 'seo_title'):
        counter_max = seo_check.title_max
      elif spec.role == 'description':
        counter_max = seo_check.description_max
    choices = _choices_for(spec, locale=locale, default_locale=default_locale)
    pattern_regex, pattern_message = _pattern_for(spec)
    children = (
      _object_child_fields(
        spec,
        is_new=is_new,
        parent_read_only=(
          spec.read_only or any(parent.read_only for parent in parents)
        ),
        link_choices=link_choices,
        parent_name=name,
        locale=locale,
        default_locale=default_locale,
      )
      if spec.type == 'list[object]'
      else []
    )
    items = (
      [
        _object_item_fields(spec, item, children)
        for item in (value or [])
        if isinstance(item, Mapping)
      ]
      if spec.type == 'list[object]'
      else []
    )
    selected_values = (
      [str(item) for item in value]
      if isinstance(value, (list, tuple))
      else ([str(value)] if value is not None else [])
    )
    result.append(
      {
        'name': name,
        'key': spec.key,
        'path': path,
        'type': spec.type,
        'kind': kind,
        'choices': choices,
        'multiple': kind == 'multi_select',
        'selected_values': selected_values,
        'pattern': pattern_regex,
        'pattern_message': pattern_message or '',
        'link_suggestions': link_choices.get(name, []),
        'datalist_id': (
          f'link-options-{name}' if kind in ('link', 'link_list') else ''
        ),
        'children': children,
        'items': items,
        'group': _group(
          spec,
          parents,
          locale=locale,
          default_locale=default_locale,
        ),
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
        'hint': resolve_localized(spec.hint, locale, default_locale)
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
      'choices': field.get('choices', []),
      'multiple': field.get('multiple', False),
      'pattern': field.get('pattern'),
      'pattern_message': field.get('pattern_message', ''),
      'link_suggestions': field.get('link_suggestions', []),
      'children': [
        {
          'name': child['name'],
          'key': child['key'],
          'kind': child['kind'],
          'type': child['type'],
          'pattern': child.get('pattern'),
          'pattern_message': child.get('pattern_message', ''),
        }
        for child in field.get('children', [])
      ],
      **({'value': field['value']} if field['kind'] == 'hidden' else {}),
    }
    for field in fields
  ]
