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


def test_home_and_markdown_pages_dont_double_wrap_the_container():
  """A page must not add its own top-level `.container-*` wrapper.

  `{% block content %}` already sits inside the layout's `.container-xl`
  (see `@starlette-admin/templates/layout.html`'s `.page-body`), so doing
  it again double-nests the gutter padding and ends up a different width
  than the built-in Role/User pages, which don't add one. `markdown_edit.
  html` still nests a `container-fluid` *inside* its card header for
  internal spacing — that one is fine, it isn't a second top-level wrapper.
  """
  for name in ('home.html', 'markdown_list.html'):
    content = _read(name)
    assert 'container-fluid' not in content, name
    assert 'container-xl' not in content, name

  edit_content = _read('markdown_edit.html')
  # Exactly one container-fluid: the card-header's internal one.
  assert edit_content.count('container-fluid') == 1


def test_no_project_login_override():
  """There is no project override of login.html any more.

  It used to duplicate the stock login page (dark theme, its own
  hand-rolled theme/language switchers) for no real reason: the stock
  `@starlette-admin/login.html` extends the bare `"layout.html"` name too,
  so it already inherits this project's theme via the shadowed
  `layout.html` (the `navbar` block just doesn't render pre-login, since
  there's no `current_user` yet — nothing project-specific to add). Letting
  the framework serve its own login page keeps it visually identical to
  every other page with zero duplicated code, and `SimpleAuthProvider.
  render_login` (see `admin/auth_provider.py`) only needs to swap in the
  project's YAML-based `_` translator via the template context.
  """
  assert not (ADMIN_TEMPLATES / 'login.html').exists()


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


def test_layout_html_pins_the_top_navbar_while_scrolling():
  """The top navbar (theme/language/user menu) must stay on screen.

  It used to scroll away with the page content, unlike the sidebar (which
  is `position: fixed`). `header.navbar` is `position: sticky` here for
  exactly that reason.
  """
  layout = (ADMIN_TEMPLATES / 'layout.html').read_text()
  assert 'header.navbar' in layout
  assert 'position: sticky' in layout


def test_layout_html_removes_the_dead_sidebar_scrollbar():
  """The sidebar must not reserve a permanent scrollbar gutter.

  Tabler hardcodes `overflow-y: scroll` on the sidebar, so even a menu
  nowhere near tall enough to need scrolling still shows a non-functional
  scrollbar. `layout.html` overrides it to `auto`.
  """
  layout = (ADMIN_TEMPLATES / 'layout.html').read_text()
  assert 'navbar-vertical' in layout
  assert 'overflow-y: auto' in layout


def test_layout_html_reserves_a_stable_scrollbar_gutter():
  """`.container-xl` must sit at the same x position on every page.

  It's centered with `margin: auto` in `.page-wrapper`, so its position
  depends on the viewport's content width, which a short page (no
  scrollbar) and a tall page (scrollbar present) disagree on by the
  scrollbar's own width unless that space is always reserved.
  """
  layout = (ADMIN_TEMPLATES / 'layout.html').read_text()
  assert 'scrollbar-gutter: stable' in layout


def test_layout_html_narrows_the_sidebar_to_14rem():
  """The sidebar is 14rem wide, not Tabler's stock 15rem.

  The sidebar's own width and the margin-left Tabler puts on its siblings
  (`.navbar`, `.page-wrapper`) must change together, or the content either
  starts under the sidebar or leaves a gap next to it.
  """
  layout = (ADMIN_TEMPLATES / 'layout.html').read_text()
  assert 'width: 14rem' in layout
  assert 'margin-left: 14rem' in layout
