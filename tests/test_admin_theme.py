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
  than the built-in Role/User pages, which don't add one.
  """
  for name in ('home.html', 'markdown_list.html'):
    content = _read(name)
    assert 'container-fluid' not in content, name
    assert 'container-xl' not in content, name

  edit_content = _read('markdown_edit.html')
  assert 'container-fluid' not in edit_content
  assert 'container-xl' not in edit_content


def test_home_page_header_matches_the_plain_h1_pattern():
  """home.html's header block must match every other page's structure.

  It used to wrap an `<h2 class="page-title">` in a `.row.g-2` grid, while
  every other page (the stock `@starlette-admin/list.html` for Users/Roles,
  and this project's own markdown_list.html/markdown_edit.html) uses a
  plain `<h1>` directly inside the `.d-flex` header. The row/col wrapper
  rendered a shorter `.page-header`, which pushed Home's content a few
  pixels higher than every other page's — not visible at a glance, only as
  a slight vertical misalignment when switching between pages.
  """
  content = _read('home.html')
  assert '<h1>{{ t.title }}</h1>' in content
  assert 'page-title' not in content
  assert 'row g-2' not in content


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


def test_layout_has_shared_responsive_card_header_and_button_metrics():
  layout = (ADMIN_TEMPLATES / 'layout.html').read_text()
  assert '.card-header .btn {' in layout
  assert '.card-header .card-title {' in layout
  assert 'align-items: center' in layout
  assert 'height: 2.25rem' in layout
  assert 'padding: .5rem .875rem' in layout
  assert '@media (max-width: 991.98px)' in layout
  assert '.card-header .card-actions' in layout


def test_layout_fixes_dark_editor_toolbar_and_navbar_transition_delay():
  layout = (ADMIN_TEMPLATES / 'layout.html').read_text()
  assert "html[data-bs-theme='dark'] .editor-toolbar a:hover" in layout
  assert 'transition-delay: 0s !important' in layout


def test_post_list_uses_readable_badges_and_compact_action_icons():
  listing = _read('markdown_list.html')
  assert 'bg-success-lt text-success' in listing
  assert 'bg-warning-lt text-warning' in listing
  layout = (ADMIN_TEMPLATES / 'layout.html').read_text()
  assert '--tblr-badge-padding-y: 4px' in layout
  assert '--tblr-badge-padding-x: 4px' in layout
  assert listing.count('width="1em" height="1em"') >= 2
  assert 'd-none d-sm-inline-block' not in listing


def test_admin_and_public_layouts_declare_inline_favicons():
  admin_layout = (ADMIN_TEMPLATES / 'layout.html').read_text()
  public_layout = (
    Path(__file__).parents[1]
    / 'src'
    / 'fastapi_blog'
    / 'templates'
    / 'layouts'
    / 'base.html'
  ).read_text()
  assert 'rel="icon"' in admin_layout
  assert 'rel="icon"' in public_layout
  assert 'data:image/svg+xml,' in admin_layout
  assert 'data:image/svg+xml,' in public_layout


def test_diagnostics_heading_has_a_full_width_block():
  editor = _read('markdown_edit.html')
  assert '<div class="w-100">' in editor
  assert '<h4 class="mb-2">Document diagnostics</h4>' in editor


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


def test_sidebar_width_override_is_scoped_to_the_lg_breakpoint():
  """`width: 14rem` must not apply below 992px.

  Tabler's own `.navbar-vertical.navbar-expand-lg{width:15rem}` is
  unscoped in its CSS text, but a *separate*, higher-specificity mobile
  rule resets the sidebar to an in-flow, full-width bar below 992px
  (confirmed live: `position: relative`, width matching the viewport).
  An unscoped `width: 14rem` override here fights that reset and pins the
  sidebar's own mobile header row to 224px instead of the viewport's full
  width — this was reported as "the header shrinks in width below 992px".
  """
  layout = (ADMIN_TEMPLATES / 'layout.html').read_text()
  media_start = layout.index('@media (min-width: 992px)')
  media_body_start = layout.index('{', media_start)
  depth = 1
  i = media_body_start + 1
  while depth > 0:
    if layout[i] == '{':
      depth += 1
    elif layout[i] == '}':
      depth -= 1
    i += 1
  media_body = layout[media_body_start:i]
  assert 'width: 14rem' in media_body
  # Only one `width: 14rem` in the whole file: inside this media query.
  assert layout.count('width: 14rem') == media_body.count('width: 14rem')


def test_layout_html_keeps_the_switchers_visible_below_the_lg_breakpoint():
  """The theme/language switchers must not vanish below 992px.

  Tabler hides `header.navbar` entirely below `lg` (`d-none d-lg-flex`),
  and the sidebar's own mobile row has no hook for our content, so the
  switchers (added via the `navbar_extra` block, which only renders inside
  `header.navbar`) simply disappeared there until this was added.
  """
  layout = (ADMIN_TEMPLATES / 'layout.html').read_text()
  assert '@media (max-width: 991.98px)' in layout
  assert 'header.navbar.navbar-expand-md' in layout
  assert 'display: flex !important' in layout
