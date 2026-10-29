"""Tests for theme switcher template inheritance."""

from pathlib import Path

import fastapi_blog


PKG = Path(fastapi_blog.__file__).parent
ADMIN_TEMPLATES = PKG / 'admin' / 'templates'


def _read(name: str) -> str:
  """Read template file content."""
  return (ADMIN_TEMPLATES / name).read_text()


def test_list_template_extends_stock():
  """list.html extends the built-in @starlette-admin/list.html.

  starlette-admin 1.0 replaced the DataTables-based list/detail/edit/create
  rendering with server-rendered templates built from a new set of partials
  (filters, column visibility, inline edit, ...). Re-theming that from
  scratch isn't practical, so these 4 ModelView pages (Role/User management)
  use the stock theme rather than `layouts/custom_base.html`; the blog's own
  post editor pages keep the custom dark theme (see `home.html`,
  `markdown_list.html`, `markdown_edit.html`, which are unaffected).
  """
  content = _read('list.html')
  assert '{% extends "@starlette-admin/list.html" %}' in content


def test_detail_template_extends_stock():
  """detail.html extends the built-in @starlette-admin/detail.html."""
  content = _read('detail.html')
  assert '{% extends "@starlette-admin/detail.html" %}' in content


def test_create_template_extends_stock():
  """create.html extends the built-in @starlette-admin/create.html."""
  content = _read('create.html')
  assert '{% extends "@starlette-admin/create.html" %}' in content


def test_edit_template_extends_stock():
  """edit.html extends the built-in @starlette-admin/edit.html."""
  content = _read('edit.html')
  assert '{% extends "@starlette-admin/edit.html" %}' in content


def test_custom_base_extends_base():
  """Verify custom_base.html extends base.html."""
  content = _read('layouts/custom_base.html')
  assert '{% extends "layouts/base.html" %}' in content, (
    'custom_base.html must extend layouts/base.html'
  )


def test_base_html_exists_in_layouts():
  """Verify base.html exists in layouts directory."""
  base = ADMIN_TEMPLATES / 'layouts' / 'base.html'
  assert base.exists(), 'layouts/base.html must exist'


def test_base_html_contains_theme_marker():
  """Verify base.html contains theme switcher markers."""
  base = (ADMIN_TEMPLATES / 'layouts' / 'base.html').read_text()
  # base should contain theme-related markers
  assert any(
    marker in base
    for marker in ['theme', 'dark', 'data-bs-theme', 'color-scheme']
  ), 'base.html must contain theme marker'
