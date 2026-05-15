# Changelog Additions for v0.8.1

Add these entries to changelog.md:

## Features Added

### Environment Variables Configuration
- **FASTAPI_BLOG_INCLUDE_API**: Control REST API inclusion via environment variable
- **FASTAPI_BLOG_ADMIN_LOGIN**: Set admin username via environment variable
- **FASTAPI_BLOG_ADMIN_PASSWORD**: Set admin password via environment variable
- Priority: explicit parameter > environment variable > default value

### Internationalization Improvements
- Moved translations to YAML files (en.yaml, ru.yaml) for better maintainability
- Created i18n module with Translator class for convenient access
- Automatic locale name discovery from YAML files
- Better separation of concerns for translation management

### Role-Based Access Control (RBAC)
- Added Role model for defining custom roles
- Added UserWithRoles model for users with role assignments
- Many-to-many relationship between users and roles
- RoleModelView and UserWithRolesModelView admin views
- Built-in methods: has_role(), has_any_role()
- Default roles: admin, editor, viewer
- Separate admin section for role management

### Templates Restructure
- Renamed `layout/` to `layouts/` (plural) across all templates
- Created `layouts/` directory in admin templates
- Created `partials/` directory structure (reserved for future components)
- Consistent template organization between blog and admin
- Updated all template extends to use new paths

## Documentation Added

### New Documentation Files
- **docs/ENVIRONMENT_VARIABLES.md**: Complete guide to environment variable configuration
  - All available environment variables
  - Configuration examples for development and production
  - Docker and docker-compose examples
  - Security best practices
  - Troubleshooting guide

- **docs/ROLE_MANAGEMENT.md**: Comprehensive role management guide
  - Role and UserWithRoles model documentation
  - Setup instructions
  - Usage examples
  - Custom permissions implementation
  - Migration guide from simple User model
  - Database schema explanation

- **docs/TEMPLATES_STRUCTURE.md**: Template organization guide
  - Directory layout documentation
  - Naming conventions
  - Template inheritance examples
  - Best practices
  - Migration guide from old structure
  - Troubleshooting

## Examples Added

### New Example Files
- **tests/examples/with_env_vars.py**: Demonstrates environment variable usage
  - Shows FASTAPI_BLOG_INCLUDE_API usage
  - Shows admin credential configuration via env vars
  - Environment variable status display

- **tests/examples/with_roles.py**: Demonstrates role management
  - Shows how to add role management views
  - Example of Role and UserWithRoles usage
  - Multi-locale role management

## Technical Changes

### Code Improvements
- Fixed SQLAlchemy association table to use Column instead of mapped_column
- Added i18n module with load_translations() and Translator class
- Improved admin initialization with YAML-based translations
- Better type hints and documentation

### Testing
- All tests passing: 54 passed, 1 skipped
- No breaking changes to existing functionality
- Backward compatible with existing configurations

## Migration Guide

### For Users

#### Environment Variables (Optional)
```bash
# No changes required, but you can now use environment variables:
export FASTAPI_BLOG_INCLUDE_API=true
export FASTAPI_BLOG_ADMIN_LOGIN=myuser
export FASTAPI_BLOG_ADMIN_PASSWORD=mypass
```

#### Templates (Required if using custom templates)
If you have custom templates extending the base layout:

**Old:**
```jinja2
{% extends "layout/base.html" %}
```

**New:**
```jinja2
{% extends "layouts/base.html" %}
```

Run this to update automatically:
```bash
find templates/ -name "*.html" -exec sed -i 's|layout/base\.html|layouts/base.html|g' {} \;
```

#### Role Management (Optional)
If you want to use role management:

```python
from fastapi_blog.admin import RoleModelView, UserWithRolesModelView

admins = fastapi_blog.add_admin_to_app(app)

for locale, admin in admins.items():
    from fastapi_blog.admin.models_role import Role, UserWithRoles
    admin.add_view(RoleModelView(Role))
    admin.add_view(UserWithRolesModelView(UserWithRoles))
```

## Breaking Changes

**None** - All changes are backward compatible or opt-in.

## Deprecations

**None**

---

**Commit**: bef3131dbdc1f7c2a692e9741a86dc5038435b67  
**Date**: 2026-05-15
