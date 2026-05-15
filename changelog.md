# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

### Added
- Password logging protection: replaced print() with logger to prevent credential leaks
- Validation for weak secret_key with UserWarning and generation examples
- `.env.example` with all configuration options and best practices
- `setup_fastapi_blog()` unified facade for blog and admin setup
- Comprehensive test coverage for password logging and secret validation

### Fixed
- test_lifespan.py: use in-memory SQLite and async inspector
- Lifespan composition: correctly wraps user's lifespan instead of replacing
- Parameter name: posts_dir → posts_dirname in setup_fastapi_blog()

### Changed
- All print() statements replaced with logging (logger.info/debug/warning)
- Repository URLs updated from awestley/fastapi-blog to pydanny/fastapi-blog

### Removed
- Deprecated parameters removed from `add_admin_to_app()`:
  - `base_url` (use `locales` and `default_locale` instead)
  - `i18n_enabled` (use `locales` parameter)
  - `i18n_default_locale` (use `default_locale` parameter)
  - `i18n_locales` (use `locales` parameter)

### Security
- **CRITICAL**: Passwords are never logged (not even at DEBUG level)
- Weak secret_key detection with UserWarning (< 32 chars or known weak values)
- Environment variables documented in .env.example

## [v0.8.0] - Previous

### Added
- Admin panel with starlette-admin
- Role-based access control (RBAC)
- Internationalization (i18n) support for English and Russian
- Markdown CRUD for blog posts
- Custom fields: MarkdownField, TagsField, SlugField
