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

The project file is used by the CLI and can also be loaded explicitly by an
application. Passing a `CollectionSpec` to `setup_fastapi_blog()` shares its
schema, slug-generation settings and summary with the REST API and admin UI.
"""

import dataclasses
import pathlib
from collections.abc import Callable, Mapping
from typing import Any

import yaml

from . import store
from .models import DEFAULT_SCHEMA, FrontmatterSchema
from .templates import (
  SLUG_TAGS_DEFAULT,
  SUMMARY_TAGS,
  SlugOptions,
  Template,
  build_slug,
  parse_template,
)
from .validators import Validator


DEFAULT_CONFIG_NAME = 'fastapi_blog.yaml'

_COLLECTION_KEYS = {
  'dir',
  'schema',
  'slug_pattern',
  'extension',
  'create',
  'delete',
  'validators',
  'slug',
  'slug_template',
  'unique',
  'summary',
  'check',
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
      create: When `False`, no new documents may be written (TODO 4.6).
      delete: When `False`, documents may not be deleted (TODO 4.6).
      validators: External validators run by `check` (TODO 6.2).
      slug_options: How `{title_slug}` is made (the `slug` section, TODO 6.4).
      slug_template: Parsed `slug_template` (`templates.Template`), if any.
      unique: Field/tag names whose values must not repeat (TODO 6.4).
      summary: Parsed `summary` template for document captions, if any.
      check_links: Link-integrity level (`off`, `warn`, `error`).
      check_files: File-integrity level (`off`, `warn`, `error`).

  """

  name: str
  dir: pathlib.Path
  schema: FrontmatterSchema | None = None
  slug_pattern: str | None = None
  extension: str | tuple[str, ...] | None = None
  create: bool = True
  delete: bool = True
  validators: tuple[Validator, ...] = ()
  slug_options: SlugOptions = dataclasses.field(default_factory=SlugOptions)
  slug_template: Template | None = None
  unique: tuple[str, ...] = ()
  summary: Template | None = None
  check_links: str = 'off'
  check_files: str = 'off'
  on_change: Callable[[store.ChangeEvent], Any] | None = None

  def with_schema(self, schema: FrontmatterSchema) -> 'CollectionSpec':
    """Return this collection specification with an application schema."""
    return dataclasses.replace(self, schema=schema)

  def to_collection(self) -> store.Collection:
    """Build the storage-layer `Collection` for this spec."""
    kwargs: dict[str, Any] = {}
    if self.slug_pattern is not None:
      kwargs['slug_pattern'] = self.slug_pattern
    elif self.slug_template is not None:
      # A generated template may deliberately use Unicode title slugs.
      # Keep it to one safe path segment; `build_slug` enforces the byte cap.
      kwargs['slug_pattern'] = r'^[^/\\\x00-\x20]{1,200}$'
    if self.extension is not None:
      kwargs['extension'] = self.extension
    return store.Collection(
      self.name,
      self.dir,
      on_change=self.on_change,
      create=self.create,
      delete=self.delete,
      **kwargs,
    )

  def make_slug(
    self,
    frontmatter: Mapping[str, Any],
    existing_slugs: Any,
    *,
    created_at: Any = None,
    dirname: str = '',
  ) -> str:
    """Build a new slug once, using the configured role bindings/template."""
    if self.slug_template is None:
      raise ConfigError(f'Collection {self.name!r} has no `slug_template`')
    schema = self.schema or DEFAULT_SCHEMA
    fields = {field.name: frontmatter.get(field.key) for field in schema.fields}
    title_spec = schema.field_for_role('title')
    date_spec = schema.field_for_role('date')
    title = frontmatter.get(title_spec.key, '') if title_spec else ''
    date_value = frontmatter.get(date_spec.key) if date_spec else None
    return build_slug(
      self.slug_template,
      title=str(title or ''),
      fields=fields,
      collection=self.name,
      existing_slugs=existing_slugs,
      date_value=date_value,
      created_at=created_at,
      dirname=dirname,
      options=self.slug_options,
    )

  def create_document(
    self,
    documents: store.DocumentStore,
    frontmatter: dict[str, Any],
    body: str,
    *,
    created_at: Any = None,
    dirname: str = '',
    user: Any = None,
    notify: bool = True,
  ) -> tuple[str, str]:
    """Create a document using the configured slug template and sequence lock."""
    if self.slug_template is None:
      raise ConfigError(f'Collection {self.name!r} has no `slug_template`')
    schema = self.schema or DEFAULT_SCHEMA
    fields = {field.name: frontmatter.get(field.key) for field in schema.fields}
    title_spec = schema.field_for_role('title')
    date_spec = schema.field_for_role('date')
    title = frontmatter.get(title_spec.key, '') if title_spec else ''
    date_value = frontmatter.get(date_spec.key) if date_spec else None
    return documents.write_generated(
      self.slug_template,
      frontmatter,
      body,
      title=str(title or ''),
      collection=self.name,
      fields=fields,
      date_value=date_value,
      created_at=created_at,
      dirname=dirname,
      options=self.slug_options,
      user=user,
      notify=notify,
    )

  def summarize(self, slug: str, frontmatter: Mapping[str, Any]) -> str:
    """Render the configured caption, or fall back to the title role."""
    schema = self.schema or DEFAULT_SCHEMA
    title_spec = schema.field_for_role('title')
    title = frontmatter.get(title_spec.key) if title_spec else None
    if self.summary is None:
      return str(title or slug)
    fields = {field.name: frontmatter.get(field.key) for field in schema.fields}
    result = self.summary.render(
      {
        'slug': slug,
        'collection': self.name,
        'dirname': slug.rsplit('/', 1)[0] if '/' in slug else '',
        'filename': slug.rsplit('/', 1)[-1],
      },
      fields,
    )
    return result or str(title or slug)


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
  for flag in ('create', 'delete'):
    if flag in entry and not isinstance(entry[flag], bool):
      raise ConfigError(
        f'`{flag}` of collection {name!r} must be true or false'
      )
  create = entry.get('create', True)
  delete = entry.get('delete', True)
  validators: tuple[Validator, ...] = ()
  if entry.get('validators'):
    try:
      validators = tuple(
        Validator.from_dict(item) for item in entry['validators']
      )
    except (ValueError, TypeError) as exc:
      raise ConfigError(f'Collection {name!r}: {exc}') from exc
  effective_schema = schema or DEFAULT_SCHEMA
  field_names = {spec.name for spec in effective_schema.fields}
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
      # Compile the filename matcher while loading configuration, so
      # ambiguous repeated capture tags fail before the application starts.
      slug_template.slug_regex()
    except ValueError as exc:
      raise ConfigError(f'Collection {name!r}: {exc}') from exc
  summary = None
  if entry.get('summary') is not None:
    try:
      summary = parse_template(str(entry['summary']), SUMMARY_TAGS, field_names)
    except ValueError as exc:
      raise ConfigError(f'Collection {name!r}: {exc}') from exc
  check_options = entry.get('check', {})
  if check_options is None:
    check_options = {}
  if not isinstance(check_options, Mapping):
    raise ConfigError(f'Collection {name!r}: `check` must be a mapping')
  unknown_checks = sorted(set(check_options) - {'links', 'files'})
  if unknown_checks:
    raise ConfigError(
      f'Collection {name!r}: unknown check option(s) {unknown_checks}'
    )

  def _check_level(value: Any) -> str:
    # PyYAML's YAML 1.1 resolver treats the unquoted token `off` as False.
    return 'off' if value is False else str(value)

  check_links = _check_level(check_options.get('links', 'off'))
  check_files = _check_level(check_options.get('files', 'off'))
  for check_name, level in (('links', check_links), ('files', check_files)):
    if level not in ('off', 'warn', 'error'):
      raise ConfigError(
        f'Collection {name!r}: `check.{check_name}` must be off, warn or error'
      )
  unique = entry.get('unique') or ()
  if isinstance(unique, str):
    unique = (unique,)
  try:
    unique = tuple(str(item) for item in unique)
  except TypeError as exc:
    raise ConfigError(f'Collection {name!r}: `unique` must be a list') from exc
  if len(set(unique)) != len(unique):
    raise ConfigError(f'Collection {name!r}: `unique` contains duplicates')
  allowed_unique = field_names | {'seq'}
  unknown_unique = sorted(set(unique) - allowed_unique)
  if unknown_unique:
    raise ConfigError(
      f'Collection {name!r}: unknown `unique` field/tag(s) {unknown_unique}'
    )
  if 'seq' in unique and (
    slug_template is None or 'seq' not in slug_template.tags
  ):
    raise ConfigError(
      f'Collection {name!r}: `unique: [seq]` needs a slug_template using {{seq}}'
    )
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
    create=create,
    delete=delete,
    validators=validators,
    slug_options=slug_options,
    slug_template=slug_template,
    unique=unique,
    summary=summary,
    check_links=check_links,
    check_files=check_files,
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
  # Resolve link declarations only after the complete collection registry is
  # known, so forward references are valid but misspelled targets fail early.
  for source in collections.values():
    if source.schema is None:
      continue
    for field in source.schema.fields:
      if not field.is_link:
        continue
      target_name = field.collection or source.name
      target = collections.get(target_name)
      if target is None:
        raise ConfigError(
          f'Collection {source.name!r}, field {field.name!r}: '
          f'target collection {target_name!r} does not exist'
        )
      if field.value_field:
        target_field = (
          target.schema.get(field.value_field) if target.schema else None
        )
        if target_field is None and target.schema:
          target_field = next(
            (
              item
              for item in target.schema.fields
              if item.key == field.value_field
            ),
            None,
          )
        if target_field is None:
          raise ConfigError(
            f'Collection {source.name!r}, field {field.name!r}: '
            f'target field {field.value_field!r} does not exist in '
            f'collection {target_name!r}'
          )
      if field.filters and target.schema:
        for rule in field.filters:
          filter_field = target.schema.get(rule['field'])
          if filter_field is None and not any(
            item.key == rule['field'] for item in target.schema.fields
          ):
            raise ConfigError(
              f'Collection {source.name!r}, field {field.name!r}: '
              f'filter field {rule["field"]!r} does not exist in '
              f'collection {target_name!r}'
            )
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
