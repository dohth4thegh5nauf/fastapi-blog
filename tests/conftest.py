"""Shared pytest configuration.

The core install has no extras, so test modules that exercise the admin panel
(or sessions) can't be imported there. They are skipped when the `admin` extra
is missing. Modules named `test_core_*` must work in both setups.
"""

import importlib.util
import pathlib
import re


# Anything in a test module that needs the `admin` extra
_NEEDS_ADMIN = re.compile(
  r'setup_fastapi_blog|fastapi_blog\.admin|add_admin_to_app|starlette_admin'
  r'|sqlalchemy|SessionMiddleware|itsdangerous'
)


def _admin_extra_installed() -> bool:
  return importlib.util.find_spec('starlette_admin') is not None


def pytest_ignore_collect(collection_path: pathlib.Path) -> bool | None:
  if _admin_extra_installed():
    return None
  name = collection_path.name
  if not (name.startswith('test_') and name.endswith('.py')):
    return None
  if name.startswith('test_core_'):
    return None
  text = collection_path.read_text(encoding='utf-8')
  # Tests that use the admin only via the facade still need the extra
  return True if _NEEDS_ADMIN.search(text) else None
