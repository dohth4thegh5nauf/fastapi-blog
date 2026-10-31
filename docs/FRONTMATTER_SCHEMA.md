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
| `type` | `str` (default), `int`, `float`, `bool`, `datetime`, `date`, `list[str]`, `list[int]`, `link`, `list[link]`, `file`, `image`, `dict`, `any` |
| `required` | The field must be present. A required field can't have a `default` |
| `default` | Value for an absent field. Without it: `False` for `bool`, empty for `list`/`dict`, `None` otherwise |
| `alias` | Key in the markdown file when it differs from the internal name. Both are accepted on input |
| `role` | Semantic role (see below) |
| `min_length`, `max_length` | For `str` and `list` types |
| `description` | Free text |
| `collection`, `value_field`, `filters` | For `link` fields: the target collection (default: the same one), the target field whose value is stored (default: the `@id` field, else the slug), and `[{field, values}]` filters on valid targets |
| `media_dir`, `public_path` | For `file`/`image` fields: the files' directory (relative to the project root, no `..`) and the prefix of the stored path (default: `media_dir`) |

Field names must be Python identifiers that don't start with `_` or `model_` and
don't clash with `pydantic.BaseModel` attributes (for example `json` or `copy`).
`slug` and `content` are reserved: the blog sets them on every post (the file name
and the rendered text). For such keys use another name plus an `alias`, for example
`FieldSpec("post_slug", alias="slug")`. Names and aliases share one
namespace, so they can't clash with each other.

An empty YAML value for a list or dict field (`tags:`) is read as an empty
container.

### Integrity checks for links and files

The project collection entry (in `fastapi_blog.yaml`) can opt into checks:

```yaml
collections:
  pages:
    dir: pages
    schema: pages.yaml
    check:
      links: warn   # off (default), warn, error
      files: error  # off (default), warn, error
```

`check.links` validates local `link` and `list[link]` values against the
configured target collection. A target is identified by its `@id` alias, the
configured `value_field`, or its slug. `collection` selects another collection
and `filters` restrict which target records are valid. A missing target and a
target excluded by filters are separate findings. External IRIs are not
fetched or resolved.

`check.files` validates `file` and `image` values when `media_dir` is set. The
stored value must begin with `public_path` (or `media_dir` by default); the
remaining path is resolved below `media_dir`. Missing files and paths that
escape the media directory are reported. HTTP(S) URLs are treated as external
and are not fetched.

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

## Generated slugs and collection summaries

Slug generation and document summaries are collection configuration, not
frontmatter schema fields. Configure them in `fastapi_blog.yaml` and pass the
loaded collection explicitly to the application:

```yaml
collections:
  posts:
    dir: posts
    slug_template: "{seq|pad(4)}-{title_slug}"
    unique: [seq]
    summary: "{title}"
```

```python
from fastapi_blog import load_project, setup_fastapi_blog

posts = load_project("fastapi_blog.yaml").collections["posts"]
setup_fastapi_blog(app, collection_spec=posts, include_api=True)
```

The generated-slug REST endpoint is `POST /api/posts/create`; its request
contains `frontmatter` and `content`, without a `slug`. The admin create form
uses the same behavior when the slug field is blank. A manually supplied slug
continues to work. Date tags use the date-role field when populated, or the
UTC first-save timestamp otherwise. The slug is generated once and remains
stable across subsequent edits. A configured `summary` appears beneath the
document title in the admin list.

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
- On a rewrite (`PUT`/`save` of an existing post) the frontmatter is merged
  over the file (TODO 4.5): known keys keep their positions, unknown keys
  are kept when the schema is `extra: 'allow'`, keys emptied to `None` are
  dropped, and schema fields the file didn't have yet are appended in
  schema order.
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

## The `jsonld:` section

A schema may carry a `jsonld` section (`JsonLdConfig`) for the JSON-LD
export (see `fastapi_blog.jsonld`):

- `context`: an inline mapping, a path to a file inside the project root, a
  URL, or a list of them. Files and URLs are loaded by
  `jsonld.resolve_context(schema, project_root=...)`; nothing in a context
  is executed. Remote contexts are refused unless listed in
  `allow_remote_contexts` and only with the `jsonld` extra installed
  (timeout, `max_context_bytes` size limit, redirects to another host are
  refused).
- `base`, `id_template`, `type`: defaults for `@id`/`@type` when no field
  carries the alias; `id_template` is a plain `{base}`/`{collection}`/
  `{slug}` format string.
- `content_term`: the term the document body is emitted under.
- `max_documents`: limit of documents in one exported `@graph`.
- `jsonld.uncovered_keys(schema, project_root=...)` lists the schema keys
  the (resolved) context doesn't cover — JSON-LD would silently drop them.

## The `seo:` section

A schema may carry a `seo` section (`SeoConfig`) with site-wide SEO
settings. The same settings can be passed as `seo=SeoConfig(...)` to
`add_blog_to_fastapi()` and `setup_fastapi_blog()`; the argument is stronger
than the section and replaces it as a whole (the two aren't merged).

```yaml
seo:
  site_url: "https://example.org"      # base of absolute addresses
  site_name: "Example Notes"           # page header, `title_template`
  title_template: "{title} - {site_name}"
  default_image: "/static/social.png"
  default_author: null
  default_robots: []                   # noindex, nofollow, noarchive, nosnippet
  index_description: "Short site description"
  og: true
  twitter_card: summary_large_image    # summary, summary_large_image or null
  structured_data: blogposting         # blogposting, article or none
  description_fallback: excerpt        # excerpt or none
  description_length: 160
  noindex_tags: false                  # tag pages get robots noindex
  disallow: []                         # paths for robots.txt `Disallow`
```

- Every key is optional. An empty section (`seo: {}`) is valid and means
  "all defaults"; without a section and without the argument the blog behaves
  as before.
- Values are checked when the schema is loaded, and an error names the key
  (for example `seo.twitter_card`). `site_url` must be an `http(s)` URL
  without a query or fragment; a trailing `/` is dropped. `default_image` is
  an `http(s)` URL or a path from the site root. `title_template` may only
  use `{title}` and `{site_name}`.
- With a `seo` section (even an empty one) the page `<head>` is built by
  `fastapi_blog.seo.build_head()`: title, description, canonical, robots,
  author, Open Graph, Twitter Card and schema.org JSON-LD, using the
  fallback order of TODO 5.9.3. A tag is printed only when it has a value.
  Without a section only the 5.9.6 fixes apply (page title, description,
  `<html lang>`). A document whose `canonical` points to another address gets
  no `hreflang` alternates.
- `disallow` entries must start with `/` and contain no whitespace.
- `add_blog_to_fastapi(seo_routes=True)` (or the same argument of
  `setup_fastapi_blog()`) adds `GET /sitemap.xml`, `GET /robots.txt` and
  permanent `301` redirects for the `redirect_from` role. It needs
  `seo.site_url`; without it the app fails at startup with
  `ConfigurationError`. The sitemap lists published documents only, skips
  `noindex` documents and documents whose `canonical` is another address,
  lists tag pages unless `noindex_tags` is on, and becomes an index of
  `sitemap-N.xml` files above 50,000 URLs. A `redirect_from` value without a
  `/` is a slug under `{prefix}/posts/`; one with a `/` is a site path. An
  alias that equals a live post address or the document's own is ignored.
  Redirects apply to the default locale's URLs only.

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
- Pages (`pages/*.md`) validate against a built-in schema with the fields
  they have always had (`helpers.PAGES_SCHEMA`: `title`, `description`,
  `author`; unknown keys are kept, a page that doesn't match is served with
  its raw frontmatter). A configurable page schema is not part of the
  public API yet.

## Roadmap

1. **Done:** `FrontmatterSchema`, `FieldSpec`, model generation, `frontmatter_model(schema=...)`.
2. **Done:** `helpers.list_posts`, the blog router and the templates use roles
   instead of fixed keys; `add_blog_to_fastapi(frontmatter_schema=...)`.
3. **Done:** the REST API (`editor.py`) validates and serializes with the schema;
   `frontmatter_schema` parameter of `get_api_router`, `add_editor_to_app`
   and `add_blog_to_fastapi`.
4. **Done:** the admin forms, list and dashboard are built from the schema;
   `frontmatter_schema` parameter of `add_admin_to_app` and `setup_fastapi_blog`.
