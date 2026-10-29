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


def test_home_and_markdown_pages_extend_the_unified_layout():
  """home.html/markdown_list.html/markdown_edit.html share one layout.

  They used to extend the project's own `layouts/custom_base.html` (a
  separate dark-themed chain the built-in Role/User pages never saw). Now
  they extend the same `layout.html` the built-in pages inherit through
  (see `test_list_template_extends_stock` and friends above), so the theme
  toggle and language switcher render identically everywhere.
  """
  for name in ('home.html', 'markdown_list.html', 'markdown_edit.html'):
    content = _read(name)
    assert '{% extends "layout.html" %}' in content, name


def test_login_extends_the_stock_layout_directly():
  """login.html's switchers/styling don't need `navbar_extra`.

  It builds its own self-contained switchers (there is no logged-in navbar
  to hook into), so it extends the framework's layout directly rather than
  the shared `layout.html`.
  """
  content = _read('login.html')
  assert '{% extends "@starlette-admin/layout.html" %}' in content


def test_layout_html_exists():
  """Verify the unified layout.html exists."""
  layout = ADMIN_TEMPLATES / 'layout.html'
  assert layout.exists(), 'layout.html must exist'


def test_layout_html_contains_theme_and_language_markers():
  """Verify layout.html adds the theme toggle and language switcher."""
  layout = (ADMIN_TEMPLATES / 'layout.html').read_text()
  assert 'theme-toggle' in layout
  assert 'navbar_extra' in layout
  assert 'custom-language-item' in layout
