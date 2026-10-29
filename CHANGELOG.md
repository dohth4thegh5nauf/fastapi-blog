# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.9.0] - Unreleased

### Dependency upgrade

Every dependency floor bumped to its current latest release: `fastapi`
0.116→0.162, `markdown` 3.9→3.11, `nh3` 0.2→0.3, `pydantic` 2.9→2.14,
`pymdown-extensions` 10→12, `uvicorn` 0.35→0.54, `sqlalchemy` 2.0→2.1,
`aiosqlite`/`itsdangerous`/`python-multipart` to latest patch, `pyld` 2→3,
`ruff` 0.13→0.17, `pytest` 8→9, `mypy` 1→2, `coverage`, `setuptools`.
`pyyaml`/`jinja2`/`jinja2-time`/`httpx` were already current.

#### `starlette-admin` 0.16 → 1.0.3 (the one major-breaking bump)

- `auth_provider.py`/`rbac_auth_provider.py`: ported to the new
  `AuthProvider` contract — `is_authenticated`/`get_admin_user` merged into a
  single `authenticate(request) -> AdminUser | None`; `login`/`logout` no
  longer take/return a `Response`; `render_login` keeps our YAML-translated
  login page but matches the new `(request, templates)` signature
- `Admin(...)` now needs an explicit `secret_key` for its own CSRF/flash
  cookies (previously only `SessionMiddleware` needed one); wired through
  from `add_admin_to_app`'s already-validated `secret_key`
- `views.py`/`views_role.py`/`markdown_crud.py`: `CustomView.render()` →
  `@route('') async def index()`; constructor kwargs renamed
  (`label`→`menu_label`, `name`→`route_name`, `template_path` removed);
  `ModelView`/`BaseView` attributes renamed (`label`→`menu_label` for the
  sidebar, `name`→`display_name` for the singular form title,
  `identity`→`key`); `DropDown(label=...)` → `DropDown(menu_label=...)`
- `admin/fields.py` (`MarkdownField`, `TagsField`, `SlugField`): the
  `action` parameter dropped from `serialize_value`/`parse_form_data`; read
  `request.state.action` instead (these classes aren't used by this
  project's own views yet, only exported for consumers)
- **The 4 customized `list.html`/`detail.html`/`edit.html`/`create.html`
  templates (Role/User management pages only) now extend the built-in
  `@starlette-admin/*.html` directly**, instead of our themed
  `layouts/custom_base.html`. 1.0 replaced the DataTables-based rendering
  these were built against with a server-rendered system built from a new
  set of partials/macros; re-theming that wasn't practical to do blind, so
  these 4 pages lost the project's custom dark theme/language switcher (they
  use the stock light theme now) in exchange for actually working — verified
  end-to-end in a real browser: login, create/list/detail/edit a user, role
  list. The blog's own post editor pages (`home.html`, `markdown_list.html`,
  `markdown_edit.html`) are untouched and keep the custom theme
- `passlib[bcrypt]`'s self-test crashes on `bcrypt>=4.1` (`ValueError:
  password cannot be longer than 72 bytes`) — a known passlib/bcrypt
  incompatibility (passlib is unmaintained since 2020). Pinned
  `bcrypt<4.1` in the `admin` extra
- New regression tests: `tests/test_admin_modelview_pages.py` (logs in for
  real, exercises create→list→detail→edit on the Role/User pages — the
  gap that let the empty-table regression through unnoticed); updated
  `tests/test_admin_theme.py` to assert the new extends-stock-template
  design instead of the old custom-theme one

### Phase A: packages, imports, cache

#### Changed
- **Core vs extras.** The core install needs only files: `fastapi`, `jinja2`,
  `jinja2-time`, `markdown`, `nh3`, `pydantic`, `pyyaml`, `pymdown-extensions`,
  `uvicorn`. New extras: `admin` (`starlette-admin[i18n]`, `sqlalchemy[asyncio]`,
  `aiosqlite`, `itsdangerous`, `passlib[bcrypt]`, `python-multipart`) and `jsonld`
  (`pyld`). Install with `pip install "fastapi-blog[admin]"`
- **Lazy admin.** `import fastapi_blog` no longer imports the admin panel.
  `Admin` and `add_admin_to_app` load on first access (PEP 562) and raise an
  `ImportError` that names the extra when it is missing
- `setup_fastapi_blog(..., admin=False)` adds only the blog (and the REST API) and
  needs no extra. It makes up no default credentials in that mode
- `list_posts` no longer uses `lru_cache`: the cached list is checked against the
  directory signature (`(name, mtime_ns, size)` of the `*.md` files), so edits made
  outside the app are visible without a restart. No TTL, thread-safe, no external
  service. `helpers.clear_posts_cache()` (and `list_posts.cache_clear()`) still work
- The translation helpers moved to `fastapi_blog.i18n` and the translation files to
  `fastapi_blog/translations/` because the public blog uses them.
  `fastapi_blog.admin.i18n` stays as an alias
- Basic auth no longer needs a `SessionMiddleware`: `auth.get_current_user` only
  reads the session when there is one. Credentials are compared with
  `secrets.compare_digest`

#### Added
- `auth_dependency` parameter of `get_api_router()` and `add_editor_to_app()`, and
  `api_auth_dependency` of `add_blog_to_fastapi()`: a custom dependency replaces
  the built-in checks
- `admin_username` and `admin_password` parameters of `add_editor_to_app()`
- `ConfigurationError`: the app fails at startup when the REST API requires
  authentication (`require_auth=True`) and has no credentials, no dependency and
  no `SessionMiddleware`
- CI matrix `core` / `all` extras; tests that need the admin extra are skipped in
  the core run (`tests/conftest.py`)

#### Removed
- Dependencies `redis[hiredis]` and `pyjwt` (they were not used), and all mentions

#### Fixed
- Docstring of `add_blog_to_fastapi` said the admin panel ignores the schema; it
  uses it when given the same schema (done for you by `setup_fastapi_blog`)

#### Deprecated
- Already deprecated and still present: `add_editor_to_app(ui=True)`. Planned for the
  next phases: the `POSTS_DIR` environment variable, the default `admin` /
  `Admin123!` credentials

### Phase B: document storage (in progress)

#### Added
- `fastapi_blog.store`: shared frontmatter parsing (`parse_document`),
  serialization, atomic writes (`atomic_write_text`, temp file + `os.replace`),
  slug/path-escape checks (`safe_document_path`) and an etag primitive
  (`compute_etag`) for later `If-Match` support

#### Fixed
- The blog post page, `helpers.list_posts`, the deprecated editor API and both
  admin post models (`markdown_model.MarkdownPost`, `markdown_crud.MarkdownPost`)
  used to split the file on every `---`, so a Markdown horizontal rule or table
  (`|---|---|`) in the body silently truncated the rendered post. All five now
  parse frontmatter the same way, only at the file's first `---`/`...` boundary
- All file reads/writes across these modules are explicit UTF-8; writes from the
  editor API and the admin post models are atomic (temp file + `os.replace`)
- `admin.markdown_model.MarkdownPost` no longer invents `datetime.now()` for a
  post with no date; a missing date stays `None` (the admin list/sort already
  handled `None` dates for mixed-timezone posts)

#### Still open for this phase
- No `Collection`/`DocumentStore` abstraction yet (4.1, 4.6): the four read/write
  call sites above now share parsing/writing primitives but aren't a single
  service, and `posts`/`pages` aren't yet modeled as two collections
- No `etag`/`If-Match` concurrency on the REST API or the admin save path yet
  (4.7); `store.compute_etag` exists but nothing calls it yet
- `markdown_crud.MarkdownPost` already defaulted an absent date to `''` (not
  `datetime.now()`); only `admin.markdown_model.MarkdownPost` invented a date,
  and that's what this pass fixed

## [Unreleased]

### Added
- **Configurable frontmatter schema** (step 1): `FrontmatterSchema` and `FieldSpec`
  describe frontmatter fields (types, defaults, aliases, semantic roles) in code or
  in a YAML/JSON file and build a Pydantic model on demand
  - `DEFAULT_SCHEMA` and `LOOSE_DEFAULT_SCHEMA` reproduce the old hardcoded behavior
  - `frontmatter_model()` accepts an optional `schema` argument
  - Step 2: the public blog uses the schema roles (`title`, `date`, `published`,
    `tags`, `description`) instead of fixed keys: new `frontmatter_schema`
    parameter of `add_blog_to_fastapi()` and `get_blog_router()`, `schema`
    parameter of `helpers.list_posts()`
  - Post lists hide the date when a post has none; posts without a date go last
  - `slug` and `content` are reserved field names (use an `alias`)
  - Step 3: the REST API validates requests with the schema and writes posts with
    the external keys (aliases): `frontmatter_schema` parameter of
    `get_api_router()` and `add_editor_to_app()` (also passed on by
    `add_blog_to_fastapi(include_api=True)`), `payload_model(strict, schema)`,
    `FrontmatterSchema.payload_model()`
  - `add_editor_to_app(ui=True, frontmatter_schema=...)` warns: the deprecated UI
    keeps the built-in fields
  - Step 4: the admin panel builds the post form, the post list and the dashboard
    from the schema: `frontmatter_schema` parameter of `add_admin_to_app()` and
    `setup_fastapi_blog()` (which passes it to the blog, the REST API and the admin)
  - New `admin/form_fields.py`: input kinds, form values and labels per field type
  - The post list hides the date, status and tags columns when the matching roles
    are not bound; the dashboard shows posts without a date
  - See `docs/FRONTMATTER_SCHEMA.md`
- **i18n for blog routes**: Blog public interface now supports internationalization
  - Added `blog` namespace to translation files (en.yaml, ru.yaml)
  - New parameters: `locales` and `default_locale` in `add_blog_to_fastapi()`
  - Blog responds to `Accept-Language` header for UI localization
  - 10 new i18n tests
- **Unified authentication**: Single auth mechanism for both admin panel and REST API
  - New `auth.py` module with `get_current_user()` and `require_current_user()`
  - Supports both session cookie (admin panel) and HTTP Basic auth (REST API)
  - Same credentials work for both authentication methods
  - 9 new unified auth tests (6 unit + 3 integration)
- Parameters `admin_username` and `admin_password` in `add_blog_to_fastapi()` for API auth

### Fixed
- `require_authentication()` now handles missing SessionMiddleware gracefully
- `.git.bak` directory removed from repository (technical debt cleanup)

### Changed
- REST API can now use unified auth when credentials are provided
- Blog templates updated to use translation keys via `{{ t.blog.* }}`

---

## [0.8.1] - 2026-05-15

### Added
- `setup_fastapi_blog()` unified facade for one-step blog and admin initialization
- Validation for weak `secret_key` with `UserWarning` and generation examples
- `.env.example` with documentation for all environment variables
- Comprehensive test coverage:
  - Password logging protection (3 tests)
  - Weak secret validation (6 tests)
  - Unified facade setup (5 tests)
  - Theme switcher template inheritance (7 tests)
  - Total: 88 tests (+21 new)
- `CONTRIBUTING.md` with guidelines for contributors

### Fixed
- **CRITICAL**: Admin password no longer logged to stdout at application startup
- Lifespan composition: user's `lifespan` correctly wrapped instead of replaced
- Parameter name: `posts_dir` → `posts_dirname` in `setup_fastapi_blog()` for consistency
- `test_lifespan.py`: use in-memory SQLite and async inspector for reliability
- Theme switcher tests: exact assertions instead of `or`-checks, full inheritance chain verified

### Security
- **CRITICAL**: Passwords never logged, not even at DEBUG level
- Weak `secret_key` detection (< 32 chars or known weak values) with user-friendly warnings
- Environment variable best practices documented in `.env.example`

### Changed
- All `print()` statements in `admin/__init__.py` replaced with proper logging
- Repository URLs updated from `awestley/fastapi-blog` to `pydanny/fastapi-blog`
- README: added development fork notice
- QUICKSTART: added prerequisites, environment variables, role management sections

### Removed
- Deprecated parameters from `add_admin_to_app()`:
  - `base_url` (replaced by automatic locale-based URLs)
  - `i18n_enabled` (use `locales` parameter)
  - `i18n_default_locale` (use `default_locale` parameter)
  - `i18n_locales` (use `locales` parameter)

---

## [0.8.0] - 2026-05-12

### Added
- Admin panel powered by starlette-admin
- Role-based access control (RBAC) with `enable_role_management` flag
- Internationalization (i18n) for English and Russian locales
- Separate admin instances per locale (`/admin/en`, `/admin/ru`)
- Markdown CRUD for managing blog posts from admin panel
- Custom fields: `MarkdownField`, `TagsField`, `SlugField`
- Theme switcher (light/dark/auto) on all admin ModelView pages
- RBAC: role management accessible only to root admin user
- Dropdown menu for access control section
- Template isolation: admin templates separate from public blog templates
- Password hashing with bcrypt for secure credential storage
- Session-based authentication for admin panel
