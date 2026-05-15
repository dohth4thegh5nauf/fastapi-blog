"""Role management views for admin panel."""

from starlette.requests import Request
from starlette_admin import action
from starlette_admin.contrib.sqla import ModelView

from .i18n import Translator


class RoleModelView(ModelView):
    """Admin view for Role management.

    Provides CRUD interface for managing roles.
    Only accessible by root admin user.
    """

    # Basic configuration
    identity = "role"
    name = "Role"
    label = "Roles"
    icon = "fa fa-shield"

    # Custom templates with theme and language switchers
    list_template = "list.html"
    detail_template = "detail.html"
    create_template = "create.html"
    edit_template = "edit.html"

    def __init__(
        self, model, locale: str = "en", admin_username: str = "admin", *args, **kwargs
    ):
        """Initialize with translations and admin username."""
        super().__init__(model, *args, **kwargs)
        self.locale = locale
        self.admin_username = admin_username  # Store for access checks
        self.translator = Translator(locale)
        self.label = self.translator.role.role_label

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

    # Access control - only for root admin user
    def is_accessible(self, request: Request) -> bool:
        """Check if role management is accessible.

        Only the root admin user (matching admin_username) can access.
        """
        current_user = request.session.get("user")
        # Use instance attribute instead of app.state to avoid app identity issues
        return current_user == self.admin_username

    def is_action_accessible(self, request: Request, name: str) -> bool:
        """Check if action is accessible."""
        return self.is_accessible(request)

    def can_view_details(self, request: Request) -> bool:
        """Check if user can view role details."""
        return self.is_accessible(request)

    def can_create(self, request: Request) -> bool:
        """Check if user can create roles."""
        return self.is_accessible(request)

    def can_edit(self, request: Request) -> bool:
        """Check if user can edit roles."""
        return self.is_accessible(request)

    def can_delete(self, request: Request) -> bool:
        """Check if user can delete roles."""
        return self.is_accessible(request)

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
    Only accessible by root admin user.
    """

    # Basic configuration
    identity = "user_with_roles"
    name = "User"
    label = "Users with Roles"
    icon = "fa fa-users"

    # Custom templates with theme and language switchers
    list_template = "list.html"
    detail_template = "detail.html"
    create_template = "create.html"
    edit_template = "edit.html"

    def __init__(
        self, model, locale: str = "en", admin_username: str = "admin", *args, **kwargs
    ):
        """Initialize with translations and admin username."""
        super().__init__(model, *args, **kwargs)
        self.locale = locale
        self.admin_username = admin_username  # Store for access checks
        self.translator = Translator(locale)
        self.label = self.translator.role.user_roles_label

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

    # Access control - only for root admin user
    def is_accessible(self, request: Request) -> bool:
        """Check if user role management is accessible.

        Only the root admin user (matching admin_username) can access.
        """
        current_user = request.session.get("user")
        # Use instance attribute instead of app.state to avoid app identity issues
        return current_user == self.admin_username

    def is_action_accessible(self, request: Request, name: str) -> bool:
        """Check if action is accessible."""
        return self.is_accessible(request)

    def can_view_details(self, request: Request) -> bool:
        """Check if user can view user role details."""
        return self.is_accessible(request)

    def can_create(self, request: Request) -> bool:
        """Check if user can create users with roles."""
        return self.is_accessible(request)

    def can_edit(self, request: Request) -> bool:
        """Check if user can edit users with roles."""
        return self.is_accessible(request)

    def can_delete(self, request: Request) -> bool:
        """Check if user can delete users with roles."""
        return self.is_accessible(request)
