"""Test role management access control."""

from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from starlette.requests import Request

import fastapi_blog
from fastapi_blog.admin.views_role import RoleModelView, UserWithRolesModelView


@pytest.fixture
def app_with_roles():
    """Create FastAPI app with role management enabled."""
    app = FastAPI()
    admins = fastapi_blog.add_admin_to_app(
        app,
        title="Test Admin",
        admin_username="admin",
        admin_password="Admin123!",
        secret_key="test-secret-key",
        enable_role_management=True,
    )
    return app, admins


def test_admin_username_passed_to_views(app_with_roles):
    """Verify admin_username is passed to role management views."""
    from starlette_admin import DropDown

    app, admins = app_with_roles

    # Check that role views have admin_username set
    for locale, admin in admins.items():
        for view in admin._views:
            if isinstance(view, DropDown):
                for subview in view.views:
                    if isinstance(subview, (RoleModelView, UserWithRolesModelView)):
                        assert hasattr(subview, "admin_username"), (
                            f"{type(subview).__name__} missing admin_username attribute"
                        )
                        assert subview.admin_username == "admin", (
                            f"{type(subview).__name__} has wrong admin_username"
                        )


def test_role_views_registered_when_enabled(app_with_roles):
    """Verify role views are registered when enable_role_management=True."""
    from starlette_admin import DropDown

    app, admins = app_with_roles

    # Check both locales have role management dropdown in menu
    for locale, admin in admins.items():
        views = admin._views

        # Find DropDown for role management
        role_dropdown = None
        for view in views:
            if isinstance(view, DropDown):
                # Check if this is the role management dropdown by label
                expected_label = (
                    "Access Control" if locale == "en" else "Управление доступом"
                )
                if view.label == expected_label:
                    role_dropdown = view
                    break

        assert role_dropdown is not None, (
            f"Role management DropDown not found in {locale} admin"
        )

        # Check that dropdown contains both role views
        dropdown_view_types = [type(v).__name__ for v in role_dropdown.views]
        assert "RoleModelView" in dropdown_view_types, (
            f"RoleModelView not in dropdown for {locale}"
        )
        assert "UserWithRolesModelView" in dropdown_view_types, (
            f"UserWithRolesModelView not in dropdown for {locale}"
        )


def test_role_view_accessible_only_for_root_user(app_with_roles):
    """Test that RoleModelView is only accessible for root admin user."""
    from starlette_admin import DropDown

    app, admins = app_with_roles

    # Create mock request
    request = Mock(spec=Request)
    request.app.state.admin_username = "admin"

    # Get role view from first admin's dropdown
    admin = list(admins.values())[0]
    role_view = None
    for view in admin._views:
        if isinstance(view, DropDown):
            for subview in view.views:
                if isinstance(subview, RoleModelView):
                    role_view = subview
                    break
            if role_view:
                break

    assert role_view is not None, "RoleModelView not found in dropdown"

    # Test root user access
    request.session = {"user": "admin"}
    assert role_view.is_accessible(request) is True
    assert role_view.can_view_details(request) is True
    assert role_view.can_create(request) is True
    assert role_view.can_edit(request) is True
    assert role_view.can_delete(request) is True

    # Test non-root user access
    request.session = {"user": "other_user"}
    assert role_view.is_accessible(request) is False
    assert role_view.can_view_details(request) is False
    assert role_view.can_create(request) is False
    assert role_view.can_edit(request) is False
    assert role_view.can_delete(request) is False

    # Test no user
    request.session = {}
    assert role_view.is_accessible(request) is False


def test_user_roles_view_accessible_only_for_root_user(app_with_roles):
    """Test that UserWithRolesModelView is only accessible for root admin user."""
    from starlette_admin import DropDown

    app, admins = app_with_roles

    # Create mock request
    request = Mock(spec=Request)
    request.app.state.admin_username = "admin"

    # Get user roles view from first admin's dropdown
    admin = list(admins.values())[0]
    user_roles_view = None
    for view in admin._views:
        if isinstance(view, DropDown):
            for subview in view.views:
                if isinstance(subview, UserWithRolesModelView):
                    user_roles_view = subview
                    break
            if user_roles_view:
                break

    assert user_roles_view is not None, "UserWithRolesModelView not found in dropdown"

    # Test root user access
    request.session = {"user": "admin"}
    assert user_roles_view.is_accessible(request) is True
    assert user_roles_view.can_view_details(request) is True
    assert user_roles_view.can_create(request) is True
    assert user_roles_view.can_edit(request) is True
    assert user_roles_view.can_delete(request) is True

    # Test non-root user access
    request.session = {"user": "other_user"}
    assert user_roles_view.is_accessible(request) is False
    assert user_roles_view.can_view_details(request) is False
    assert user_roles_view.can_create(request) is False
    assert user_roles_view.can_edit(request) is False
    assert user_roles_view.can_delete(request) is False

    # Test no user
    request.session = {}
    assert user_roles_view.is_accessible(request) is False


def test_role_views_use_translations(app_with_roles):
    """Test that role views use translated labels."""
    from starlette_admin import DropDown

    app, admins = app_with_roles

    # Check English admin
    en_admin = admins.get("en")
    assert en_admin is not None

    role_view_en = None
    user_roles_view_en = None
    for view in en_admin._views:
        if isinstance(view, DropDown):
            for subview in view.views:
                if isinstance(subview, RoleModelView):
                    role_view_en = subview
                elif isinstance(subview, UserWithRolesModelView):
                    user_roles_view_en = subview

    assert role_view_en is not None
    assert role_view_en.label == "Roles"

    assert user_roles_view_en is not None
    assert user_roles_view_en.label == "User Roles"

    # Check Russian admin
    ru_admin = admins.get("ru")
    assert ru_admin is not None

    role_view_ru = None
    user_roles_view_ru = None
    for view in ru_admin._views:
        if isinstance(view, DropDown):
            for subview in view.views:
                if isinstance(subview, RoleModelView):
                    role_view_ru = subview
                elif isinstance(subview, UserWithRolesModelView):
                    user_roles_view_ru = subview

    assert role_view_ru is not None
    assert role_view_ru.label == "Роли"

    assert user_roles_view_ru is not None
    assert user_roles_view_ru.label == "Роли пользователей"


def test_role_management_disabled_by_default():
    """Test that role management is not enabled by default."""
    from starlette_admin import DropDown

    app = FastAPI()
    admins = fastapi_blog.add_admin_to_app(
        app,
        title="Test Admin",
        admin_username="admin",
        admin_password="Admin123!",
        secret_key="test-secret-key",
        # enable_role_management is False by default
    )

    # Check that role management dropdown is NOT present
    for locale, admin in admins.items():
        views = admin._views

        # Look for role management dropdown
        role_dropdown_found = False
        for view in views:
            if isinstance(view, DropDown):
                expected_label = (
                    "Access Control" if locale == "en" else "Управление доступом"
                )
                if view.label == expected_label:
                    role_dropdown_found = True
                    break

        assert not role_dropdown_found, (
            f"Role management DropDown should not be in {locale} admin when disabled"
        )


def test_role_dropdown_has_correct_label(app_with_roles):
    """Test that role management dropdown has correct translated label."""
    from starlette_admin import DropDown

    app, admins = app_with_roles

    # Check English admin
    en_admin = admins.get("en")
    assert en_admin is not None

    en_dropdown = None
    for view in en_admin._views:
        if isinstance(view, DropDown) and view.label == "Access Control":
            en_dropdown = view
            break

    assert en_dropdown is not None
    assert en_dropdown.label == "Access Control"
    assert en_dropdown.icon == "fa fa-shield"

    # Check Russian admin
    ru_admin = admins.get("ru")
    assert ru_admin is not None

    ru_dropdown = None
    for view in ru_admin._views:
        if isinstance(view, DropDown) and view.label == "Управление доступом":
            ru_dropdown = view
            break

    assert ru_dropdown is not None
    assert ru_dropdown.label == "Управление доступом"
    assert ru_dropdown.icon == "fa fa-shield"


def test_role_dropdown_not_accessible_for_non_root_user(app_with_roles):
    """Test that role management dropdown is not accessible for non-root users."""
    from unittest.mock import Mock

    from starlette_admin import DropDown

    app, admins = app_with_roles

    # Create mock request for non-root user
    request = Mock(spec=Request)
    request.app.state.admin_username = "admin"
    request.session = {"user": "other_user"}

    # Get admin instance
    admin = list(admins.values())[0]

    # Find role management dropdown
    role_dropdown = None
    for view in admin._views:
        if isinstance(view, DropDown) and view.label in [
            "Access Control",
            "Управление доступом",
        ]:
            role_dropdown = view
            break

    assert role_dropdown is not None, "Role management dropdown not found"

    # DropDown.is_accessible checks if ANY nested view is accessible
    # Since all nested views check for root user, dropdown should be inaccessible
    assert not role_dropdown.is_accessible(request), (
        "Role dropdown should not be accessible to non-root user"
    )

    # Now check for root user - should have access
    request.session = {"user": "admin"}
    assert role_dropdown.is_accessible(request), (
        "Role dropdown should be accessible to root user"
    )
