# Configurable Frontmatter Schema

> **Status:** step 2 of 4. The public blog (`/blog`) already uses the schema. The
> REST API and the admin panel still use the built-in fields; they will be switched
> in the next steps (see "Roadmap").

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
        FieldSpec("title", required=True, max_length=200, role="title"),
        FieldSpec("pub_date", alias="pubDate", required=True, role="date"),
        FieldSpec("draft", type="bool", default=True),
        FieldSpec("tags", type="list[str]", role="tags"),
        FieldSpec("author"),
    ),
    extra="allow",
)

Model = schema.model()  # a Pydantic model, built once and cached
post = Model(**{"title": "Hi", "pubDate": "2024-01-01"})
schema.dump(post)                 # {'title': 'Hi', 'pub_date': '2024-01-01', ...}
schema.dump(post, by_alias=True)  # {'title': 'Hi', 'pubDate': '2024-01-01', ...}
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
schema = FrontmatterSchema.from_file("schema.yaml")
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

## Known limits (until steps 3 and 4)

- The REST API (`include_api=True`) and the admin panel still write and edit posts
  with the built-in fields. Combining `include_api=True` with `frontmatter_schema`
  emits a `UserWarning`, because posts written by the API may be skipped by the blog.
- `published` is a plain flag: a `draft: true` flag (the opposite meaning) needs
  its own role, which is not available yet.

## Roadmap

1. **Done:** `FrontmatterSchema`, `FieldSpec`, model generation, `frontmatter_model(schema=...)`.
2. **Done:** `helpers.list_posts`, the blog router and the templates use roles
   instead of fixed keys; `add_blog_to_fastapi(frontmatter_schema=...)`.
3. REST API (`editor.py`) validates and serializes with the schema.
4. Admin forms and `MarkdownPost` are built from the schema; a `frontmatter_schema`
   parameter is added to `setup_fastapi_blog` and `add_admin_to_app`.
