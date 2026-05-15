"""Test admin template isolation from public templates."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from jinja2.loaders import ChoiceLoader, FileSystemLoader, PrefixLoader

import fastapi_blog


@pytest.fixture
def app_with_admin():
    app = FastAPI()
    admins = fastapi_blog.add_admin_to_app(
        app,
        title="Test Admin",
        admin_username="admin",
        admin_password="Admin123!",
        secret_key="test-secret-key",
        locales=["en"],        # instead of i18n_enabled=False
        default_locale="en",
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

    # Collect all FileSystemLoader search paths recursively
    def collect_filesystem_paths(loader_obj, paths=None):
        if paths is None:
            paths = []
        if isinstance(loader_obj, FileSystemLoader):
            paths.extend(loader_obj.searchpath)
        elif isinstance(loader_obj, ChoiceLoader):
            for sub_loader in loader_obj.loaders:
                collect_filesystem_paths(sub_loader, paths)
        elif isinstance(loader_obj, PrefixLoader):
            for sub_loader in loader_obj.mapping.values():
                collect_filesystem_paths(sub_loader, paths)
        return paths

    all_fs_paths = collect_filesystem_paths(loader)

    # Verify at least one path points to admin/templates
    admin_templates_found = False
    for path_str in all_fs_paths:
        path = Path(path_str)
        if path.name == "templates" and path.parent.name == "admin":
            admin_templates_found = True
            break

    assert admin_templates_found, "Admin templates path not found in loader"

    # Verify public templates directory is NOT in any FileSystemLoader path
    pkg_path = Path(fastapi_blog.__file__).parent
    public_templates_path = pkg_path / "templates"

    for path_str in all_fs_paths:
        path = Path(path_str).resolve()
        public_path = public_templates_path.resolve()
        assert path != public_path, (
            f"Public templates path {public_path} should not be in loader, "
            f"found: {path}"
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
    # Note: index.html exists in starlette-admin built-ins, so excluded from this test
    public_only_templates = [
        "page.html",
        "post.html",
        "posts.html",
        "tag.html",
        "tags.html",
    ]

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
