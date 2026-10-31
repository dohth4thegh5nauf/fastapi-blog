"""The project file that names the collections for the command line.

`python -m fastapi_blog` needs to know where the documents are. A small YAML
file in the project root says so:

```yaml
collections:
  notes:
    dir: content/notes            # relative to the project root
    schema: content/notes.schema.yaml
    slug_pattern: '[0-9]{4}-[a-z0-9-]+'   # optional
    extension: md                         # optional, one or several
```

The project root is the directory of this file. Precedence (TODO phase D):
an explicit CLI flag beats the project file, the project file beats the
built-in defaults (`posts/` with the built-in schema). Applications that use
the library directly don't need the file: they keep passing
`posts_dirname`/`frontmatter_schema` in code.

The format intentionally covers only what is implemented; `validators`,
`slug_template`, `unique` and the `check` options (TODO 6.2/6.4) will extend
it when they land.
"""

import dataclasses
import pathlib
from collections.abc import Mapping
from typing import Any

import yaml

from . import store
from .models import FrontmatterSchema
from .templates import (
  SLUG_TAGS_DEFAULT,
  SUMMARY_TAGS,
  SlugOptions,
  Template,
  parse_template,
)
from .validators import Validator


DEFAULT_CONFIG_NAME = 'fastapi_blog.yaml'

_COLLECTION_KEYS = {
  'dir',
  'schema',
  'slug_pattern',
  'extension',
  'validators',
  'slug',
  'slug_template',
  'unique',
  'summary',
}


class ConfigError(ValueError):
  """The project file or a schema file it points to is wrong."""


@dataclasses.dataclass(frozen=True)
class CollectionSpec:
  """One collection as described by the project file (or CLI defaults).

  Attributes:
      name: Collection name, used in messages and the JSON-LD `@id` template.
      dir: Directory holding the documents (absolute).
      schema: Frontmatter schema the documents must match, if any.
      slug_pattern: `slug_pattern` of the underlying `store.Collection`.
      extension: `extension` of the underlying `store.Collection`.
      validators: External validators run by `check` (TODO 6.2).
      slug_options: How `{title_slug}` is made (the `slug` section, TODO 6.4).
      slug_template: Parsed `slug_template` (`templates.Template`), if any.
      unique: Field/tag names whose values must not repeat (TODO 6.4).
      summary: Parsed `summary` template for document captions, if any.

  """

  name: str
  dir: pathlib.Path
  schema: FrontmatterSchema | None = None
  slug_pattern: str | None = None
  extension: str | tuple[str, ...] | None = None
  validators: tuple[Validator, ...] = ()
  slug_options: SlugOptions = dataclasses.field(default_factory=SlugOptions)
  slug_template: Template | None = None
  unique: tuple[str, ...] = ()
  summary: Template | None = None

  def to_collection(self) -> store.Collection:
    """Build the storage-layer `Collection` for this spec."""
    kwargs: dict[str, Any] = {}
    if self.slug_pattern is not None:
      kwargs['slug_pattern'] = self.slug_pattern
    if self.extension is not None:
      kwargs['extension'] = self.extension
    return store.Collection(self.name, self.dir, **kwargs)


@dataclasses.dataclass(frozen=True)
class Project:
  """The collections of a project.

  Attributes:
      root: Project root (the directory of the project file).
      collections: Collection specs by name, in file order.

  """

  root: pathlib.Path
  collections: dict[str, CollectionSpec]


def _collection_spec(
  name: str, entry: Any, root: pathlib.Path
) -> CollectionSpec:
  if not isinstance(entry, Mapping):
    raise ConfigError(f'Collection {name!r} must be a mapping')
  unknown = sorted(set(entry) - _COLLECTION_KEYS)
  if unknown:
    raise ConfigError(f'Collection {name!r} has unknown option(s) {unknown}')
  if not entry.get('dir'):
    raise ConfigError(f'Collection {name!r} needs `dir`')
  schema = None
  schema_path = entry.get('schema')
  if schema_path:
    try:
      schema = FrontmatterSchema.from_file(root / str(schema_path))
    except OSError as exc:
      raise ConfigError(
        f"Schema of collection {name!r} can't be read: {exc.strerror or exc}"
      ) from exc
    except ValueError as exc:
      raise ConfigError(f'Schema of collection {name!r}: {exc}') from exc
  extension = entry.get('extension')
  if extension is not None and not isinstance(extension, (str, list, tuple)):
    raise ConfigError(
      f'`extension` of collection {name!r} must be a string or a list'
    )
  validators: tuple[Validator, ...] = ()
  if entry.get('validators'):
    try:
      validators = tuple(
        Validator.from_dict(item) for item in entry['validators']
      )
    except (ValueError, TypeError) as exc:
      raise ConfigError(f'Collection {name!r}: {exc}') from exc
  field_names = {spec.name for spec in schema.fields} if schema else set()
  slug_options = SlugOptions()
  if entry.get('slug') is not None:
    try:
      slug_options = SlugOptions.from_dict(entry['slug'])
    except ValueError as exc:
      raise ConfigError(f'Collection {name!r}: {exc}') from exc
  slug_template = None
  if entry.get('slug_template') is not None:
    try:
      slug_template = parse_template(
        str(entry['slug_template']), SLUG_TAGS_DEFAULT, field_names
      )
    except ValueError as exc:
      raise ConfigError(f'Collection {name!r}: {exc}') from exc
  summary = None
  if entry.get('summary') is not None:
    try:
      summary = parse_template(
        str(entry['summary']), SUMMARY_TAGS, field_names
      )
    except ValueError as exc:
      raise ConfigError(f'Collection {name!r}: {exc}') from exc
  unique = entry.get('unique') or ()
  if isinstance(unique, str):
    unique = (unique,)
  try:
    unique = tuple(str(item) for item in unique)
  except TypeError as exc:
    raise ConfigError(f'Collection {name!r}: `unique` must be a list') from exc
  return CollectionSpec(
    name=name,
    dir=root / str(entry['dir']),
    schema=schema,
    slug_pattern=str(entry['slug_pattern'])
    if entry.get('slug_pattern') is not None
    else None,
    extension=tuple(str(item) for item in extension)
    if isinstance(extension, (list, tuple))
    else extension,
    validators=validators,
    slug_options=slug_options,
    slug_template=slug_template,
    unique=unique,
    summary=summary,
  )


def load_project(path: str | pathlib.Path) -> Project:
  """Read the project file (strict: the file must exist and be valid).

  Raises:
      ConfigError: If the file is missing or wrong.

  """
  config_path = pathlib.Path(path)
  try:
    text = config_path.read_text(encoding='utf-8')
  except OSError as exc:
    raise ConfigError(
      f"Can't read {config_path}: {exc.strerror or exc}"
    ) from exc
  try:
    data = yaml.safe_load(text)
  except yaml.YAMLError as exc:
    raise ConfigError(f'{config_path} is not valid YAML: {exc}') from exc
  if not isinstance(data, Mapping):
    raise ConfigError(f'{config_path} must be a mapping')
  unknown = sorted(set(data) - {'collections'})
  if unknown:
    raise ConfigError(f'{config_path} has unknown key(s) {unknown}')
  entries = data.get('collections') or {}
  if not isinstance(entries, Mapping) or not entries:
    raise ConfigError(f'{config_path} needs a `collections` mapping')
  root = config_path.resolve().parent
  collections = {
    str(name): _collection_spec(str(name), entry, root)
    for name, entry in entries.items()
  }
  return Project(root=root, collections=collections)


def find_project(start: str | pathlib.Path | None = None) -> Project | None:
  """Return the project of `start` (default: cwd), or `None` without a file.

  There is no search up the directory tree: the file counts only where the
  command runs, so behavior stays explicit and deterministic (П5).
  """
  base = pathlib.Path.cwd() if start is None else pathlib.Path(start)
  config_path = base / DEFAULT_CONFIG_NAME
  if not config_path.is_file():
    return None
  return load_project(config_path)
