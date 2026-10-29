# Configurable Frontmatter Schema

> **Status:** step 4 of 4, all parts are implemented. The public blog (`/blog`), the
> REST API (`/api/posts`) and the admin panel (`/admin`) use the schema.

## Why

Frontmatter fields (`title`, `date`, `published`, `tags`, `description`) used to be
hardcoded in several places. A `FrontmatterSchema` describes the fields once, so a
document can match the format of another service (for example `pubDate` instead of
`date`, or extra fields like `author` and `cover`).

## Describing a schema in code

```python
from fastapi_blog import FieldSpec, FrontmatterSchema

schema = FrontmatterSchema(
  fields=(
    FieldSpec('title', required=True, max_length=200, role='title'),
    FieldSpec('pub_date', alias='pubDate', required=True, role='date'),
    FieldSpec('draft', type='bool', default=True),
    FieldSpec('tags', type='list[str]', role='tags'),
    FieldSpec('author'),
  ),
  extra='allow',
)

Model = schema.model()  # a Pydantic model, built once and cached
post = Model(**{'title': 'Hi', 'pubDate': '2024-01-01'})
schema.dump(post)  # {'title': 'Hi', 'pub_date': '2024-01-01', ...}
schema.dump(
  post, by_alias=True
)  # {'title': 'Hi', 'pubDate': '2024-01-01', ...}
```

## Describing a schema in a file

YAML (or JSON) with the same structure:

```yaml
extra: allow          # forbid | allow | ignore
fields:
  title:
    required: true
    max_length: 200
    role: title
  pub_date:
    alias: pubDate    # the key used in the markdown file
    required: true
    role: date
  draft:
    type: bool
    default: true
  tags:
    type: list[str]
    role: tags
  author: {}
```

```python
schema = FrontmatterSchema.from_file('schema.yaml')
```

`fields` can also be a list of `{name: ..., ...}` items.

## Field options

| Option | Meaning |
| --- | --- |
| `type` | `str` (default), `int`, `float`, `bool`, `datetime`, `date`, `list[str]`, `list[int]`, `dict`, `any` |
| `required` | The field must be present. A required field can't have a `default` |
| `default` | Value for an absent field. Without it: `False` for `bool`, empty for `list`/`dict`, `None` otherwise |
| `alias` | Key in the markdown file when it differs from the internal name. Both are accepted on input |
| `role` | Semantic role (see below) |
| `min_length`, `max_length` | For `str` and `list` types |
| `description` | Free text |

Field names must be Python identifiers that don't start with `_` or `model_` and
don't clash with `pydantic.BaseModel` attributes (for example `json` or `copy`).
`slug` and `content` are reserved: the blog sets them on every post (the file name
and the rendered text). For such keys use another name plus an `alias`, for example
`FieldSpec("post_slug", alias="slug")`. Names and aliases share one
namespace, so they can't clash with each other.

An empty YAML value for a list or dict field (`tags:`) is read as an empty
container.

## Using a schema in the blog

```python
app = FastAPI()
fastapi_blog.add_blog_to_fastapi(app, frontmatter_schema=schema)
```

The blog reads each post with the schema and looks at the **roles**, not at field
names. The same applies to `helpers.list_posts(schema=...)` and `get_blog_router(
frontmatter_schema=...)`. When `frontmatter_schema` is given, `strict_frontmatter`
is ignored: set `extra` on the schema instead. Files that don't match the schema
are skipped with a warning, as before.

## One schema for everything

`setup_fastapi_blog()` passes the schema to the blog, the REST API and the admin:

```python
from fastapi_blog import FrontmatterSchema, setup_fastapi_blog

schema = FrontmatterSchema.from_file('schema.yaml')
setup_fastapi_blog(app, include_api=True, frontmatter_schema=schema)
```

The same parameter exists on `add_blog_to_fastapi()`, `add_admin_to_app()`,
`get_api_router()` and `add_editor_to_app()` if you set the parts up one by one.
Use the same schema everywhere, otherwise the parts disagree about the files.

## Using a schema in the REST API

```python
fastapi_blog.add_blog_to_fastapi(
  app, include_api=True, frontmatter_schema=schema
)
# or, with the editor helper:
add_editor_to_app(app, ui=False, frontmatter_schema=schema)
# or, with the router itself:
get_api_router(frontmatter_schema=schema)
```

- `POST /create/{slug}`, `PUT /update/{slug}` and `POST /save` validate the
  `frontmatter` object with the schema. Keys can be external names (aliases) or
  internal names. Unknown keys follow `extra` (`forbid` gives a 422 error).
- Posts are written to disk with the **external keys** (aliases), so files stay
  compatible with the other service. Empty (`None`) values are not written.
- `GET /{slug}/raw` returns the frontmatter as it is in the file, so it can be sent
  back to `PUT /update/{slug}` unchanged.
- `/docs` shows the schema keys (for example `pubDate`) in the request body.
- `strict_frontmatter` is ignored when a schema is given.
- `add_editor_to_app(ui=True)` (deprecated UI) doesn't support a schema: it emits a
  `UserWarning` and keeps the built-in fields.

## Using a schema in the admin panel

```python
add_admin_to_app(app, frontmatter_schema=schema)
```

The markdown posts section of the admin is built from the schema:

- **Form** (new and edit post): one input per schema field, in schema order. The
  input depends on the field type:

  | Type | Input |
  | --- | --- |
  | `str` | text line (a text area for the `description` role or `max_length` > 200) |
  | `int`, `float` | number |
  | `bool` | Yes/No select |
  | `date` (or `str` with the `date` role) | date picker |
  | `datetime` | date and time picker (the time zone is dropped) |
  | `list[str]`, `list[int]` | comma-separated text |
  | `dict`, `any` | JSON text area |

  Labels of fields with a role are translated (`Title`, `Date`, ...). Other fields
  use their `description`, or their name. Required `str`, number and date fields
  are required in the browser as well.
- **Saving** goes through the REST API (`POST /api/posts/save`) with the schema
  keys (aliases), so the API must be enabled with the same schema:
  `add_blog_to_fastapi(include_api=True, frontmatter_schema=schema)`.
  Empty inputs are not sent, so the API applies the field defaults or reports a
  missing required field.
- **Post list**: the title and slug columns are always there. The date, status and
  tags columns are shown only if the `date`, `published` and `tags` roles are bound.
- **Dashboard**: counts, latest posts and top tags use the roles. A post with an
  empty date is listed without a date.

The admin reads files leniently: a post that doesn't match the schema (an old
format, a missing required field) is still listed, with the slug as its title, so it
can be opened and fixed.

## Roles

A role tells the blog what a field means without hardcoding its name:

| Role | Required type | What the blog does with it |
| --- | --- | --- |
| `title` | `str` | Page and list titles. Without a value the slug is shown |
| `date` | `str`, `date`, `datetime` | Sort key (newest first) and the date shown in lists |
| `published` | `bool` | Published/draft filter (`published=False` returns drafts) |
| `tags` | `list[str]` | Tag list, `/tags` and `/tags/{tag}` pages |
| `description` | `str` | Short text in post lists |

Each role is bound to at most one field. Templates and routes receive every bound
role under its own name (`post.date` is the value of the field with the `date`
role, whatever its name is), and all fields under their internal names as well.
So no other field may be named like a role that is bound elsewhere.

What happens when a role is **not** bound:

- no `date`: posts are ordered by slug, and no date is shown;
- no `published`: there is no draft concept, every post is published;
- no `tags`: the tag pages stay empty;
- no `title`: the slug is used as the title;
- no `description`: nothing is shown.

Posts with an empty `date` come after the dated ones. Dates can be strings or YAML
dates (`date` / `datetime` types); they are compared as ISO strings.

Pages (`pages/*.md`) are not part of the schema yet.

## Built-in schemas

- `DEFAULT_SCHEMA` reproduces the old hardcoded behavior (`StrictFrontmatter`).
- `LOOSE_DEFAULT_SCHEMA` is the same, but keeps unknown keys (`LooseFrontmatter`).

`frontmatter_model(strict, schema=None)` still returns the old classes when no
schema is passed. Without `frontmatter_schema` the blog behaves exactly as before.

## Known limits

- The admin form saves through `/api/posts/save` (the URL is fixed in the template),
  so it needs the REST API at the default prefix.
- The admin reads the posts directory from the `POSTS_DIR` environment variable
  (default `posts` in the working directory), not from `posts_dirname`.
- `published` is a plain flag: a `draft: true` flag (the opposite meaning) needs
  its own role, which is not available yet.
- `PostModelView` (the SQL `Post` model) and the user/role views don't use the
  schema: they are unrelated to the markdown files.
- Pages (`pages/*.md`) are not part of the schema.

## Roadmap

1. **Done:** `FrontmatterSchema`, `FieldSpec`, model generation, `frontmatter_model(schema=...)`.
2. **Done:** `helpers.list_posts`, the blog router and the templates use roles
   instead of fixed keys; `add_blog_to_fastapi(frontmatter_schema=...)`.
3. **Done:** the REST API (`editor.py`) validates and serializes with the schema;
   `frontmatter_schema` parameter of `get_api_router`, `add_editor_to_app`
   and `add_blog_to_fastapi`.
4. **Done:** the admin forms, list and dashboard are built from the schema;
   `frontmatter_schema` parameter of `add_admin_to_app` and `setup_fastapi_blog`.
