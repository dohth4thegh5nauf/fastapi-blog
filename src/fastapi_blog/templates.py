"""The template language shared by slugs, summaries and validators.

One syntax, used by `slug_template`, `summary` and the arguments of
`validators`:

    {name}                  a service tag or a frontmatter field
    {fields.name}           a frontmatter field (the explicit form, for when a
                            field is called like a service tag)
    {name|filter(arg)|...}  a chain of filters

Filters: `lower`, `upper`, `truncate(n)`, `default(x)`, `pad(n)` (zero-pad
on the left) and `date(format)` (`strftime`). Expressions are never
evaluated: an unknown tag or filter is a configuration error found when the
template is parsed (that is, when the project file is loaded).

Service tags are `slug`, `title_slug`, `seq`, `year`, `month`, `day`,
`dirname`, `filename`, `collection`, `base`, `path` and `locale`; each use
of a template allows only the tags that make sense there.
"""

import dataclasses
import datetime
import re
import unicodedata
from collections.abc import Collection as AbstractCollection
from collections.abc import Iterable, Mapping
from typing import Any


SERVICE_TAGS: tuple[str, ...] = (
  'slug',
  'title_slug',
  'seq',
  'year',
  'month',
  'day',
  'dirname',
  'filename',
  'collection',
  'base',
  'path',
  'locale',
)

# Tags allowed in a `slug_template`.
SLUG_TAGS_DEFAULT: tuple[str, ...] = (
  'seq',
  'title_slug',
  'year',
  'month',
  'day',
  'collection',
  'dirname',
)

# Tags allowed in a `summary` template.
SUMMARY_TAGS: tuple[str, ...] = ('slug', 'collection', 'dirname', 'filename')

# Longest file name (without the directory) in bytes.
MAX_FILE_NAME_BYTES = 200

_TAG = re.compile(r'\{([^{}]*)\}')
_FILTER = re.compile(r'^([a-z_]+)(?:\((.*)\))?$', re.DOTALL)
_FILTER_NAMES = ('lower', 'upper', 'truncate', 'default', 'pad', 'date')
_NEEDS_ARGUMENT = ('truncate', 'default', 'pad', 'date')


@dataclasses.dataclass(frozen=True)
class SlugOptions:
  """How `title_slug` is made (the `slug` section of a collection).

  Attributes:
      encoding: `unicode` keeps letters of any script; `ascii` keeps only
          `a-z` and `0-9`.
      clean_accents: Turn `é` into `e` before anything else.
      sanitize_replacement: What replaces every run of other characters.

  """

  encoding: str = 'unicode'
  clean_accents: bool = False
  sanitize_replacement: str = '-'

  def __post_init__(self) -> None:
    if self.encoding not in ('unicode', 'ascii'):
      raise ValueError(
        f'`slug.encoding` must be unicode or ascii, got {self.encoding!r}'
      )
    if not isinstance(self.clean_accents, bool):
      raise ValueError('`slug.clean_accents` must be true or false')
    if not isinstance(self.sanitize_replacement, str):
      raise ValueError('`slug.sanitize_replacement` must be a string')

  @classmethod
  def from_dict(cls, data: Mapping[str, Any]) -> 'SlugOptions':
    """Build the options from the collection's `slug` mapping."""
    if not isinstance(data, Mapping):
      raise ValueError('`slug` must be a mapping')
    unknown = set(data) - {'encoding', 'clean_accents', 'sanitize_replacement'}
    if unknown:
      raise ValueError(f'Unknown key(s) {sorted(unknown)} in `slug`')
    return cls(**data)

  def to_dict(self) -> dict[str, Any]:
    """Return the non-default options as a plain dict."""
    default = SlugOptions()
    return {
      item.name: getattr(self, item.name)
      for item in dataclasses.fields(self)
      if getattr(self, item.name) != getattr(default, item.name)
    }


def cut_bytes(text: str, limit: int) -> str:
  """Cut a string to at most `limit` UTF-8 bytes without splitting a char."""
  return text.encode('utf-8')[:limit].decode('utf-8', 'ignore')


def make_slug_part(text: str, options: SlugOptions | None = None) -> str:
  """Turn a title into a slug part (the value of `{title_slug}`).

  Steps: optionally drop accents; lowercase; replace each run of characters
  outside the allowed set (letters and digits of any script for `unicode`,
  `a-z0-9` for `ascii`) with the replacement; trim the replacement at both
  ends; cut to the file name limit. An empty result is `untitled`.
  """
  options = options or SlugOptions()
  if options.clean_accents or options.encoding == 'ascii':
    decomposed = unicodedata.normalize('NFKD', text)
    text = ''.join(ch for ch in decomposed if not unicodedata.combining(ch))
  text = unicodedata.normalize('NFC', text).lower()
  allowed = r'[^a-z0-9]+' if options.encoding == 'ascii' else r'[\W_]+'
  replacement = options.sanitize_replacement
  slug = re.sub(allowed, replacement, text)
  if replacement:
    slug = slug.strip(replacement)
  slug = cut_bytes(slug, MAX_FILE_NAME_BYTES)
  if replacement:
    slug = slug.strip(replacement)
  return slug or 'untitled'


@dataclasses.dataclass(frozen=True)
class Expression:
  """One `{...}` tag: where the value comes from and the filters to apply."""

  tag: str
  field: str | None
  filters: tuple[tuple[str, str | None], ...]


def _split_top_level(text: str, separator: str) -> list[str]:
  parts: list[str] = []
  depth = 0
  current: list[str] = []
  for char in text:
    if char == '(':
      depth += 1
    elif char == ')':
      depth -= 1
    if char == separator and depth == 0:
      parts.append(''.join(current))
      current = []
    else:
      current.append(char)
  parts.append(''.join(current))
  return parts


def _parse_expression(
  source: str,
  tags: AbstractCollection[str],
  field_names: AbstractCollection[str],
) -> Expression:
  head, *raw_filters = _split_top_level(source.strip(), '|')
  name = head.strip()
  field: str | None = None
  if name.startswith('fields.'):
    field = name[len('fields.') :]
    if field not in field_names:
      raise ValueError(f'unknown field in {{{source}}}: {field!r}')
    tag = 'fields'
  elif name in tags:
    tag = name
  elif name in field_names:
    tag, field = 'fields', name
  else:
    allowed = ', '.join(sorted(tags))
    raise ValueError(
      f'unknown tag {{{name}}}: use {allowed}, a field name or {{fields.NAME}}'
    )
  filters: list[tuple[str, str | None]] = []
  for item in raw_filters:
    match = _FILTER.match(item.strip())
    if match is None or match.group(1) not in _FILTER_NAMES:
      raise ValueError(f'unknown filter {item.strip()!r} in {{{source}}}')
    fname, arg = match.group(1), match.group(2)
    if fname in _NEEDS_ARGUMENT and arg is None:
      raise ValueError(f'filter `{fname}` needs an argument in {{{source}}}')
    if fname not in _NEEDS_ARGUMENT and arg is not None:
      raise ValueError(f'filter `{fname}` takes no argument in {{{source}}}')
    if fname in ('truncate', 'pad') and not (arg or '').strip().isdigit():
      raise ValueError(f'filter `{fname}` needs a number in {{{source}}}')
    if arg is not None:
      arg = arg.strip()
      if len(arg) >= 2 and arg[0] == arg[-1] and arg[0] in '\'"':
        arg = arg[1:-1]
    filters.append((fname, arg))
  return Expression(tag, field, tuple(filters))


def _format_value(value: Any) -> str:
  if value is None:
    return ''
  if isinstance(value, bool):
    return 'true' if value else 'false'
  if isinstance(value, datetime.datetime | datetime.date):
    return value.isoformat()
  return str(value)


def _apply_filter(name: str, arg: str | None, value: Any) -> Any:
  if name == 'default':
    return value if _format_value(value) != '' else arg
  if name == 'date':
    moment: Any = value
    if isinstance(value, str):
      try:
        moment = datetime.datetime.fromisoformat(value)
      except ValueError:
        return value
    if isinstance(moment, datetime.date | datetime.datetime):
      return moment.strftime(arg or '')
    return value
  text = _format_value(value)
  if name == 'lower':
    return text.lower()
  if name == 'upper':
    return text.upper()
  if name == 'truncate':
    return text[: int(arg or 0)]
  if name == 'pad':
    return text.zfill(int(arg or 0))
  return text


@dataclasses.dataclass(frozen=True)
class Template:
  """A parsed template.

  Attributes:
      source: The template text.
      tags: The service tags used (`fields` stands for any field).
      fields: Names of the frontmatter fields used.

  """

  source: str
  _parts: tuple[str | Expression, ...]

  @property
  def tags(self) -> frozenset[str]:
    """Return the tags used (`fields` stands for any frontmatter field)."""
    return frozenset(p.tag for p in self._parts if isinstance(p, Expression))

  @property
  def fields(self) -> frozenset[str]:
    """Return the names of the frontmatter fields used."""
    return frozenset(
      p.field
      for p in self._parts
      if isinstance(p, Expression) and p.field is not None
    )

  def render(
    self, tags: Mapping[str, Any], fields: Mapping[str, Any] | None = None
  ) -> str:
    """Render the template.

    Args:
        tags: Values of the service tags.
        fields: Values of the frontmatter fields by internal name.

    A missing value renders as an empty string (use `default(x)` to change
    that); nothing is evaluated.

    """
    fields = fields or {}
    out: list[str] = []
    for part in self._parts:
      if isinstance(part, str):
        out.append(part)
        continue
      if part.tag == 'fields':
        value = fields.get(part.field) if part.field is not None else None
      else:
        value = tags.get(part.tag)
      for name, arg in part.filters:
        value = _apply_filter(name, arg, value)
      out.append(_format_value(value))
    return ''.join(out)

  def slug_regex(self) -> re.Pattern[str]:
    """Return a regex that recognises slugs made by this template.

    Named groups `seq` and `title_slug` are captured; every other tag
    matches loosely. It is used to find the highest number in existing
    file names.
    """
    pattern = ''
    captured: set[str] = set()
    for part in self._parts:
      if isinstance(part, str):
        pattern += re.escape(part)
      elif part.tag == 'seq':
        if 'seq' in captured:
          raise ValueError('slug_template may contain {seq} only once')
        captured.add('seq')
        width = 1
        for name, arg in part.filters:
          if name == 'pad':
            width = max(width, int(arg or 1))
        pattern += rf'(?P<seq>\d{{{width},}})'
      elif part.tag == 'title_slug':
        if 'title_slug' in captured:
          raise ValueError('slug_template may contain {title_slug} only once')
        captured.add('title_slug')
        pattern += r'(?P<title_slug>[^/]+?)'
      elif part.tag in ('year', 'month', 'day'):
        pattern += r'\d+'
      else:
        pattern += r'[^/]*?'
    return re.compile(pattern)


def parse_template(
  source: str,
  tags: AbstractCollection[str],
  field_names: AbstractCollection[str] = (),
) -> Template:
  """Parse a template and check its tags and filters.

  Args:
      source: Template text.
      tags: Service tags allowed in this use.
      field_names: Frontmatter field names that may be used.

  Raises:
      ValueError: If a tag or a filter is unknown, or a brace is stray.

  """
  if not isinstance(source, str):
    raise ValueError('a template must be a string')
  parts: list[str | Expression] = []
  position = 0
  for match in _TAG.finditer(source):
    literal = source[position : match.start()]
    if '{' in literal or '}' in literal:
      raise ValueError(f'stray brace in template {source!r}')
    if literal:
      parts.append(literal)
    parts.append(_parse_expression(match.group(1), tags, field_names))
    position = match.end()
  tail = source[position:]
  if '{' in tail or '}' in tail:
    raise ValueError(f'stray brace in template {source!r}')
  if tail:
    parts.append(tail)
  return Template(source, tuple(parts))


def next_seq(template: Template, slugs: Iterable[str]) -> int:
  """Return the next number: the highest number in `slugs` plus one."""
  regex = template.slug_regex()
  highest = 0
  for slug in slugs:
    match = regex.fullmatch(slug)
    if match is not None and 'seq' in match.groupdict():
      highest = max(highest, int(match.group('seq')))
  return highest + 1


def build_slug(
  template: Template,
  *,
  title: str,
  fields: Mapping[str, Any] | None = None,
  collection: str = '',
  existing_slugs: Iterable[str] = (),
  date_value: Any = None,
  created_at: datetime.datetime | None = None,
  dirname: str = '',
  options: SlugOptions | None = None,
  sequence: int | None = None,
) -> str:
  """Render a new document slug from a parsed collection template.

  `created_at` is the first-save timestamp in UTC and is used only when the
  schema has no date value. The caller must hold its collection's write lock
  while obtaining `existing_slugs` and persisting the returned slug.
  """
  now = created_at or datetime.datetime.now(datetime.UTC)
  if now.tzinfo is None:
    now = now.replace(tzinfo=datetime.UTC)
  else:
    now = now.astimezone(datetime.UTC)
  moment = date_value or now
  if isinstance(moment, str):
    try:
      moment = datetime.datetime.fromisoformat(moment.replace('Z', '+00:00'))
    except ValueError:
      moment = now
  if isinstance(moment, datetime.datetime):
    if moment.tzinfo is None:
      moment = moment.replace(tzinfo=datetime.UTC)
    moment = moment.astimezone(datetime.UTC)
  elif isinstance(moment, datetime.date):
    moment = datetime.datetime.combine(
      moment, datetime.time(), tzinfo=datetime.UTC
    )
  else:
    moment = now
  values = dict(fields or {})
  if sequence is not None and (
    not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1
  ):
    raise ValueError('sequence must be a positive integer')
  tags = {
    'seq': sequence
    if sequence is not None
    else next_seq(template, existing_slugs),
    'title_slug': make_slug_part(title, options),
    'year': moment.year,
    'month': f'{moment.month:02d}',
    'day': f'{moment.day:02d}',
    'collection': collection,
    'dirname': dirname,
  }
  rendered = template.render(tags, values)
  if dirname and not rendered.startswith(dirname + '/'):
    rendered = f'{dirname}/{rendered}'
  parts = rendered.split('/')
  if any(not part or part in ('.', '..') for part in parts):
    raise ValueError(f'slug template produced an invalid path: {rendered!r}')
  parts[-1] = cut_bytes(parts[-1], MAX_FILE_NAME_BYTES).strip('-') or 'untitled'
  return '/'.join(parts)
