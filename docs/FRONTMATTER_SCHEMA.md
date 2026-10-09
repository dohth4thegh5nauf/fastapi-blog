# Configurable Frontmatter Schema

> **Status:** step 1 of 4. The schema object and the generated Pydantic model are
> implemented. The blog, REST API and admin still use the built-in fields; they
> will be switched to the schema in the next steps (see "Roadmap").

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
For such keys use another name plus an `alias`. Names and aliases share one
namespace, so they can't clash with each other.

An empty YAML value for a list or dict field (`tags:`) is read as an empty
container.

## Roles

A role tells the blog what a field means without hardcoding its name:

| Role | Required type | Planned use |
| --- | --- | --- |
| `title` | `str` | Page title |
| `date` | `str`, `date`, `datetime` | Sort key |
| `published` | `bool` | Published/draft filter |
| `tags` | `list[str]` | Tag pages |
| `description` | `str` | Meta description, snippets |

Each role is bound to at most one field. A role that isn't bound disables the
related feature (no `tags` role means no tag pages).

## Built-in schemas

- `DEFAULT_SCHEMA` reproduces the old hardcoded behavior (`StrictFrontmatter`).
- `LOOSE_DEFAULT_SCHEMA` is the same, but keeps unknown keys (`LooseFrontmatter`).

`frontmatter_model(strict, schema=None)` still returns the old classes when no
schema is passed.

## Roadmap

1. **Done:** `FrontmatterSchema`, `FieldSpec`, model generation, `frontmatter_model(schema=...)`.
2. `helpers.list_posts` and `router` use roles instead of fixed keys.
3. REST API (`editor.py`) validates and serializes with the schema.
4. Admin forms and `MarkdownPost` are built from the schema; a `frontmatter_schema`
   parameter is added to `setup_fastapi_blog`, `add_blog_to_fastapi`,
   `add_admin_to_app` and `get_api_router`.
