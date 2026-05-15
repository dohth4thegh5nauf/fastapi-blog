# Template Isolation in Admin Panel

## Overview

The admin panel templates are completely isolated from public blog templates. This ensures:
- Admin cannot accidentally access or override public templates
- Clear separation of concerns between admin and public interfaces
- Better security and maintainability

## Implementation

### Template Loader Configuration

The admin panel uses starlette-admin's built-in template loader, which is configured automatically via the `templates_dir` parameter:

```python
# In src/fastapi_blog/admin/__init__.py
templates_dir = str(pkg_path / "admin" / "templates")

admin = Admin(
    engine,
    title=title,
    base_url=base_url,
    auth_provider=auth_provider,
    templates_dir=templates_dir,  # Points to admin/templates only
    i18n_config=i18n_config,
    debug=os.getenv("DEBUG", "false").lower() == "true",
    index_view=HomeView(label=home_label, icon="fa fa-home"),
)
```

### Jinja2 ChoiceLoader

Starlette-admin internally uses Jinja2's `ChoiceLoader` with the following priority:

1. **Custom templates** (`src/fastapi_blog/admin/templates/`)
2. **Built-in starlette-admin templates** (from package)
3. **Prefixed starlette-admin templates** (`@starlette-admin` prefix)

The public blog templates at `src/fastapi_blog/templates/` are **NOT** included in this loader chain.

## Directory Structure

```
src/fastapi_blog/
├── admin/
│   └── templates/          # Admin templates (isolated)
│       ├── layouts/
│       │   ├── base.html
│       │   └── custom_base.html
│       ├── partials/
│       ├── home.html
│       ├── login.html
│       └── ...
└── templates/              # Public blog templates (separate)
    ├── layouts/
    │   └── base.html
    ├── partials/
    ├── index.html
    ├── post.html
    └── ...
```

## Verification

### Automated Tests

The file `tests/test_admin_template_isolation.py` contains comprehensive tests:

1. **`test_admin_template_loader_isolation()`**
   - Verifies the template loader configuration
   - Checks that only admin/templates is in the search path
   - Confirms public templates directory is NOT included

2. **`test_admin_cannot_access_public_templates()`**
   - Attempts to load public-only templates (`post.html`, `posts.html`, etc.)
   - Verifies that `TemplateNotFound` exception is raised
   - Confirms complete isolation from public templates

3. **`test_admin_templates_directory_structure()`**
   - Validates directory structure
   - Checks for required `layouts/` and `partials/` subdirectories
   - Verifies `base.html` exists in layouts

### Manual Verification

You can verify template isolation manually:

```python
from fastapi import FastAPI
import fastapi_blog

app = FastAPI()
admins = fastapi_blog.add_admin_to_app(
    app,
    title="Test Admin",
    admin_username="admin",
    admin_password="Admin123!",
    secret_key="test-key",
)

# Get admin instance
admin = admins['en']

# Check loader configuration
loader = admin.templates.env.loader
print(f"Loader type: {type(loader)}")
print(f"Search paths: {loader.loaders[0].searchpath}")

# Try to access public template (should fail)
try:
    admin.templates.get_template("post.html")
    print("ERROR: Public template accessible!")
except Exception as e:
    print(f"OK: Public template blocked - {e}")
```

## Benefits

### Security
- Admin templates cannot accidentally expose public routes or data
- No risk of template injection between interfaces

### Maintainability
- Clear separation makes it easy to modify either interface independently
- No namespace collisions between admin and public templates

### Performance
- Smaller template search space for admin
- Faster template resolution

## Best Practices

### Adding New Admin Templates

When creating new admin templates:

1. Place them in `src/fastapi_blog/admin/templates/`
2. For reusable components, use `partials/` directory
3. For layouts, use `layouts/` directory
4. Never reference public templates from admin templates

### Template Naming

- Use `base.html` for main layout (consistent with public templates)
- Prefix partials with `_` (convention)
- Use descriptive names that indicate admin context

### Extending Templates

Admin templates can extend:
- ✅ Other admin templates (`{% extends "layouts/base.html" %}`)
- ✅ Built-in starlette-admin templates
- ❌ Public blog templates (not accessible)

## Troubleshooting

### Template Not Found

If you get `TemplateNotFound` errors:

1. Check that template exists in `src/fastapi_blog/admin/templates/`
2. Verify template name matches exactly (case-sensitive)
3. Check extends/include paths are relative to admin/templates/

### Wrong Template Loaded

If the wrong template is being used:

1. Check template name doesn't conflict with starlette-admin built-ins
2. Custom templates take priority over built-in ones
3. Use unique names or organize in subdirectories

## Related Documentation

- [Template Structure](TEMPLATES_STRUCTURE.md) - Overall template organization
- [Role Management](ROLE_MANAGEMENT.md) - Admin features including custom templates
- [Environment Variables](ENVIRONMENT_VARIABLES.md) - Configuration options
