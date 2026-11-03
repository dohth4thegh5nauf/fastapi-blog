# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.9.0] - Unreleased

### Added

- Added configurable frontmatter schemas with aliases, semantic roles,
  validation, defaults, nested objects, links, media fields and schema-driven
  admin forms. The public blog, REST API and admin share the schema.
- Added file-backed collections and `DocumentStore` with safe paths, atomic
  writes, nested documents, configurable extensions, ETags and `If-Match`.
  `DocumentService` applies shared validation, uniqueness, blocking checks and
  post-commit change notifications to API and admin writes.
- Added project configuration, generated slugs, summaries, external validators
  and the `check`, `schema` and `export` commands. Integrity checks cover
  configured document links, media paths, frontmatter, SEO and JSON-LD.
- Added JSON-LD projection and export, optional HTTP routes, local and
  allow-listed remote contexts, and lost-term checks. Expansion and N-Quads
  output use the optional `jsonld` extra.
- Added configurable SEO metadata, Open Graph, social cards, structured data,
  canonical links, sitemap, robots.txt and redirects.
- Added a shared authorization policy for API and admin operations, optional
  role-management views, customizable authentication and English/Russian UI
  translations. Admin features are available through the optional `admin` extra.
- Added public health endpoints at `/api/v1/health`, `/live` and `/ready`.
  They are enabled by default, use `application/health+json` and are described
  in OpenAPI; `health_routes=False` disables them.
- Added a Compose demo and container health checks.

### Changed

- The core package runs without the admin or JSON-LD extras. Admin imports are
  lazy, and `setup_fastapi_blog(admin=False)` does not require the admin extra.
- The post-list cache detects external file changes from directory signatures.
- Admin Markdown operations use `DocumentService` directly instead of loopback
  HTTP. Public rendering and admin preview sanitize Markdown HTML by default.
- Updated dependency floors and migrated to `starlette-admin` 1.x. Replaced
  `passlib` with direct bcrypt; existing bcrypt hashes remain supported.
- Improved admin layout, responsive actions, status badges, editor toolbar and
  diagnostics. Public and admin layouts include inline favicons.
- CI tests Python 3.12–3.15 with core and all extras on pull requests and on
  pushes to `main`/`develop`. It runs Ruff, mypy, Bandit, pip-audit and Trivy;
  CodeQL is conditional for private repositories. PRs build amd64 and arm64
  container images. Publishing smoke-tests a candidate image by digest before
  promoting release tags. The runtime image uses Python 3.15.0 and updates
  OpenSSL packages during the build.
- Development commands use the locked `uv` environment. Release preparation
  and publication are planned in a separate destination repository.

### Fixed

- Normalize unquoted YAML dates and timestamps for string-valued `date` and
  `updated` roles while preserving native YAML values for other fields.
- Accept absolute post directories in public post listings.
- Declare HTML response classes on route decorators instead of exposing
  `response_class` as a request parameter in OpenAPI.
- Render page-specific titles, language and description metadata. Removed
  personal branding from the default public templates.
- Preserve Markdown bodies containing `---`, prevent slug path escapes and
  retain unknown frontmatter keys when rewriting schemas that allow them.
- Require configured admin credentials and a strong session secret by default;
  development credentials require explicit `insecure_dev=True`. Cookie-based
  API writes validate the request origin, and admin forms use CSRF protection.
- Corrected tests and health response type annotations after the date and
  OpenAPI changes. Temporary project files are excluded from mypy collection.

### Deprecated

- `add_editor_to_app(ui=True)` and the `POSTS_DIR` environment variable.

### Removed

- Removed unused Redis and PyJWT dependencies and superseded CI workflows.

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
