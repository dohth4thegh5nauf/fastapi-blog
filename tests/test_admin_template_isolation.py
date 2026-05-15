"""Test admin template isolation from public templates."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from jinja2.loaders import ChoiceLoader, FileSystemLoader, PackageLoader

import fastapi_blog


@pytest.fixture
def app_with_admin():
    """Create FastAPI app with admin panel."""
    app = FastAPI()
    admins = fastapi_blog.add_admin_to_app(
        app,
        title="Test Admin",
        admin_username="admin",
        admin_password="Admin123!",
        secret_key="test-secret-key",
        i18n_enabled=False,  # Disable i18n to get single admin instance
    )
    return app, admins


def test_admin_template_loader_isolation(app_with_admin):
    """Verify admin template loader only includes admin/templates directory."""
    app, admins = app_with_admin

    # Get first admin instance (should be 'en' when i18n is disabled)
    assert len(admins) > 0, "No admin instances found"
    admin = list(admins.values())[0]

    # Check template loader configuration
    loader = admin.templates.env.loader
    assert isinstance(loader, ChoiceLoader), "Expected ChoiceLoader"

    # Verify loaders in ChoiceLoader
    loaders = loader.loaders
    assert len(loaders) >= 2, "Expected at least 2 loaders"

    # First loader should be FileSystemLoader pointing to admin/templates
    first_loader = loaders[0]
    assert isinstance(first_loader, FileSystemLoader), (
        "First loader should be FileSystemLoader"
    )

    # Get the searchpath from FileSystemLoader
    searchpath = first_loader.searchpath
    assert len(searchpath) == 1, "Should have exactly one search path"

    admin_templates_path = Path(searchpath[0])
    assert admin_templates_path.name == "templates", (
        "Should point to templates directory"
    )
    assert admin_templates_path.parent.name == "admin", (
        "Should be inside admin directory"
    )

    # Verify second loader is PackageLoader for starlette_admin
    second_loader = loaders[1]
    assert isinstance(second_loader, PackageLoader), (
        "Second loader should be PackageLoader"
    )
    assert second_loader.package_name == "starlette_admin", (
        "Should load from starlette_admin package"
    )

    # Verify public templates directory is NOT in the loader path
    public_templates_path = admin_templates_path.parent.parent / "templates"
    assert str(public_templates_path) not in searchpath, (
        "Public templates should not be accessible"
    )


def test_admin_cannot_access_public_templates(app_with_admin):
    """Verify admin templates cannot access public blog templates."""
    from jinja2.exceptions import TemplateNotFound

    app, admins = app_with_admin

    # Get first admin instance
    assert len(admins) > 0, "No admin instances found"
    admin = list(admins.values())[0]

    # Try to get templates that exist only in public templates
    # These should raise TemplateNotFound because public templates are not in the loader
    public_only_templates = ["post.html", "posts.html", "tag.html", "tags.html"]

    for template_name in public_only_templates:
        with pytest.raises(TemplateNotFound, match=template_name):
            admin.templates.get_template(template_name)


def test_admin_templates_directory_structure():
    """Verify admin templates directory has correct structure."""
    pkg_path = Path(fastapi_blog.__file__).parent
    admin_templates = pkg_path / "admin" / "templates"

    assert admin_templates.exists(), "Admin templates directory should exist"
    assert admin_templates.is_dir(), "Admin templates should be a directory"

    # Check for required subdirectories
    layouts_dir = admin_templates / "layouts"
    partials_dir = admin_templates / "partials"

    assert layouts_dir.exists(), "layouts/ directory should exist"
    assert partials_dir.exists(), "partials/ directory should exist"

    # Verify base.html exists in layouts
    base_html = layouts_dir / "base.html"
    assert base_html.exists(), "base.html should exist in layouts/"

    # Verify public templates are separate
    public_templates = pkg_path / "templates"
    assert public_templates.exists(), "Public templates should exist"
    assert public_templates != admin_templates, (
        "Admin and public templates should be separate"
    )
