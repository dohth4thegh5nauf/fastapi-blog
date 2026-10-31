# FastAPI Blog

> A file-based Markdown blog and content-management toolkit for FastAPI.

**Package version:** `0.9.0` (development release; see [CHANGELOG.md](CHANGELOG.md))  
**Python:** 3.12+  
**Platforms:** Ubuntu (latest LTS), as specified by the project guidelines.

FastAPI Blog adds a public blog to an existing FastAPI application. Posts and pages are Markdown files with YAML frontmatter; an optional admin interface and an optional authenticated REST API provide content-management workflows.

This repository is a development fork of [pydanny/fastapi-blog](https://github.com/pydanny/fastapi-blog).

## Features

### Public blog

- Markdown posts with YAML frontmatter and HTML sanitization.
- Static pages from a separate `pages/` directory.
- Tag, post-list, post-detail and page routes.
- Configurable URL prefix, locale list, default locale and favorite posts.
- Jinja2 templates that can be overridden with a custom loader.
- Responsive templates, dark-mode styling and code syntax highlighting.
- Configurable frontmatter schemas, including semantic roles for title, date, publication status, tags and description.
- Optional SEO metadata resolution and page-head output when SEO settings are configured.
- Optional `sitemap.xml`, `robots.txt` and permanent redirects for moved posts (`seo_routes=True`).

### Content management

- Optional Starlette Admin web interface (installed with the `admin` extra).
- User authentication and management, with optional role-management views.
- Markdown post CRUD operations and custom admin form fields.
- English and Russian admin translations.
- Optional REST API for creating, reading, updating and deleting Markdown posts.
- API authentication through session middleware, HTTP Basic credentials or a custom FastAPI dependency.
- Optional `If-Match` concurrency checks for update and delete operations.

The admin panel is an HTML web application and does not appear in FastAPI's OpenAPI docs. The REST API is a separate feature and is included in `/docs` when enabled.

### Schemas, storage and export

- `FrontmatterSchema` and `FieldSpec` let applications define field names, aliases, types, validation, defaults and semantic roles.
- Built-in strict and loose schemas preserve the legacy frontmatter behavior.
- `DocumentStore` provides file-backed document operations, nested collections, safe slug-to-path handling, ETags and specific storage errors.
- Optional JSON-LD projection and collection export, including local and allow-listed remote contexts.
- A command-line interface for schema inspection and JSON-LD export.

## Installation

The core package provides the public blog, file-backed storage, schema support and optional REST API. The admin interface and JSON-LD expansion have separate extras.

```bash
# Core package
pip install fastapi-blog

# Optional admin interface and session-based authentication
pip install "fastapi-blog[admin]"

# Optional JSON-LD expansion and N-Quads output
pip install "fastapi-blog[jsonld]"

# Development dependencies
pip install "fastapi-blog[dev]"
```

You can combine extras, for example `pip install "fastapi-blog[admin,jsonld]"`.

The admin package is imported lazily. Importing `fastapi_blog` does not require the `admin` extra; calling `add_admin_to_app()` or using `setup_fastapi_blog()` with its default `admin=True` does.

## Quick start

### Blog only

```python
from fastapi import FastAPI
from fastapi_blog import add_blog_to_fastapi

app = FastAPI()
add_blog_to_fastapi(app, prefix='blog')
```

Create a post at `posts/hello-world.md`:

```markdown
---
title: Hello, world
date: 2026-10-31
published: true
tags:
  - fastapi
  - markdown
description: My first post.
---

# Hello

This post is written in **Markdown**.
```

Run the application with Uvicorn:

```bash
uvicorn main:app --reload
```

With the default `prefix='blog'`, the blog is available at `/blog/`. The package also serves Markdown pages from `pages/` (for example, `pages/about.md` is available at `/blog/about`).

### Blog and admin panel

Install the `admin` extra, then configure both components:

```python
from fastapi import FastAPI
from fastapi_blog import add_admin_to_app, add_blog_to_fastapi

app = FastAPI()

add_blog_to_fastapi(app, prefix='blog')
add_admin_to_app(
  app,
  admin_username='admin',
  admin_password='change-this-password',
  secret_key='replace-with-a-random-secret',
)
```

The admin interface is available under `/admin` (with locale-specific paths when multiple locales are configured). Configure credentials and a strong session secret for your deployment; do not use example or default credentials in production.

### Unified setup

`setup_fastapi_blog()` configures the blog and, optionally, the admin panel together. It passes a shared frontmatter schema to both.

```python
from fastapi import FastAPI
from fastapi_blog import setup_fastapi_blog

app = FastAPI()

setup_fastapi_blog(
  app,
  posts_dirname='posts',
  include_api=True,
  locales=['en', 'ru'],
  default_locale='en',
  admin_username='admin',
  admin_password='change-this-password',
  secret_key='replace-with-a-random-secret',
  enable_role_management=False,
)
```

The admin panel is enabled by default and therefore requires the `admin` extra. To run without the admin dependency, set `admin=False`; the function then adds the public blog and, if requested, the REST API, and returns an empty dictionary.

See [QUICKSTART.md](QUICKSTART.md) for runnable examples and [demo.sh](demo.sh) for the repository demo.

## Generated slugs and collection summaries

A project collection can define a `slug_template` and an optional `summary`.
Pass the loaded `CollectionSpec` to `setup_fastapi_blog()` so the public blog,
REST API and admin panel share the same collection settings:

```yaml
# fastapi_blog.yaml
collections:
  posts:
    dir: posts
    slug_template: "{seq|pad(4)}-{title_slug}"
    summary: "{title}"
    unique: [seq]
    check:
      links: error   # off | warn | error
      files: warn    # off | warn | error
```

```python
from fastapi import FastAPI
from fastapi_blog import load_project, setup_fastapi_blog

app = FastAPI()
posts = load_project("fastapi_blog.yaml").collections["posts"]

setup_fastapi_blog(
    app,
    collection_spec=posts,
    include_api=True,
    admin=True,
    # Supply deployment credentials and a strong secret in production.
)
```

When a collection has a `slug_template`, the REST API supports
`POST /api/posts/create` with only `frontmatter` and `content`; it allocates the
next slug under the collection's write lock. The legacy
`POST /api/posts/create/{slug}` route remains available. The admin create form
also allows the slug to be left blank for automatic generation, or entered
manually to override it. The API applies the same schema validation and
blocking external validators to generated documents as to explicitly named
documents.

The optional `check.links` setting validates local `link`/`list[link]`
references (including target-collection filters); `check.files` validates
`file`/`image` paths against their configured `media_dir` and `public_path`.
Both default to `off`; choose `warn` or `error` per collection. External IRIs
are not resolved, and media paths are containment-checked before access.

The `{year}`, `{month}` and `{day}` template tags use the document's date-role
field when it has a value; otherwise they use the UTC timestamp captured at
first save. Once created, the filename is stable when the title or date is
edited. A configured `summary` is shown below the title in the admin post
list; without one, the title is used.

The package does not discover a project file implicitly at runtime. Load it
explicitly with `load_project()` and pass the collection you want to use.
This keeps application configuration explicit and preserves the file-based
storage boundary.

## REST API

Enable the post-management API with `include_api=True`:

```python
from fastapi import FastAPI
from fastapi_blog import add_blog_to_fastapi

app = FastAPI()

add_blog_to_fastapi(
  app,
  include_api=True,
  api_prefix='/api/posts',
  api_require_auth=True,
  admin_username='writer',
  admin_password='use-a-long-unique-password',
)
```

The API routes are documented in `/docs`. Authentication is required by default. Supply credentials, a custom `api_auth_dependency`, or a session middleware. A custom dependency replaces the built-in session and Basic-auth checks:

```python
from fastapi import HTTPException, Request


def check_token(request: Request) -> dict:
  if request.headers.get('X-Token') != 'replace-this-token':
    raise HTTPException(status_code=403)
  return {'username': 'automation'}
```

Pass it as `api_auth_dependency=check_token`. If authentication is required but no usable authentication mechanism is configured, the application reports a configuration error at startup rather than silently exposing an unusable or unprotected API.

The API supports Markdown post CRUD, raw-document retrieval, and optional conditional writes. Set `require_if_match=True` on `get_api_router()` to require an `If-Match` header for update and delete requests; the ETag is obtained from the raw-document response.

## Frontmatter schemas

The built-in schema supports the conventional fields `title`, `date`, `published`, `tags` and `description`. For a project with different frontmatter keys, define a `FrontmatterSchema` and assign semantic roles to the fields:

```python
from fastapi_blog.models import FieldSpec, FrontmatterSchema

schema = FrontmatterSchema(
  fields=(
    FieldSpec('heading', role='title'),
    FieldSpec('pubDate', type='date', role='date'),
    FieldSpec('visible', type='bool', role='published', default=True),
    FieldSpec('labels', type='list[str]', role='tags'),
    FieldSpec('summary', role='description'),
  )
)
```

Pass the same schema to the blog, REST API and admin setup. `setup_fastapi_blog()` does this automatically:

```python
setup_fastapi_blog(app, frontmatter_schema=schema)
```

For separate setup, pass `frontmatter_schema=schema` to `add_blog_to_fastapi()` and `add_admin_to_app()`. The API router also accepts it through `get_api_router()`.

Schemas can be loaded from YAML or JSON with `FrontmatterSchema.from_file()`. They support aliases, field validation, defaults, read-only and create-time values, extra-key policies, and roles. See [Frontmatter Schema](docs/FRONTMATTER_SCHEMA.md) for the full format and behavior.

### Built-in semantic roles

| Role | Expected value | Purpose |
| --- | --- | --- |
| `title` | string | Document title; falls back to the slug when absent |
| `date` | string, date or datetime | Sorting and displayed publication date |
| `published` | boolean | Published/draft filtering |
| `tags` | list of strings | Tag list and tag routes |
| `description` | string | Short description in listings and metadata |

A schema may also define SEO-specific roles. `fastapi_blog.seo.seo_fields()` returns field specifications for `seo_title`, `canonical`, `robots`, `image`, `image_alt`, `updated`, `author`, `lang` and `redirect_from`.

### SEO routes

Sitemap, robots and redirect routes are opt-in and need `seo.site_url`:

```python
from fastapi_blog import add_blog_to_fastapi
from fastapi_blog.models import SeoConfig

add_blog_to_fastapi(
  app,
  seo=SeoConfig(site_url='https://example.org', disallow=['/admin']),
  seo_routes=True,
)
```

This adds `GET /sitemap.xml` (published documents only; `noindex` documents and documents with a foreign `canonical` are left out), `GET /robots.txt`, and `301` redirects from each document's `redirect_from` aliases to its canonical address. Without `seo.site_url` the application fails at startup with `ConfigurationError`. See [Frontmatter Schema](docs/FRONTMATTER_SCHEMA.md) for the details.

## JSON-LD

JSON-LD routes are opt-in:

```python
from fastapi_blog import add_blog_to_fastapi

add_blog_to_fastapi(
  app,
  jsonld_routes=True,
  frontmatter_schema=schema,
)
```

This adds JSON-LD representations for published posts and the collection index. JSON-LD configuration can define a context, identifiers, types and document limits. Contexts may be inline, loaded from files inside the project root, or fetched from explicitly allow-listed URLs. Remote contexts require the `jsonld` extra and are subject to size and redirect restrictions.

The CLI can export a collection:

```bash
# Export compact JSON-LD to stdout
python -m fastapi_blog export --posts-dir posts

# Export with a project schema and write to a file
python -m fastapi_blog export --posts-dir posts --schema frontmatter.yaml --out posts.jsonld

# Expanded JSON-LD and N-Quads require the jsonld extra
python -m fastapi_blog export --format expanded
python -m fastapi_blog export --format nquads
```

Inspect the generated JSON Schema for frontmatter:

```bash
python -m fastapi_blog schema --json-schema
python -m fastapi_blog schema --schema frontmatter.yaml --json-schema --out frontmatter.schema.json
```

## Configuration

### Main integration options

| Option | Default | Description |
| --- | --- | --- |
| `prefix` | `'blog'` | Public blog URL prefix; use `None` to mount at the application root |
| `posts_dirname` | `'posts'` | Directory containing Markdown posts |
| `pages_dirname` | `'pages'` | Directory containing Markdown pages |
| `include_api` | `False` (or environment setting) | Include the post-management REST API |
| `api_prefix` | `'/api/posts'` | REST API URL prefix |
| `api_require_auth` | `True` | Require API authentication |
| `locales` | `['en']` | Supported locales |
| `default_locale` | `'en'` | Fallback locale |
| `strict_frontmatter` | `True` | Use strict built-in validation; ignored when a custom schema is supplied |
| `sanitize_html` | `True` | Sanitize HTML in Markdown content |
| `frontmatter_schema` | built-in schema | Custom post frontmatter schema |
| `seo` | `None` | Site-wide SEO configuration; overrides the schema's `seo` section |
| `seo_routes` | `False` | Add `sitemap.xml`, `robots.txt` and `redirect_from` redirects; requires `seo.site_url` |

`add_blog_to_fastapi()` also accepts a Jinja2 loader and extensions, favorite post slugs, an API authentication dependency, and the `jsonld_routes` switch. See its function signature and docstring for the complete API.

### Environment variables

The package recognizes `FASTAPI_BLOG_INCLUDE_API`, `FASTAPI_BLOG_ADMIN_LOGIN` and `FASTAPI_BLOG_ADMIN_PASSWORD`. Admin/database deployment settings are described in [Environment Variables](docs/ENVIRONMENT_VARIABLES.md).

Generate a session secret rather than reusing a password:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Templates and static assets

The blog uses Jinja2 templates. Supply a custom loader to `add_blog_to_fastapi()` to override package templates while falling back to the built-in templates. The package includes templates and translation resources as package data.

The admin interface has its own templates and translations, separate from the public blog templates.

## Development

### Requirements and setup

The project targets Python 3.12+ and follows the repository's Ubuntu latest-LTS development guideline. The recommended development workflow uses `uv` and the Makefile:

```bash
git clone https://github.com/pydanny/fastapi-blog.git
cd fastapi-blog
make install
```

### Common commands

```bash
make test       # Run the test suite with coverage
make lint       # Run Ruff checks
make format     # Format/fix with Ruff
make mypy       # Run mypy
make all        # Run the configured quality checks
```

Tests are scoped to `tests/` by the pytest configuration. CI workflows are defined under `.github/workflows/`.

### Repository layout

```text
.
├── src/fastapi_blog/
│   ├── admin/          # Optional Starlette Admin integration
│   ├── models/         # Frontmatter and API models
│   ├── templates/      # Public Jinja2 templates
│   ├── main.py         # FastAPI integration and unified setup
│   ├── router.py       # Public blog routes
│   ├── editor.py       # Post-management REST API
│   ├── store.py        # File-backed collections and documents
│   ├── jsonld.py       # JSON-LD projection and contexts
│   ├── seo.py          # SEO roles, configuration and head metadata
│   └── helpers.py      # Markdown and post helpers
├── tests/              # Unit and integration tests
│   └── examples/       # Runnable example applications
├── docs/               # Architecture and feature documentation
├── .github/workflows/  # CI workflows
├── pyproject.toml      # Package metadata and dependencies
├── CHANGELOG.md        # Release history
├── QUICKSTART.md       # Guided setup and examples
└── Makefile            # Development tasks
```

### Tests and quality

The repository contains 37 test modules covering the core blog, storage, schema validation, REST API, authentication, admin behavior, SEO, JSON-LD and CLI. Run `make test` to execute the current suite; test counts and coverage are intentionally not hard-coded here because they change as the project evolves.

## Documentation

- [Quick Start](QUICKSTART.md) — demos, setup and common workflows.
- [Frontmatter Schema](docs/FRONTMATTER_SCHEMA.md) — schema fields, roles, validation and JSON-LD/SEO configuration.
- [Architecture](docs/ARCHITECTURE.md) — components and request/data flow.
- [Database](docs/DATABASE.md) — database models and setup.
- [Environment Variables](docs/ENVIRONMENT_VARIABLES.md) — environment-based configuration.
- [Role Management](docs/ROLE_MANAGEMENT.md) — optional RBAC functionality.
- [Changelog](CHANGELOG.md) — changes in version `0.9.0` and earlier.

## License

See [LICENSE.md](LICENSE.md).

## Contributors

<!-- readme: contributors -start -->
<table>
<tr>
    <td align="center">
        <a href="https://github.com/pydanny">
            <img src="https://avatars.githubusercontent.com/u/62857?v=4" width="100;" alt="pydanny"/>
            <br />
            <sub><b>Daniel Roy Greenfeld</b></sub>
        </a>
    </td>
    <td align="center">
        <a href="https://github.com/audreyfeldroy">
            <img src="https://avatars.githubusercontent.com/u/74739?v=4" width="100;" alt="audreyfeldroy"/>
            <br />
            <sub><b>Audrey Roy Greenfeld</b></sub>
        </a>
    </td>
</tr>
</table>
<!-- readme: contributors -end -->
