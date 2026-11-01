"""Role management views for admin panel."""

import inspect

from starlette.requests import Request
from starlette_admin import action
from starlette_admin.contrib.sqla import ModelView

from ..i18n import Translator
from ..permissions import default_authorize, user_from_session


class _RoleProtectedView(ModelView):
  """Admin-only view using the shared authorization callback."""

  resource = 'role'

  def _allowed(self, request: Request, action_name: str = 'read') -> bool:
    principal = getattr(request.state, 'blog_user', None)
    if principal is None:
      principal = user_from_session(request)
      request.state.blog_user = principal
    callback = getattr(self, 'authorize', None) or default_authorize
    result = callback(request, self.resource, action_name)
    return bool(result) if not inspect.isawaitable(result) else False

  def is_accessible(self, request: Request) -> bool:
    return self._allowed(request, 'read')

  def can_view_detail(self, request: Request) -> bool:
    return self._allowed(request, 'read')

  def can_create(self, request: Request) -> bool:
    return self._allowed(request, 'create')

  def can_edit(self, request: Request) -> bool:
    return self._allowed(request, 'update')

  def can_delete(self, request: Request) -> bool:
    return self._allowed(request, 'delete')

  def can_export(self, request: Request) -> bool:
    return self._allowed(request, 'read')

  def can_import(self, request: Request) -> bool:
    return self._allowed(request, 'create')

  async def is_action_allowed(self, request: Request, name: str) -> bool:
    # Starlette Admin awaits this hook (unlike the sync `can_*` ones).
    principal = getattr(request.state, 'blog_user', None)
    if principal is None:
      principal = user_from_session(request)
      request.state.blog_user = principal
    callback = getattr(self, 'authorize', None) or default_authorize
    result = callback(request, self.resource, 'update')
    if inspect.isawaitable(result):
      result = await result
    return bool(result)


class RoleModelView(_RoleProtectedView):
  """Admin view for Role management.

  Provides CRUD interface for managing roles.
  Only accessible by root admin user.
  """

  # Basic configuration
  key = 'role'
  display_name = 'Role'
  menu_label = 'Roles'
  icon = 'fa fa-shield'

  # Custom templates with theme and language switchers
  list_template = 'list.html'
  detail_template = 'detail.html'
  create_template = 'create.html'
  edit_template = 'edit.html'

  def __init__(
    self,
    model,
    locale: str = 'en',
    admin_username: str = 'admin',
    authorize=None,
    *args,
    **kwargs,
  ):
    """Initialize with translations and admin username."""
    super().__init__(model, *args, **kwargs)
    self.locale = locale
    self.admin_username = admin_username  # Store for access checks
    self.authorize = authorize
    self.translator = Translator(locale)
    self.menu_label = self.translator.role.role_label

  # Fields to display (using Any to avoid mypy errors with starlette-admin)
  fields: list = [
    'id',
    'name',
    'description',
    'is_active',
    'created_at',
    'updated_at',
  ]

  # Fields shown in list view
  fields_default_sort = [('created_at', True)]  # Sort by created_at desc

  # Search configuration
  searchable_fields = ['name', 'description']

  # Export configuration
  export_fields = ['id', 'name', 'description', 'is_active']

  # Access is checked by _RoleProtectedView through the shared policy.

  @action(
    name='activate',
    text='Activate',
    confirmation='Are you sure you want to activate selected roles?',
    submit_btn_text='Yes, activate',
    submit_btn_class='btn-success',
  )
  async def activate_action(self, request: Request, pks: list) -> str:
    """Activate selected roles."""
    # This is an example action - implement as needed
    return f'Activated {len(pks)} role(s)'

  @action(
    name='deactivate',
    text='Deactivate',
    confirmation='Are you sure you want to deactivate selected roles?',
    submit_btn_text='Yes, deactivate',
    submit_btn_class='btn-warning',
  )
  async def deactivate_action(self, request: Request, pks: list) -> str:
    """Deactivate selected roles."""
    # This is an example action - implement as needed
    return f'Deactivated {len(pks)} role(s)'


class UserWithRolesModelView(_RoleProtectedView):
  resource = 'user_with_roles'
  """Admin view for User management with roles.

  Provides CRUD interface for managing users with role assignments.
  Only accessible by root admin user.
  """

  # Basic configuration
  key = 'user_with_roles'
  display_name = 'User'
  menu_label = 'Users with Roles'
  icon = 'fa fa-users'

  # Custom templates with theme and language switchers
  list_template = 'list.html'
  detail_template = 'detail.html'
  create_template = 'create.html'
  edit_template = 'edit.html'

  def __init__(
    self,
    model,
    locale: str = 'en',
    admin_username: str = 'admin',
    authorize=None,
    *args,
    **kwargs,
  ):
    """Initialize with translations and admin username."""
    super().__init__(model, *args, **kwargs)
    self.locale = locale
    self.admin_username = admin_username  # Store for access checks
    self.authorize = authorize
    self.translator = Translator(locale)
    self.menu_label = self.translator.role.user_roles_label

  # Fields to display (using Any to avoid mypy errors with starlette-admin)
  fields: list = [
    'id',
    'email',
    'hashed_password',
    'is_active',
    'roles',  # Many-to-many relationship
    'created_at',
    'updated_at',
  ]

  # Fields shown in list view
  fields_default_sort = [('created_at', True)]  # Sort by created_at desc

  # Exclude from list view
  exclude_fields_from_list = ['hashed_password']

  # Exclude from create/edit forms
  exclude_fields_from_create = ['created_at', 'updated_at']
  exclude_fields_from_edit = ['created_at', 'updated_at']

  # Search configuration
  searchable_fields = ['email']

  # Export configuration
  export_fields = ['id', 'email', 'is_active']

  # Access is checked by _RoleProtectedView through the shared policy.
