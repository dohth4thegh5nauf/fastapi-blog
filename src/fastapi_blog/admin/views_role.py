"""Role management views for admin panel."""

from starlette.requests import Request
from starlette_admin import action
from starlette_admin.contrib.sqla import ModelView


class RoleModelView(ModelView):
    """Admin view for Role management.

    Provides CRUD interface for managing roles.
    """

    # Basic configuration
    identity = "role"
    name = "Role"
    label = "Roles"
    icon = "fa fa-shield"

    # Fields to display (using Any to avoid mypy errors with starlette-admin)
    fields: list = [
        "id",
        "name",
        "description",
        "is_active",
        "created_at",
        "updated_at",
    ]

    # Fields shown in list view
    fields_default_sort = [("created_at", True)]  # Sort by created_at desc

    # Search configuration
    searchable_fields = ["name", "description"]

    # Export configuration
    export_fields = ["id", "name", "description", "is_active"]

    # Permissions (can be overridden)
    def can_create(self, request: Request) -> bool:
        """Check if user can create roles."""
        # Only admins can create roles
        user = request.session.get("user", {})
        return user.get("is_admin", False)

    def can_edit(self, request: Request) -> bool:
        """Check if user can edit roles."""
        # Only admins can edit roles
        user = request.session.get("user", {})
        return user.get("is_admin", False)

    def can_delete(self, request: Request) -> bool:
        """Check if user can delete roles."""
        # Only admins can delete roles
        user = request.session.get("user", {})
        return user.get("is_admin", False)

    @action(
        name="activate",
        text="Activate",
        confirmation="Are you sure you want to activate selected roles?",
        submit_btn_text="Yes, activate",
        submit_btn_class="btn-success",
    )
    async def activate_action(self, request: Request, pks: list) -> str:
        """Activate selected roles."""
        # This is an example action - implement as needed
        return f"Activated {len(pks)} role(s)"

    @action(
        name="deactivate",
        text="Deactivate",
        confirmation="Are you sure you want to deactivate selected roles?",
        submit_btn_text="Yes, deactivate",
        submit_btn_class="btn-warning",
    )
    async def deactivate_action(self, request: Request, pks: list) -> str:
        """Deactivate selected roles."""
        # This is an example action - implement as needed
        return f"Deactivated {len(pks)} role(s)"


class UserWithRolesModelView(ModelView):
    """Admin view for User management with roles.

    Provides CRUD interface for managing users with role assignments.
    """

    # Basic configuration
    identity = "user_with_roles"
    name = "User"
    label = "Users with Roles"
    icon = "fa fa-users"

    # Fields to display (using Any to avoid mypy errors with starlette-admin)
    fields: list = [
        "id",
        "email",
        "hashed_password",
        "is_active",
        "roles",  # Many-to-many relationship
        "created_at",
        "updated_at",
    ]

    # Fields shown in list view
    fields_default_sort = [("created_at", True)]  # Sort by created_at desc

    # Exclude from list view
    exclude_fields_from_list = ["hashed_password"]

    # Exclude from create/edit forms
    exclude_fields_from_create = ["created_at", "updated_at"]
    exclude_fields_from_edit = ["created_at", "updated_at"]

    # Search configuration
    searchable_fields = ["email"]

    # Export configuration
    export_fields = ["id", "email", "is_active"]

    # Permissions (can be overridden)
    def can_create(self, request: Request) -> bool:
        """Check if user can create users."""
        # Only admins can create users
        user = request.session.get("user", {})
        return user.get("is_admin", False)

    def can_edit(self, request: Request) -> bool:
        """Check if user can edit users."""
        # Only admins can edit users
        user = request.session.get("user", {})
        return user.get("is_admin", False)

    def can_delete(self, request: Request) -> bool:
        """Check if user can delete users."""
        # Only admins can delete users
        user = request.session.get("user", {})
        return user.get("is_admin", False)
