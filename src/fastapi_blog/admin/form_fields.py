"""Build the admin post form from a frontmatter schema.

The functions here have no web framework dependencies: they turn a
`FrontmatterSchema` and the current frontmatter values into plain dicts that
the `markdown_edit.html` template renders and its script reads back.
"""

import datetime
import json
import re
from collections.abc import Mapping
from typing import Any

from ..models import MISSING, FieldSpec, FrontmatterSchema


# Kinds that fit two in a row on wide screens (the rest take the full width).
_HALF_WIDTH_KINDS = ('date', 'datetime', 'bool', 'number')

# Kinds whose input can carry the HTML `required` attribute.
_REQUIRABLE_KINDS = ('text', 'textarea', 'date', 'datetime', 'number')

_ISO_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}')


def get_field_value(
  frontmatter: Mapping[str, Any], spec: FieldSpec | None, default: Any = None
) -> Any:
  """Return the value of a field from raw frontmatter.

  Documents may use the external key (alias) or the internal name, so both are
  tried. A missing or empty (`None`) value gives `default`.

  Args:
      frontmatter: Raw frontmatter loaded from a markdown file.
      spec: Field description, or `None` (then `default` is returned).
      default: Value for a missing field.

  Returns:
      The value from the document or `default`.

  """
  if spec is None:
    return default
  for key in (spec.key, spec.name):
    value = frontmatter.get(key)
    if value is not None:
      return value
  return default


def field_kind(spec: FieldSpec) -> str:
  """Return the kind of form input for a field.

  Args:
      spec: Field description.

  Returns:
      One of `bool`, `date`, `datetime`, `number`, `list`, `int_list`, `json`,
      `textarea` or `text`.

  """
  if spec.type == 'bool':
    return 'bool'
  if spec.type == 'date' or (spec.role == 'date' and spec.type == 'str'):
    return 'date'
  if spec.type == 'datetime':
    return 'datetime'
  if spec.type in ('int', 'float'):
    return 'number'
  if spec.type == 'list[str]':
    return 'list'
  if spec.type == 'list[int]':
    return 'int_list'
  if spec.type in ('dict', 'any'):
    return 'json'
  if spec.role == 'description':
    return 'textarea'
  if spec.max_length is not None and spec.max_length > 200:
    return 'textarea'
  return 'text'


def format_value(kind: str, value: Any) -> str:
  """Convert a frontmatter value to the string shown in the form input.

  Args:
      kind: Input kind from `field_kind`.
      value: Value from the document (any type YAML can produce).

  Returns:
      The string for the input's `value`.

  """
  if value is None:
    return ''
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
  """Return the initial value of a field in the "new post" form.

  The field with the `date` role starts with today’s date, a `bool` starts
  with its default (or `False`), other fields use their default if they have one.

  Args:
      spec: Field description.
      kind: Input kind from `field_kind`.

  Returns:
      The initial value (may be `None`).

  """
  if spec.default is not MISSING:
    return spec.default
  if kind == 'bool':
    return False
  if spec.role == 'date':
    now = datetime.datetime.now()
    if kind == 'datetime':
      return now
    return now.strftime('%Y-%m-%d')
  return None


def build_form_fields(
  schema: FrontmatterSchema,
  frontmatter: Mapping[str, Any],
  labels: Mapping[str, str],
  *,
  is_new: bool = False,
) -> list[dict[str, Any]]:
  """Describe every schema field for the admin form.

  Args:
      schema: Frontmatter schema of the blog.
      frontmatter: Raw frontmatter of the edited post (ignored for a new post).
      labels: Translations of the form. The labels for the roles (`title`,
          `date`, ...) and `tags_hint` are taken from it.
      is_new: Fill the form with initial values instead of the post’s values.

  Returns:
      One dict per field, in schema order.

  """
  result: list[dict[str, Any]] = []
  for spec in schema.fields:
    kind = field_kind(spec)
    if is_new:
      value = new_value(spec, kind)
    else:
      value = get_field_value(frontmatter, spec)
      if value is None and kind == 'bool':
        value = spec.default is True

    label = labels.get(spec.role) if spec.role else None
    result.append(
      {
        'name': spec.name,
        'key': spec.key,
        'kind': kind,
        'label': label or spec.description or spec.name,
        'value': format_value(kind, value),
        'required': spec.required,
        'html_required': spec.required and kind in _REQUIRABLE_KINDS,
        'max_length': spec.max_length,
        'col': 'col-md-6' if kind in _HALF_WIDTH_KINDS else 'col-12',
        'hint': labels.get('tags_hint', '') if kind == 'list' else '',
      }
    )
  return result


def form_fields_meta(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
  """Return what the form script needs to read each field back.

  Args:
      fields: Result of `build_form_fields`.

  Returns:
      List of `{name, key, kind}` dicts.

  """
  return [
    {'name': f['name'], 'key': f['key'], 'kind': f['kind']} for f in fields
  ]
