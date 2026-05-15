# Contributing to fastapi-blog

Thank you for your interest in contributing to fastapi-blog!

## 🚀 Quick Start

```bash
# Clone and setup
git clone https://github.com/pydanny/fastapi-blog.git
cd fastapi-blog
make install

# Run tests
make test
```

## 🧪 Running Tests

```bash
make test          # All tests with coverage
make lint          # Ruff check + format
make mypy          # Type checking
make all           # Run everything (lint + mypy + test)
```

## 📝 Code Style

We use:
- **ruff** for linting and formatting
- **mypy** for type checking
- **pytest** for testing

### Style Guidelines

- Use type annotations for all public APIs
- Follow PEP 8 (enforced by ruff)
- Write docstrings for public functions
- Keep functions focused and small
- Use descriptive variable names

### Example

```python
def add_admin_to_app(
    app: FastAPI,
    *,
    admin_username: str | None = None,
    admin_password: str | None = None,
) -> dict[str, Admin]:
    """Add admin panel to FastAPI application.
    
    Args:
        app: FastAPI application instance
        admin_username: Admin username (default: from env)
        admin_password: Admin password (default: from env)
    
    Returns:
        Dictionary mapping locale codes to Admin instances
    """
    ...
```

## 🔄 Pull Request Process

1. **Fork** the repository
2. **Create a branch** from `main`: `git checkout -b feature/my-feature`
3. **Make your changes** with tests
4. **Run all checks**: `make all`
5. **Commit** with clear messages
6. **Push** and create a Pull Request

### Commit Message Format

```
<type>: <subject>

<body>
```

Types:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation only
- `test:` - Adding tests
- `refactor:` - Code refactoring
- `chore:` - Maintenance tasks

Example:
```
feat: add role-based access control

- Add RoleModelView for role management
- Implement is_accessible() checks
- Add tests for RBAC functionality
```

## 🌍 Adding a New Locale

1. Create translation file: `src/fastapi_blog/admin/translations/{locale}.yaml`

```yaml
nav:
  home: "Home"
  users: "Users"
  posts: "Posts"

user:
  singular: "User"
  plural: "Users"
  
# ... more translations
```

2. Update `get_all_locale_names()` in `src/fastapi_blog/admin/i18n.py`

3. Add example in `tests/examples/admin_i18n.py`

4. Test with `locales=["en", "your_locale"]`

## 🎨 Adding a Custom ModelView

```python
from starlette_admin import ModelView

class MyCustomView(ModelView):
    """Custom admin view."""
    
    # Configuration
    label = "My Model"
    icon = "fa fa-star"
    
    # Fields
    fields = ["id", "name", "created_at"]
    
    # Access control
    def is_accessible(self, request: Request) -> bool:
        return request.session.get("user") == "admin"
```

## 📦 Adding Dependencies

Dependencies are managed in `pyproject.toml`:

```toml
[project]
dependencies = [
    "new-package>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "new-dev-tool>=2.0.0",
]
```

After adding, run:
```bash
make install
```

## 🐛 Reporting Bugs

Include:
- Python version
- FastAPI Blog version
- Minimal reproduction code
- Expected vs actual behavior
- Full error traceback

## 💡 Feature Requests

- Check existing issues first
- Describe use case clearly
- Explain why it's useful
- Consider implementation approach

## ❓ Questions

- Check [README.md](README.md) and [QUICKSTART.md](QUICKSTART.md)
- Review [documentation](docs/)
- Search existing issues
- Ask in discussions

## 📄 License

By contributing, you agree that your contributions will be licensed under the same license as the project.
