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
import string
import urllib.parse
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Annotated, Any, Self

import yaml

from ..templates import parse_template


if TYPE_CHECKING:
  from pydantic import BaseModel


# Semantic roles the blog understands. Each role can be bound to one field.
# `status` is a generalization of `published` (TODO 5.7): a field with more
# states than just published/draft (e.g. draft/review/active/retired),
# with `FrontmatterSchema.published_values` saying which ones count as
# public. A schema binds one or the other, never both.
#
# The SEO roles (TODO 5.9.1) feed `fastapi_blog.seo`: `seo_title` (falls
# back to `title`), `canonical` (explicit canonical URL), `robots` (meta
# robots directives), `image`/`image_alt` (social preview image),
# `updated` (falls back to `date`), `author`, `lang` (falls back to the
# request's interface locale) and `redirect_from` (previous URLs for a
# document, TODO 5.9.5). `fastapi_blog.seo.build_head()` reads them; a
# role bound to a field changes the page only when a `SeoConfig` is in effect
# (`redirect_from` additionally needs `seo_routes=True`).
ROLES: tuple[str, ...] = (
  'title',
  'date',
  'published',
  'status',
  'tags',
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
)

# Keys the blog sets on every post itself, so a field can't use them as a name.
RESERVED_NAMES: tuple[str, ...] = ('slug', 'content')

# Robots directives search engines actually act on (TODO 5.9): used by the
# `robots` role's `choices`, `SeoConfig.default_robots` and the meta output.
ROBOTS_DIRECTIVES: tuple[str, ...] = (
  'noindex',
  'nofollow',
  'noarchive',
  'nosnippet',
)

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
  # A link points to another resource: a slug of the same collection, a
  # compact IRI (`prefix:name`) or an absolute IRI. It is stored and
  # checked like `str`; `collection`/`value_field`/`filters` describe the
  # target for the link check (TODO 6.1) and the admin autocomplete.
  'link': str,
  'list[link]': list[str],
  # A file or an image is a path kept as a string (the public path).
  'file': str,
  'image': str,
  'dict': dict[str, Any],
  'any': Any,
}

# Types that may carry `min_length` / `max_length` constraints.
_LENGTH_TYPES: tuple[str, ...] = (
  'str',
  'link',
  'file',
  'image',
  'list[str]',
  'list[int]',
  'list[link]',
)

# Types whose empty value is a container (a missing/null value becomes empty).
_CONTAINER_TYPES: tuple[str, ...] = (
  'list[str]',
  'list[int]',
  'list[link]',
  'dict',
)

# Allowed field types for each role.
_ROLE_TYPES: dict[str, tuple[str, ...]] = {
  'title': ('str',),
  'date': ('str', 'date', 'datetime'),
  'published': ('bool',),
  'status': ('str',),
  'tags': ('list[str]',),
  'description': ('str',),
  'seo_title': ('str',),
  'canonical': ('str',),
  'robots': ('list[str]',),
  'image': ('str',),
  'image_alt': ('str',),
  'updated': ('str', 'date', 'datetime'),
  'author': ('str', 'list[str]'),
  'lang': ('str',),
  'redirect_from': ('list[str]',),
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
  'link',
  'file',
  'image',
  'int',
  'float',
  'list[str]',
  'list[int]',
  'list[link]',
)

# Types `min`/`max` are supported for.
_MIN_MAX_TYPES: tuple[str, ...] = ('int', 'float')

# Types `min_items`/`max_items` are supported for.
_ITEMS_TYPES: tuple[str, ...] = ('list[str]', 'list[int]', 'list[link]')


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
      collection: For `link` fields: the target collection (default: the
          same one).
      value_field: For `link` fields: the target field whose value is stored
          (default: the field with the alias `@id`, else the slug).
      filters: For `link` fields: a list of `{field, values}`; only
          documents whose field has one of the values are valid targets.
      media_dir: For `file`/`image` fields: the directory of the files,
          relative to the project root (no absolute paths, no `..`).
      public_path: For `file`/`image` fields: the prefix of the stored path
          (default: `media_dir`). Needs `media_dir`.

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
  collection: str | None = None
  value_field: str | None = None
  filters: tuple[dict[str, Any], ...] | None = None
  media_dir: str | None = None
  public_path: str | None = None

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
      if self.type not in ('str', 'link', 'file', 'image'):
        raise ValueError(
          f'`pattern` is not supported for type {self.type!r} '
          f'(field {self.name!r}); did you mean `item_pattern`?'
        )
    if self.item_pattern is not None:
      object.__setattr__(
        self, 'item_pattern', _normalize_pattern(self.item_pattern)
      )
      if self.type not in ('list[str]', 'list[link]'):
        raise ValueError(
          f'`item_pattern` is not supported for type {self.type!r} '
          f"(field {self.name!r}); it needs type 'list[str]' or 'list[link]'"
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
    self._check_link_options()
    self._check_file_options()

  def _check_link_options(self) -> None:
    """Validate `collection`/`value_field`/`filters` (TODO 5.1 link type)."""
    options = ('collection', 'value_field', 'filters')
    if not self.is_link:
      for option in options:
        if getattr(self, option) is not None:
          raise ValueError(
            f'`{option}` needs a `link` or `list[link]` field, got '
            f'{self.type!r} (field {self.name!r})'
          )
      return
    for option in ('collection', 'value_field'):
      value = getattr(self, option)
      if value is not None and (not isinstance(value, str) or not value):
        raise ValueError(f'`{option}` of field {self.name!r} must be a string')
    if self.filters is None:
      return
    if not isinstance(self.filters, list | tuple) or not self.filters:
      raise ValueError(f'`filters` of field {self.name!r} must be a list')
    cleaned: list[dict[str, Any]] = []
    for item in self.filters:
      if (
        not isinstance(item, Mapping)
        or set(item) != {'field', 'values'}
        or not isinstance(item['field'], str)
        or not isinstance(item['values'], list | tuple)
        or not item['values']
      ):
        raise ValueError(
          f'Each filter of field {self.name!r} must be '
          '`{field: NAME, values: [...]}`'
        )
      cleaned.append({'field': item['field'], 'values': list(item['values'])})
    object.__setattr__(self, 'filters', tuple(cleaned))

  def _check_file_options(self) -> None:
    """Validate `media_dir`/`public_path` (TODO 5.1 file/image types)."""
    for option in ('media_dir', 'public_path'):
      value = getattr(self, option)
      if value is None:
        continue
      if self.type not in ('file', 'image'):
        raise ValueError(
          f'`{option}` needs a `file` or `image` field, got {self.type!r} '
          f'(field {self.name!r})'
        )
      if not isinstance(value, str) or not value:
        raise ValueError(f'`{option}` of field {self.name!r} must be a string')
    if self.public_path is not None and self.media_dir is None:
      raise ValueError(f'`public_path` needs `media_dir` (field {self.name!r})')
    if self.media_dir is not None and (
      self.media_dir.startswith('/') or '..' in self.media_dir.split('/')
    ):
      raise ValueError(
        f'`media_dir` of field {self.name!r} must be a relative path inside '
        'the project'
      )

  @property
  def key(self) -> str:
    """Return the key used in the markdown file (alias or name)."""
    return self.alias or self.name

  @property
  def is_link(self) -> bool:
    """Return whether the field holds links (`link` or `list[link]`)."""
    return self.type in ('link', 'list[link]')

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

  Attributes:
      context: The `@context` value: an inline mapping, a path to a file
          inside the project root, a URL (only with `allow_remote_contexts`),
          or a list of them. Files and URLs are loaded by
          `fastapi_blog.jsonld.resolve_context` (TODO 5.5); nothing in a
          context is ever executed.
      base: Base IRI substituted into `id_template`'s `{base}` placeholder.
      id_template: Used for a document's `@id` when no field has
          `alias='@id'`. A plain `str.format()` template with `{base}`,
          `{collection}`, `{slug}` placeholders — not the full slug/template
          language from TODO 6.4 (not built), so filters and date tags
          aren't available here yet.
      type: Default `@type` when no field has `alias='@type'`.
      content_term: JSON-LD term the document body is emitted under (the
          raw Markdown, not rendered HTML). `None` (default) omits the body.
      allow_remote_contexts: URLs of remote contexts that may be fetched
          (TODO 5.5). Needs the `jsonld` extra; the default is no remote
          contexts at all.
      max_context_bytes: Size limit of one context, in bytes.
      max_documents: Limit of documents in one exported `@graph`.

  """

  context: Any = None
  base: str | None = None
  id_template: str | None = None
  type: str | None = None
  content_term: str | None = None
  allow_remote_contexts: tuple[str, ...] = ()
  max_context_bytes: int = 262144
  max_documents: int = 10000

  def __post_init__(self) -> None:
    object.__setattr__(
      self, 'allow_remote_contexts', tuple(self.allow_remote_contexts)
    )
    for url in self.allow_remote_contexts:
      if not isinstance(url, str) or not url.startswith(
        ('https://', 'http://')
      ):
        raise ValueError(
          f'`jsonld.allow_remote_contexts` must list http(s) URLs, got {url!r}'
        )
    for key in ('max_context_bytes', 'max_documents'):
      value = getattr(self, key)
      if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f'`jsonld.{key}` must be a positive integer')

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
    values = dict(data)
    if 'allow_remote_contexts' in values:
      values['allow_remote_contexts'] = tuple(
        values['allow_remote_contexts'] or ()
      )
    return cls(**values)


def is_http_url_or_root_path(value: Any) -> bool:
  """Return whether `value` is an `http(s)` URL or a path from the site root.

  The same rule applies to the `canonical` and `image` roles and to
  `seo.default_image` (TODO 5.9.4): anything else (`javascript:`, `data:`,
  a protocol-relative `//host`, a relative path) is rejected.
  """
  if not isinstance(value, str) or not value or value != value.strip():
    return False
  if value.startswith('/'):
    return not value.startswith('//') and '\\' not in value
  parts = urllib.parse.urlsplit(value)
  return parts.scheme in ('http', 'https') and bool(parts.netloc)


# Names a `seo.title_template` may use (until TODO 6.4's template language).
TITLE_TEMPLATE_NAMES = ('title', 'site_name')


def _check_title_template(template: str) -> None:
  """Raise `ValueError` unless `template` only has plain known placeholders."""
  try:
    parsed = list(string.Formatter().parse(template))
  except ValueError as exc:
    raise ValueError(f'`seo.title_template` is malformed: {exc}') from exc
  for _literal, field_name, format_spec, conversion in parsed:
    if field_name is None:
      continue
    if field_name not in TITLE_TEMPLATE_NAMES or format_spec or conversion:
      raise ValueError(
        f'`seo.title_template` has an unsupported placeholder '
        f'{{{field_name}}}; allowed: '
        + ', '.join(f'{{{name}}}' for name in TITLE_TEMPLATE_NAMES)
      )


@dataclasses.dataclass(frozen=True)
class SeoConfig:
  """A schema's `seo` section (TODO 5.9.2): site-wide SEO settings.

  With no `seo` section and no `seo=` argument the blog behaves as before
  TODO 5.9 (П6: only the 5.9.6 fixes apply). The substitution order and the
  `<head>`/social-tag output that consume these settings are TODO 5.9.3 and
  5.9.4 (`fastapi_blog.seo.build_head`). Value errors carry the offending
  `seo.<key>` name.

  Attributes:
      site_url: Base of absolute addresses; in production set it always.
          Without it, absolute addresses are built from the request URL.
      site_name: Site name, used by `title_template` and the page header.
      title_template: Applied to a non-empty title, e.g.
          `'{title} - {site_name}'`. Until TODO 6.4 lands this is a plain
          `str.format()` template with the same names.
      default_image: Fallback for the `image` role (og:image and friends).
      default_author: Fallback for the `author` role.
      default_robots: Merged with a document's `robots` role value; only
          `noindex`/`nofollow`/`noarchive`/`nosnippet` are allowed.
      index_description: Description for the index and list pages.
      og: Emit Open Graph tags (only when the tag has a value).
      twitter_card: `summary`, `summary_large_image` or `None` (off).
      structured_data: `blogposting`, `article` or `none` (default).
      description_fallback: `excerpt` (first `description_length` characters
          of the plain-text body) or `none` (default).
      description_length: Length cap for the excerpt fallback.
      noindex_tags: Give tag pages a `robots` `noindex` directive.
      disallow: URL paths emitted as `Disallow` directives in robots.txt.

  """

  site_url: str | None = None
  site_name: str | None = None
  title_template: str | None = None
  default_image: str | None = None
  default_author: str | None = None
  default_robots: tuple[str, ...] = ()
  index_description: str | None = None
  og: bool = False
  twitter_card: str | None = None
  structured_data: str = 'none'
  description_fallback: str = 'none'
  description_length: int = 160
  noindex_tags: bool = False
  disallow: tuple[str, ...] = ()

  def __post_init__(self) -> None:
    if isinstance(self.default_robots, str) or not isinstance(
      self.default_robots, (list, tuple)
    ):
      raise ValueError('`seo.default_robots` must be a list of directives')
    object.__setattr__(self, 'default_robots', tuple(self.default_robots))
    for key in (
      'site_url',
      'site_name',
      'title_template',
      'default_image',
      'default_author',
      'index_description',
    ):
      value = getattr(self, key)
      if value is not None and (not isinstance(value, str) or not value):
        raise ValueError(f'`seo.{key}` must be a non-empty string')
    if self.site_url is not None:
      parts = urllib.parse.urlsplit(self.site_url)
      if (
        parts.scheme not in ('http', 'https')
        or not parts.netloc
        or parts.query
        or parts.fragment
      ):
        raise ValueError(
          '`seo.site_url` must be an http(s):// URL without a query or '
          f'fragment, got {self.site_url!r}'
        )
      # One spelling, so absolute addresses are built the same way
      # everywhere (`https://example.org/` and `https://example.org`).
      object.__setattr__(self, 'site_url', self.site_url.rstrip('/'))
    if self.default_image is not None and not is_http_url_or_root_path(
      self.default_image
    ):
      raise ValueError(
        '`seo.default_image` must be an http(s):// URL or a path from the '
        f'site root, got {self.default_image!r}'
      )
    if self.title_template is not None:
      _check_title_template(self.title_template)
    if isinstance(self.disallow, str) or not isinstance(
      self.disallow, (list, tuple)
    ):
      raise ValueError('`seo.disallow` must be a list of URL paths')
    object.__setattr__(self, 'disallow', tuple(self.disallow))
    for path in self.disallow:
      if (
        not isinstance(path, str)
        or not path.startswith('/')
        or any(char.isspace() for char in path)
      ):
        raise ValueError(
          '`seo.disallow` entries must be URL paths from the site root '
          f'without whitespace, got {path!r}'
        )
    for directive in self.default_robots:
      if directive not in ROBOTS_DIRECTIVES:
        raise ValueError(
          f'`seo.default_robots` has unknown directive {directive!r}; '
          f'allowed: {", ".join(ROBOTS_DIRECTIVES)}'
        )
    if self.twitter_card not in (None, 'summary', 'summary_large_image'):
      raise ValueError(
        '`seo.twitter_card` must be summary, summary_large_image or null'
      )
    if self.structured_data not in ('blogposting', 'article', 'none'):
      raise ValueError(
        '`seo.structured_data` must be blogposting, article or none'
      )
    if self.description_fallback not in ('excerpt', 'none'):
      raise ValueError('`seo.description_fallback` must be excerpt or none')
    if (
      not isinstance(self.description_length, int)
      or isinstance(self.description_length, bool)
      or self.description_length < 1
    ):
      raise ValueError('`seo.description_length` must be a positive integer')
    for key in ('og', 'noindex_tags'):
      if not isinstance(getattr(self, key), bool):
        raise ValueError(f'`seo.{key}` must be true or false')

  def to_dict(self) -> dict[str, Any]:
    """Return non-default options as a plain dict."""
    result: dict[str, Any] = {}
    for item in dataclasses.fields(self):
      value = getattr(self, item.name)
      if value != item.default:
        result[item.name] = value
    return result

  @classmethod
  def from_dict(cls, data: Mapping[str, Any]) -> 'SeoConfig':
    """Build from a plain dict (the `seo:` section of a schema file)."""
    if not isinstance(data, Mapping):
      raise ValueError('`seo` must be a mapping')
    known = {item.name for item in dataclasses.fields(cls)}
    unknown = set(data) - known
    if unknown:
      raise ValueError(f'Unknown seo option(s): {sorted(unknown)}')
    values = dict(data)
    for key in ('default_robots', 'disallow'):
      if key in values and values[key] is None:
        values[key] = ()
    return cls(**values)


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
  seo: SeoConfig | None = None
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
    if self.jsonld is not None and self.jsonld.id_template is not None:
      try:
        parse_template(
          self.jsonld.id_template,
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
          {spec.name for spec in self.fields},
        )
      except ValueError as exc:
        raise ValueError(f'`jsonld.id_template`: {exc}') from exc

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
      fields=self.fields,
      extra=extra,
      jsonld=self.jsonld,
      seo=self.seo,
      published_values=self.published_values,
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
        Dict with the frontmatter values, by external key (alias). On an
        update with `existing` given, the dump is merged over the file's
        current frontmatter (see `_merge_for_rewrite`): the file's key
        order and, with `extra: 'allow'`, its unknown keys are preserved.

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
    dumped = self.dump(instance, by_alias=True)
    if is_create or existing is None:
      return dumped
    return self._merge_for_rewrite(dumped, existing)

  def _merge_for_rewrite(
    self, dumped: dict[str, Any], existing: Mapping[str, Any]
  ) -> dict[str, Any]:
    """Merge an update dump over the document's current frontmatter (4.5).

    Known keys take their new values in the positions they already occupy;
    a known key emptied to `None` is not written back; unknown keys survive
    only when `extra` is `'allow'`; schema fields the file doesn't have yet
    are appended in schema order. `existing` is keyed by external key, as
    read from the file.

    Args:
        dumped: The update dump (`by_alias`); values are never `None`.
        existing: The document's current frontmatter, by external key.

    Returns:
        The frontmatter to write, in the file's original key order.

    """
    schema_keys = {spec.key for spec in self.fields}
    merged: dict[str, Any] = {}
    for key, value in existing.items():
      if key in dumped:
        merged[key] = dumped.pop(key)
      elif key in schema_keys:
        continue  # Known field emptied to None: dropped, not written back.
      elif self.extra == 'allow':
        merged[key] = value
    merged.update(dumped)
    return merged

  def to_dict(self) -> dict[str, Any]:
    """Return the schema as a plain dict (the format `from_dict` reads)."""
    result: dict[str, Any] = {
      'extra': self.extra,
      'fields': {spec.name: spec.to_dict() for spec in self.fields},
    }
    if self.jsonld is not None:
      result['jsonld'] = self.jsonld.to_dict()
    if self.seo is not None:
      result['seo'] = self.seo.to_dict()
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
    raw_seo = data.pop('seo', None)
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
    seo = SeoConfig.from_dict(raw_seo) if raw_seo is not None else None
    published_values = (
      tuple(raw_published_values) if raw_published_values is not None else None
    )
    return cls(
      fields=tuple(specs),
      extra=extra,
      jsonld=jsonld,
      seo=seo,
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
