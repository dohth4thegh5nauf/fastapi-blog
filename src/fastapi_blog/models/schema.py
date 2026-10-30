"""Configurable frontmatter schema for markdown documents.

A `FrontmatterSchema` describes which fields a markdown document may have,
their types, defaults and external names (aliases). It can be built in code
or loaded from a YAML/JSON file, and it produces a Pydantic model on demand.

Fields can also be bound to semantic roles (`title`, `date`, `published`,
`tags`, `description`). The blog uses roles to find the right field without
hardcoding its name, so a document can use `pubDate` instead of `date`.
"""

import copy
import dataclasses
import datetime
import pathlib
import re
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Annotated, Any, Self

import yaml


if TYPE_CHECKING:
  from pydantic import BaseModel


# Semantic roles the blog understands. Each role can be bound to one field.
# `status` is a generalization of `published` (TODO 5.7): a field with more
# states than just published/draft (e.g. draft/review/active/retired),
# with `FrontmatterSchema.published_values` saying which ones count as
# public. A schema binds one or the other, never both.
ROLES: tuple[str, ...] = (
  'title',
  'date',
  'published',
  'status',
  'tags',
  'description',
)

# Keys the blog sets on every post itself, so a field can't use them as a name.
RESERVED_NAMES: tuple[str, ...] = ('slug', 'content')

# How unknown frontmatter keys are handled (same names as in Pydantic).
EXTRA_MODES: tuple[str, ...] = ('forbid', 'allow', 'ignore')

# Supported field types and their Python annotations.
_TYPES: dict[str, Any] = {
  'str': str,
  'int': int,
  'float': float,
  'bool': bool,
  'datetime': datetime.datetime,
  'date': datetime.date,
  'list[str]': list[str],
  'list[int]': list[int],
  'dict': dict[str, Any],
  'any': Any,
}

# Types that may carry `min_length` / `max_length` constraints.
_LENGTH_TYPES: tuple[str, ...] = ('str', 'list[str]', 'list[int]')

# Types whose empty value is a container (a missing/null value becomes empty).
_CONTAINER_TYPES: tuple[str, ...] = ('list[str]', 'list[int]', 'dict')

# Allowed field types for each role.
_ROLE_TYPES: dict[str, tuple[str, ...]] = {
  'title': ('str',),
  'date': ('str', 'date', 'datetime'),
  'published': ('bool',),
  'status': ('str',),
  'tags': ('list[str]',),
  'description': ('str',),
}

# Values `on_create` accepts, and the field type each one needs.
_ON_CREATE_TYPES: dict[str, str] = {
  'today': 'date',
  'now': 'datetime',
  'uuid': 'str',
}

# Types `choices` is supported for.
_CHOICE_TYPES: tuple[str, ...] = (
  'str',
  'int',
  'float',
  'list[str]',
  'list[int]',
)

# Types `min`/`max` are supported for.
_MIN_MAX_TYPES: tuple[str, ...] = ('int', 'float')

# Types `min_items`/`max_items` are supported for.
_ITEMS_TYPES: tuple[str, ...] = ('list[str]', 'list[int]')


class _Missing:
  """Sentinel that means no default value was given."""

  def __repr__(self) -> str:
    return 'MISSING'


MISSING: Any = _Missing()


@dataclasses.dataclass(frozen=True)
class FieldSpec:
  """Description of a single frontmatter field.

  Attributes:
      name: Internal field name (a Python identifier).
      type: One of the supported type names, e.g. `str`, `bool`, `list[str]`.
      required: Whether the field must be present in the document.
      default: Value used when the field is absent (not for required fields).
      alias: External key used in the markdown file, if it differs from `name`.
      role: Semantic role the blog uses to find this field (see `ROLES`).
      min_length: Minimum length for `str` and list fields.
      max_length: Maximum length for `str` and list fields.
      description: Human-readable description of the field.
      read_only: When set, the storage layer rejects a write that changes
          this field's value on an existing document (new documents may
          still set it).
      on_create: `'today'`, `'now'` or `'uuid'`. Filled in automatically the
          first time the document is created, only if the field was left
          unset; never touched again afterwards (combine with `read_only`
          to make that permanent). `'today'`/`'now'` need a `date`/`datetime`
          field; `'uuid'` needs a `str` field.
      on_create_prefix: Prepended to the generated value when
          `on_create='uuid'` (e.g. `'note-'`). Not valid otherwise.
      label: Display label for the admin form and `check` messages (default:
          the field name).
      hint: Short help text shown next to the field in the admin form.
      hidden: When set, the field is not shown in the admin form (pairs well
          with `default`/`on_create`).
      choices: Allowed values: each item is a scalar, or `{value, label}`
          (`label` is display-only; the stored/validated value is `value`).
          For `list[str]`/`list[int]`, every element must be an allowed
          value. Valid for `str`, `int`, `float`, `list[str]`, `list[int]`.
      pattern: A regex string, or `[regex, message]` to show `message`
          instead of the default error. The whole value must match
          (`re.fullmatch`). Only valid for `type='str'`.
      item_pattern: Like `pattern`, but applied to every element of a
          `list[str]` field instead of the field itself.
      min: Minimum value, for `int`/`float` fields.
      max: Maximum value, for `int`/`float` fields.
      min_items: Minimum length, for `list[str]`/`list[int]` fields. Works
          independently of `max_items` (unlike some CMS tools, which only
          accept the pair together). Mutually exclusive with `min_length` on
          the same field.
      max_items: Maximum length, for `list[str]`/`list[int]` fields.
          Mutually exclusive with `max_length` on the same field.

  """

  name: str
  type: str = 'str'
  required: bool = False
  default: Any = MISSING
  alias: str | None = None
  role: str | None = None
  min_length: int | None = None
  max_length: int | None = None
  description: str | None = None
  read_only: bool = False
  on_create: str | None = None
  on_create_prefix: str | None = None
  label: str | None = None
  hint: str | None = None
  hidden: bool = False
  choices: tuple[Any, ...] | None = None
  pattern: str | tuple[str, str] | None = None
  item_pattern: str | tuple[str, str] | None = None
  min: int | float | None = None
  max: int | float | None = None
  min_items: int | None = None
  max_items: int | None = None

  def __post_init__(self) -> None:
    if not self.name.isidentifier() or self.name.startswith(('_', 'model_')):
      raise ValueError(
        f'Invalid field name {self.name!r}: use a Python identifier that '
        'does not start with `_` or `model_` (set `alias` for the real key)'
      )
    if self.name in RESERVED_NAMES:
      raise ValueError(
        f'Field name {self.name!r} is reserved by the blog: use another '
        f'name and set `alias={self.name!r}` to keep the key'
      )
    if self.type not in _TYPES:
      raise ValueError(
        f'Unknown type {self.type!r} for field {self.name!r}. '
        f'Supported types: {", ".join(_TYPES)}'
      )
    if self.alias is not None and not self.alias:
      raise ValueError(f'Empty alias for field {self.name!r}')
    if self.required and self.default is not MISSING:
      raise ValueError(f'Required field {self.name!r} cannot have a default')
    if self.on_create is not None:
      if self.on_create not in _ON_CREATE_TYPES:
        raise ValueError(
          f'Unknown on_create {self.on_create!r} for field {self.name!r}. '
          f'Supported values: {", ".join(_ON_CREATE_TYPES)}'
        )
      needed_type = _ON_CREATE_TYPES[self.on_create]
      if self.type != needed_type:
        raise ValueError(
          f'Field {self.name!r} has on_create={self.on_create!r}, which '
          f'needs type {needed_type!r}, got {self.type!r}'
        )
      if self.required:
        raise ValueError(
          f'Field {self.name!r} cannot be both `required` and `on_create`: '
          'on_create only fills a value that was left unset'
        )
    if self.on_create_prefix is not None and self.on_create != 'uuid':
      raise ValueError(
        f"`on_create_prefix` on field {self.name!r} needs on_create='uuid'"
      )
    if self.role is not None:
      if self.role not in ROLES:
        raise ValueError(
          f'Unknown role {self.role!r} for field {self.name!r}. '
          f'Supported roles: {", ".join(ROLES)}'
        )
      if self.type not in _ROLE_TYPES[self.role]:
        raise ValueError(
          f'Field {self.name!r} has role {self.role!r}, which needs type '
          f'{" or ".join(_ROLE_TYPES[self.role])}, got {self.type!r}'
        )
    has_length = self.min_length is not None or self.max_length is not None
    if has_length and self.type not in _LENGTH_TYPES:
      raise ValueError(
        f'`min_length`/`max_length` are not supported for type '
        f'{self.type!r} (field {self.name!r})'
      )
    if self.choices is not None:
      object.__setattr__(self, 'choices', tuple(self.choices))
      if not self.choices:
        raise ValueError(f'`choices` is empty for field {self.name!r}')
      if self.type not in _CHOICE_TYPES:
        raise ValueError(
          f'`choices` is not supported for type {self.type!r} '
          f'(field {self.name!r})'
        )
      for item in self.choices:
        if isinstance(item, Mapping) and 'value' not in item:
          raise ValueError(
            f'A `choices` item of field {self.name!r} is a mapping but has '
            "no 'value' key"
          )
    if self.pattern is not None:
      object.__setattr__(self, 'pattern', _normalize_pattern(self.pattern))
      if self.type != 'str':
        raise ValueError(
          f'`pattern` is not supported for type {self.type!r} '
          f'(field {self.name!r}); did you mean `item_pattern`?'
        )
    if self.item_pattern is not None:
      object.__setattr__(
        self, 'item_pattern', _normalize_pattern(self.item_pattern)
      )
      if self.type != 'list[str]':
        raise ValueError(
          f'`item_pattern` is not supported for type {self.type!r} '
          f"(field {self.name!r}); it needs type 'list[str]'"
        )
    has_min_max = self.min is not None or self.max is not None
    if has_min_max and self.type not in _MIN_MAX_TYPES:
      raise ValueError(
        f'`min`/`max` are not supported for type {self.type!r} '
        f'(field {self.name!r})'
      )
    has_items = self.min_items is not None or self.max_items is not None
    if has_items and self.type not in _ITEMS_TYPES:
      raise ValueError(
        f'`min_items`/`max_items` are not supported for type {self.type!r} '
        f'(field {self.name!r})'
      )
    if self.min_items is not None and self.min_length is not None:
      raise ValueError(
        f'Field {self.name!r} sets both `min_items` and `min_length`; use one'
      )
    if self.max_items is not None and self.max_length is not None:
      raise ValueError(
        f'Field {self.name!r} sets both `max_items` and `max_length`; use one'
      )

  @property
  def key(self) -> str:
    """Return the key used in the markdown file (alias or name)."""
    return self.alias or self.name

  def to_dict(self) -> dict[str, Any]:
    """Return non-default options as a plain dict (without the name)."""
    result: dict[str, Any] = {}
    for item in dataclasses.fields(self):
      if item.name == 'name':
        continue
      value = getattr(self, item.name)
      if value == item.default:
        continue
      result[item.name] = value
    return result


@dataclasses.dataclass(frozen=True)
class JsonLdConfig:
  """A schema's `jsonld` section (TODO 5.3): JSON-LD defaults for a collection.

  Nothing here is resolved or validated by this module — `fastapi_blog.jsonld`
  (TODO 5.4) is what turns a document into JSON-LD using it.

  Attributes:
      context: The `@context` value emitted as-is: an inline mapping, or a
          list of mappings/URLs. Loading `context` from a local file (TODO
          5.5, needs the `jsonld` extra) isn't implemented yet — pass the
          already-loaded mapping instead.
      base: Base IRI substituted into `id_template`'s `{base}` placeholder.
      id_template: Used for a document's `@id` when no field has
          `alias='@id'`. A plain `str.format()` template with `{base}`,
          `{collection}`, `{slug}` placeholders — not the full slug/template
          language from TODO 6.4 (not built), so filters and date tags
          aren't available here yet.
      type: Default `@type` when no field has `alias='@type'`.
      content_term: JSON-LD term the document body is emitted under (the
          raw Markdown, not rendered HTML). `None` (default) omits the body.

  """

  context: Any = None
  base: str | None = None
  id_template: str | None = None
  type: str | None = None
  content_term: str | None = None

  def to_dict(self) -> dict[str, Any]:
    """Return non-default options as a plain dict."""
    result: dict[str, Any] = {}
    for item in dataclasses.fields(self):
      value = getattr(self, item.name)
      if value != item.default:
        result[item.name] = value
    return result

  @classmethod
  def from_dict(cls, data: Mapping[str, Any]) -> 'JsonLdConfig':
    """Build from a plain dict (the `jsonld:` section of a schema file)."""
    known = {item.name for item in dataclasses.fields(cls)}
    unknown = set(data) - known
    if unknown:
      raise ValueError(f'Unknown jsonld option(s): {sorted(unknown)}')
    return cls(**data)


@dataclasses.dataclass(eq=False)
class FrontmatterSchema:
  """Set of frontmatter fields plus the policy for unknown keys.

  Attributes:
      fields: Field descriptions.
      extra: What to do with keys not listed in `fields`: `forbid` (error),
          `allow` (keep them) or `ignore` (drop them).
      published_values: Required when a field binds the `status` role
          (TODO 5.7): the `status` values that count as published. A
          document is public when its `status` field's value is one of
          these, instead of a plain `published: bool`. Mutually exclusive
          with binding the `published` role on the same schema.

  Example:
      ```python
      schema = FrontmatterSchema(
        fields=(
          FieldSpec(
            'title',
            required=True,
            role='title',
          ),
          FieldSpec(
            'pub_date',
            alias='pubDate',
            required=True,
            role='date',
          ),
          FieldSpec(
            'draft',
            type='bool',
            default=True,
          ),
        ),
        extra='allow',
      )
      Model = (
        schema.model()
      )
      ```

  """

  fields: tuple[FieldSpec, ...] = ()
  extra: str = 'forbid'
  jsonld: JsonLdConfig | None = None
  published_values: tuple[str, ...] | None = None
  _model: Any = dataclasses.field(default=None, init=False, repr=False)
  _payload_model: Any = dataclasses.field(default=None, init=False, repr=False)

  def __post_init__(self) -> None:
    self.fields = tuple(self.fields)
    if self.extra not in EXTRA_MODES:
      raise ValueError(
        f'Unknown extra mode {self.extra!r}. '
        f'Supported modes: {", ".join(EXTRA_MODES)}'
      )

    # Names and aliases share one namespace, so a document key is never
    # ambiguous.
    seen: dict[str, str] = {}
    for spec in self.fields:
      for token in {spec.name, spec.key}:
        if token in seen:
          raise ValueError(
            f'Key {token!r} of field {spec.name!r} clashes with '
            f'field {seen[token]!r}'
          )
        seen[token] = spec.name

    roles: dict[str, str] = {}
    for spec in self.fields:
      if spec.role is None:
        continue
      if spec.role in roles:
        raise ValueError(
          f'Role {spec.role!r} is bound to both {roles[spec.role]!r} '
          f'and {spec.name!r}'
        )
      roles[spec.role] = spec.name

    # The blog exposes a role under its own name (`post["date"]`), so no other
    # field may already use that name.
    names = {spec.name for spec in self.fields}
    for role, name in roles.items():
      if role != name and role in names:
        raise ValueError(
          f'Field {role!r} clashes with the role {role!r}, which is '
          f'bound to field {name!r}: rename it or set `alias`'
        )

    if self.published_values is not None:
      self.published_values = tuple(self.published_values)
    if 'published' in roles and 'status' in roles:
      raise ValueError(
        "Roles 'published' and 'status' are bound at the same time "
        f'(to {roles["published"]!r} and {roles["status"]!r}); a schema '
        'uses one or the other, not both'
      )
    if 'status' in roles and not self.published_values:
      raise ValueError(
        f"Field {roles['status']!r} has role 'status', which needs "
        '`published_values` on the schema (which status values count as '
        'published)'
      )
    if self.published_values and 'status' not in roles:
      raise ValueError(
        "`published_values` is set but no field has role 'status'"
      )

  def role_map(self) -> dict[str, str]:
    """Return a mapping from each bound role to its field name."""
    return {spec.role: spec.name for spec in self.fields if spec.role}

  def get(self, name: str) -> FieldSpec | None:
    """Return the field with the given internal name, if any."""
    for spec in self.fields:
      if spec.name == name:
        return spec
    return None

  def field_for_role(self, role: str) -> FieldSpec | None:
    """Return the field bound to the given role, if any."""
    for spec in self.fields:
      if spec.role == role:
        return spec
    return None

  def name_for_role(self, role: str) -> str | None:
    """Return the internal name of the field bound to the given role."""
    spec = self.field_for_role(role)
    if spec is None:
      return None
    return spec.name

  def with_extra(self, extra: str) -> 'FrontmatterSchema':
    """Return a copy of the schema with another `extra` mode."""
    return FrontmatterSchema(
      fields=self.fields, extra=extra, jsonld=self.jsonld
    )

  def model(self) -> 'type[BaseModel]':
    """Return the Pydantic model for this schema (built once, then cached)."""
    if self._model is None:
      self._model = _build_model(self)
    return self._model

  def payload_model(self) -> 'type[BaseModel]':
    """Return the REST API request model: `frontmatter` plus `content`.

    It is built once and cached, like `model()`.
    """
    if self._payload_model is None:
      self._payload_model = _build_payload_model(self)
    return self._payload_model

  def dump(
    self,
    instance: 'BaseModel',
    *,
    by_alias: bool = False,
    exclude_none: bool = True,
  ) -> dict[str, Any]:
    """Convert a validated model instance to a plain dict.

    Args:
        instance: Instance of the model returned by `model()`.
        by_alias: Use external keys (aliases) instead of internal names.
        exclude_none: Drop fields whose value is `None`.

    Returns:
        Dict with the frontmatter values.

    """
    return instance.model_dump(by_alias=by_alias, exclude_none=exclude_none)

  def dump_for_write(
    self,
    instance: 'BaseModel',
    *,
    is_create: bool,
    existing: Mapping[str, Any] | None = None,
  ) -> dict[str, Any]:
    """Dump a validated instance for writing to disk, applying 4.5 rules.

    On creation, every `on_create` field the caller left unset (not in
    `instance.model_fields_set`) is filled in now, once. On update, a
    `read_only` field whose value differs from `existing` is rejected: the
    caller may still send back the same value unchanged (full-replace
    payloads naturally echo it).

    Args:
        instance: Instance of the model returned by `model()`.
        is_create: Whether this is a new document (vs. an update).
        existing: The document's current frontmatter, by external key (as
            returned by `read_document`); ignored when `is_create`.

    Returns:
        Dict with the frontmatter values, by external key (alias).

    Raises:
        ValueError: A `read_only` field's value would change.

    """
    set_fields = instance.model_fields_set
    for spec in self.fields:
      if is_create:
        if spec.on_create and spec.name not in set_fields:
          setattr(instance, spec.name, _on_create_value(spec))
        continue
      if not spec.read_only or spec.name not in set_fields or existing is None:
        continue
      old_value = existing.get(spec.key, MISSING)
      if old_value is MISSING:
        continue
      if getattr(instance, spec.name) != old_value:
        raise ValueError(
          f'Field {spec.name!r} is read-only and cannot be changed'
        )
    return self.dump(instance, by_alias=True)

  def to_dict(self) -> dict[str, Any]:
    """Return the schema as a plain dict (the format `from_dict` reads)."""
    result: dict[str, Any] = {
      'extra': self.extra,
      'fields': {spec.name: spec.to_dict() for spec in self.fields},
    }
    if self.jsonld is not None:
      result['jsonld'] = self.jsonld.to_dict()
    if self.published_values is not None:
      result['published_values'] = list(self.published_values)
    return result

  @classmethod
  def from_dict(cls, data: Mapping[str, Any]) -> Self:
    """Build a schema from a plain dict.

    The dict has an optional `extra` key, a `fields` key, an optional
    `jsonld` key (TODO 5.3) and an optional `published_values` key (TODO
    5.7, see `FrontmatterSchema.published_values`). `fields` is either a
    mapping `{name: options}` or a list of `{name: ..., ...}`.

    Args:
        data: Schema description, e.g. loaded from YAML or JSON.

    Returns:
        The schema.

    Raises:
        ValueError: If the description is malformed.

    """
    if not isinstance(data, Mapping):
      raise ValueError('Schema description must be a mapping')
    data = dict(data)
    raw_fields = data.pop('fields', None) or {}
    extra = data.pop('extra', 'forbid')
    raw_jsonld = data.pop('jsonld', None)
    raw_published_values = data.pop('published_values', None)
    if data:
      raise ValueError(f'Unknown schema key(s): {sorted(data)}')

    specs: list[FieldSpec] = []
    if isinstance(raw_fields, Mapping):
      for name, options in raw_fields.items():
        specs.append(_parse_field(str(name), options))
    elif isinstance(raw_fields, list):
      for item in raw_fields:
        if not isinstance(item, Mapping) or 'name' not in item:
          raise ValueError('Each item in `fields` needs a `name`')
        options = {k: v for k, v in item.items() if k != 'name'}
        specs.append(_parse_field(str(item['name']), options))
    else:
      raise ValueError('`fields` must be a mapping or a list')
    jsonld = (
      JsonLdConfig.from_dict(raw_jsonld) if raw_jsonld is not None else None
    )
    published_values = (
      tuple(raw_published_values) if raw_published_values is not None else None
    )
    return cls(
      fields=tuple(specs),
      extra=extra,
      jsonld=jsonld,
      published_values=published_values,
    )

  @classmethod
  def from_file(cls, path: str | pathlib.Path) -> Self:
    """Load a schema from a YAML or JSON file (JSON is valid YAML)."""
    raw = pathlib.Path(path).read_text(encoding='utf-8')
    return cls.from_dict(yaml.safe_load(raw))


def _parse_field(name: str, options: Mapping[str, Any] | None) -> FieldSpec:
  if options is None:
    options = {}
  if not isinstance(options, Mapping):
    raise ValueError(f'Options of field {name!r} must be a mapping')
  known = {item.name for item in dataclasses.fields(FieldSpec)} - {'name'}
  unknown = set(options) - known
  if unknown:
    raise ValueError(f'Unknown option(s) {sorted(unknown)} for field {name!r}')
  return FieldSpec(name=name, **options)


def _normalize_pattern(pattern: str | tuple[str, str]) -> str | tuple[str, str]:
  """Normalize a `pattern`/`item_pattern` option and check it compiles.

  Accepts a bare regex string, or a `[regex, message]` pair (a list, if it
  came from YAML/JSON) for a custom error message; returns a `str` or a
  `tuple[str, str]`.
  """
  if isinstance(pattern, str):
    re.compile(pattern)
    return pattern
  regex, message = pattern
  re.compile(regex)
  return (regex, message)


def _choice_values(choices: tuple[Any, ...]) -> list[Any]:
  """Return the allowed values of a `choices` option (dropping UI labels)."""
  return [
    item['value'] if isinstance(item, Mapping) else item for item in choices
  ]


def _choices_validator(spec: FieldSpec) -> Callable[[Any], Any]:
  assert spec.choices is not None
  allowed = _choice_values(spec.choices)
  allowed_set = set(allowed)

  def validate(value: Any) -> Any:
    if value is None:
      return value
    if spec.type in _CONTAINER_TYPES:
      bad = [item for item in value if item not in allowed_set]
      if bad:
        raise ValueError(
          f'{spec.name}: invalid choice(s) {bad!r}; allowed: {allowed!r}'
        )
      return value
    if value not in allowed_set:
      raise ValueError(
        f'{spec.name}: invalid choice {value!r}; allowed: {allowed!r}'
      )
    return value

  return validate


def _pattern_validator(spec: FieldSpec) -> Callable[[Any], Any]:
  str_pattern = (
    _split_pattern(spec.pattern) if spec.pattern is not None else None
  )
  item_pattern = (
    _split_pattern(spec.item_pattern) if spec.item_pattern is not None else None
  )

  def validate(value: Any) -> Any:
    if value is None:
      return value
    if item_pattern is not None:
      regex, message = item_pattern
      for item in value:
        if not regex.fullmatch(str(item)):
          raise ValueError(
            message or f'{spec.name}: {item!r} does not match {regex.pattern!r}'
          )
      return value
    if str_pattern is not None:
      regex, message = str_pattern
      if not regex.fullmatch(value):
        raise ValueError(
          message or f'{spec.name}: {value!r} does not match {regex.pattern!r}'
        )
    return value

  return validate


def _split_pattern(
  pattern: str | tuple[str, str],
) -> tuple[re.Pattern[str], str | None]:
  if isinstance(pattern, str):
    return re.compile(pattern), None
  regex, message = pattern
  return re.compile(regex), message


def _implicit_default(spec: FieldSpec) -> Any:
  """Return the default used when a non-required field has none set."""
  if spec.default is not MISSING:
    return spec.default
  if spec.type == 'bool':
    return False
  if spec.type == 'dict':
    return {}
  if spec.type in _CONTAINER_TYPES:
    return []
  return None


def _on_create_value(spec: FieldSpec) -> Any:
  """Return the value an `on_create` field gets when left unset at creation."""
  if spec.on_create == 'today':
    return datetime.date.today()
  if spec.on_create == 'now':
    return datetime.datetime.now()
  if spec.on_create == 'uuid':
    import uuid

    value = uuid.uuid4().hex
    return f'{spec.on_create_prefix}{value}' if spec.on_create_prefix else value
  raise AssertionError(f'unreachable on_create: {spec.on_create!r}')


def _make_factory(value: Any) -> Callable[[], Any]:
  # A fresh copy per document, so mutable defaults are never shared.
  def factory() -> Any:
    return copy.deepcopy(value)

  return factory


def _none_to_default(factory: Callable[[], Any]) -> Callable[[Any], Any]:
  # `tags:` with no value is parsed by YAML as `None`; treat it as "empty".
  def convert(value: Any) -> Any:
    if value is None:
      return factory()
    return value

  return convert


def _build_model(schema: FrontmatterSchema) -> 'type[BaseModel]':
  from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    create_model,
  )

  reserved = set(dir(BaseModel))
  definitions: dict[str, Any] = {}
  for spec in schema.fields:
    if spec.name in reserved:
      raise ValueError(
        f'Field name {spec.name!r} clashes with a Pydantic attribute; '
        'choose another name and set `alias` to the real key'
      )

    annotation: Any = _TYPES[spec.type]
    options: dict[str, Any] = {}
    if spec.alias:
      options['alias'] = spec.alias
    if spec.min_length is not None:
      options['min_length'] = spec.min_length
    if spec.max_length is not None:
      options['max_length'] = spec.max_length
    if spec.min_items is not None:
      options['min_length'] = spec.min_items
    if spec.max_items is not None:
      options['max_length'] = spec.max_items
    if spec.min is not None:
      options['ge'] = spec.min
    if spec.max is not None:
      options['le'] = spec.max
    if spec.description:
      options['description'] = spec.description
    if spec.label:
      options['title'] = spec.label
    extra_meta: dict[str, Any] = {}
    if spec.hint:
      extra_meta['hint'] = spec.hint
    if spec.hidden:
      extra_meta['hidden'] = True
    if spec.choices is not None:
      # Surfaces in the generated JSON Schema as `enum` (TODO 5.7), even
      # though validation itself goes through `_choices_validator` below
      # (not Pydantic's own enum machinery, so a bad value's error names it).
      extra_meta['enum'] = _choice_values(spec.choices)
    if spec.pattern is not None:
      # Surfaces as `pattern` (TODO 5.7). Validation itself goes through
      # `_pattern_validator` below (fullmatch, optional custom message),
      # not Pydantic's own `Field(pattern=...)` (match, generic message).
      regex, _message = _split_pattern(spec.pattern)
      extra_meta['pattern'] = regex.pattern
    if extra_meta:
      options['json_schema_extra'] = extra_meta

    value_validators: list[Any] = []
    if spec.choices is not None:
      value_validators.append(AfterValidator(_choices_validator(spec)))
    if spec.pattern is not None or spec.item_pattern is not None:
      value_validators.append(AfterValidator(_pattern_validator(spec)))

    if spec.required:
      info = Field(..., **options)
    else:
      value = _implicit_default(spec)
      factory = _make_factory(value)
      if value is None:
        annotation = annotation | None
      if spec.type in _CONTAINER_TYPES:
        annotation = Annotated[  # type: ignore[valid-type]
          annotation, BeforeValidator(_none_to_default(factory))
        ]
      info = Field(default_factory=factory, **options)

    for validator in value_validators:
      annotation = Annotated[annotation, validator]  # type: ignore[valid-type]

    definitions[spec.name] = (annotation, info)

  # `extra` is validated in `FrontmatterSchema`, so the `str` is a valid literal.
  config = ConfigDict(
    extra=schema.extra,  # type: ignore[typeddict-item]
    populate_by_name=True,
  )
  return create_model('Frontmatter', __config__=config, **definitions)


def _build_payload_model(schema: FrontmatterSchema) -> 'type[BaseModel]':
  from pydantic import ConfigDict, Field, create_model

  return create_model(
    'PostPayload',
    __config__=ConfigDict(extra='forbid'),
    frontmatter=(schema.model(), ...),
    content=(str, Field(..., min_length=1)),
  )


# The schema that matches the original hardcoded behavior.
DEFAULT_SCHEMA = FrontmatterSchema(
  fields=(
    FieldSpec(
      'title', required=True, min_length=1, max_length=200, role='title'
    ),
    FieldSpec('date', required=True, min_length=1, role='date'),
    FieldSpec('published', type='bool', default=False, role='published'),
    FieldSpec('tags', type='list[str]', role='tags'),
    FieldSpec('description', role='description'),
  ),
  extra='forbid',
)

# Same fields, but unknown keys are kept (the old `strict_frontmatter=False`).
LOOSE_DEFAULT_SCHEMA = DEFAULT_SCHEMA.with_extra('allow')
