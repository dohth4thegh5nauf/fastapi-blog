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


def test_admin_username_stored_in_app_state(app_with_roles):
    """Verify admin_username is stored in app.state."""
    app, admins = app_with_roles

    assert hasattr(app.state, "admin_username")
    assert app.state.admin_username == "admin"


def test_role_views_registered_when_enabled(app_with_roles):
    """Verify role views are registered when enable_role_management=True."""
    app, admins = app_with_roles

    # Check both locales have role views
    for locale, admin in admins.items():
        views = admin._views
        view_identities = [
            getattr(v, "identity", None) for v in views if hasattr(v, "identity")
        ]

        assert "role" in view_identities, f"RoleModelView not found in {locale} admin"
        assert "user_with_roles" in view_identities, (
            f"UserWithRolesModelView not found in {locale} admin"
        )


def test_role_view_accessible_only_for_root_user(app_with_roles):
    """Test that RoleModelView is only accessible for root admin user."""
    app, admins = app_with_roles

    # Create mock request
    request = Mock(spec=Request)
    request.app.state.admin_username = "admin"

    # Get role view from first admin
    admin = list(admins.values())[0]
    role_view = None
    for view in admin._views:
        if isinstance(view, RoleModelView):
            role_view = view
            break

    assert role_view is not None, "RoleModelView not found"

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
    app, admins = app_with_roles

    # Create mock request
    request = Mock(spec=Request)
    request.app.state.admin_username = "admin"

    # Get user roles view from first admin
    admin = list(admins.values())[0]
    user_roles_view = None
    for view in admin._views:
        if isinstance(view, UserWithRolesModelView):
            user_roles_view = view
            break

    assert user_roles_view is not None, "UserWithRolesModelView not found"

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
    app, admins = app_with_roles

    # Check English admin
    en_admin = admins.get("en")
    assert en_admin is not None

    role_view_en = None
    user_roles_view_en = None
    for view in en_admin._views:
        if isinstance(view, RoleModelView):
            role_view_en = view
        elif isinstance(view, UserWithRolesModelView):
            user_roles_view_en = view

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
        if isinstance(view, RoleModelView):
            role_view_ru = view
        elif isinstance(view, UserWithRolesModelView):
            user_roles_view_ru = view

    assert role_view_ru is not None
    assert role_view_ru.label == "Роли"

    assert user_roles_view_ru is not None
    assert user_roles_view_ru.label == "Роли пользователей"


def test_role_management_disabled_by_default():
    """Test that role management is not enabled by default."""
    app = FastAPI()
    admins = fastapi_blog.add_admin_to_app(
        app,
        title="Test Admin",
        admin_username="admin",
        admin_password="Admin123!",
        secret_key="test-secret-key",
        # enable_role_management is False by default
    )

    # Check that role views are NOT registered
    for locale, admin in admins.items():
        views = admin._views
        view_identities = [
            getattr(v, "identity", None) for v in views if hasattr(v, "identity")
        ]

        assert "role" not in view_identities, (
            f"RoleModelView should not be in {locale} admin"
        )
        assert "user_with_roles" not in view_identities, (
            f"UserWithRolesModelView should not be in {locale} admin"
        )


def test_role_views_have_category(app_with_roles):
    """Test that role views have category set from translations."""
    app, admins = app_with_roles

    # Check English admin
    en_admin = admins.get("en")
    assert en_admin is not None

    role_view_en = None
    user_roles_view_en = None
    for view in en_admin._views:
        if isinstance(view, RoleModelView):
            role_view_en = view
        elif isinstance(view, UserWithRolesModelView):
            user_roles_view_en = view

    assert role_view_en is not None
    assert role_view_en.category == "Access Control"

    assert user_roles_view_en is not None
    assert user_roles_view_en.category == "Access Control"

    # Check Russian admin
    ru_admin = admins.get("ru")
    assert ru_admin is not None

    role_view_ru = None
    user_roles_view_ru = None
    for view in ru_admin._views:
        if isinstance(view, RoleModelView):
            role_view_ru = view
        elif isinstance(view, UserWithRolesModelView):
            user_roles_view_ru = view

    assert role_view_ru is not None
    assert role_view_ru.category == "Управление доступом"

    assert user_roles_view_ru is not None
    assert user_roles_view_ru.category == "Управление доступом"


def test_role_views_not_in_menu_for_non_root_user(app_with_roles):
    """Test that role views are not accessible (and thus not shown in menu) for non-root users."""
    from unittest.mock import Mock

    app, admins = app_with_roles

    # Create mock request for non-root user
    request = Mock(spec=Request)
    request.app.state.admin_username = "admin"
    request.session = {"user": "other_user"}

    # Get admin instance
    admin = list(admins.values())[0]

    # Collect accessible views for non-root user
    accessible_views = []
    for view in admin._views:
        # Check if view has is_accessible method (not all views do)
        if hasattr(view, "is_accessible"):
            if view.is_accessible(request):
                accessible_views.append(view)

    # Verify role views are NOT in accessible views
    for view in accessible_views:
        assert not isinstance(view, RoleModelView), (
            "RoleModelView should not be accessible to non-root user"
        )
        assert not isinstance(view, UserWithRolesModelView), (
            "UserWithRolesModelView should not be accessible to non-root user"
        )

    # Now check for root user - should have access
    request.session = {"user": "admin"}
    accessible_views_root = []
    for view in admin._views:
        if hasattr(view, "is_accessible"):
            if view.is_accessible(request):
                accessible_views_root.append(view)

    # Verify role views ARE in accessible views for root
    role_view_found = False
    user_roles_view_found = False
    for view in accessible_views_root:
        if isinstance(view, RoleModelView):
            role_view_found = True
        if isinstance(view, UserWithRolesModelView):
            user_roles_view_found = True

    assert role_view_found, "RoleModelView should be accessible to root user"
    assert user_roles_view_found, (
        "UserWithRolesModelView should be accessible to root user"
    )
