"""Tests for theme switcher template inheritance."""

from pathlib import Path

import fastapi_blog


PKG = Path(fastapi_blog.__file__).parent
ADMIN_TEMPLATES = PKG / "admin" / "templates"


def _read(name: str) -> str:
    """Read template file content."""
    return (ADMIN_TEMPLATES / name).read_text()


def test_list_template_extends_base():
    """Verify list.html extends base template."""
    content = _read("list.html")
    assert "{% extends" in content
    # Note: extends custom_base.html, not base.html directly
    assert "custom_base.html" in content or "base.html" in content


def test_detail_template_extends_base():
    """Verify detail.html extends base template."""
    content = _read("detail.html")
    assert "{% extends" in content
    assert "custom_base.html" in content or "base.html" in content


def test_create_template_extends_base():
    """Verify create.html extends base template."""
    content = _read("create.html")
    assert "{% extends" in content
    assert "custom_base.html" in content or "base.html" in content


def test_edit_template_extends_base():
    """Verify edit.html extends base template."""
    content = _read("edit.html")
    assert "{% extends" in content
    assert "custom_base.html" in content or "base.html" in content


def test_base_html_exists_in_layouts():
    """Verify base.html exists in layouts directory."""
    base = ADMIN_TEMPLATES / "layouts" / "base.html"
    assert base.exists(), "layouts/base.html must exist"


def test_base_html_contains_theme_marker():
    """Verify base.html contains theme switcher markers."""
    base = (ADMIN_TEMPLATES / "layouts" / "base.html").read_text()
    # base should contain theme-related markers
    assert any(
        marker in base for marker in ["theme", "dark", "data-bs-theme", "color-scheme"]
    ), "base.html must contain theme marker"
