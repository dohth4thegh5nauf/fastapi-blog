"""Role management views for admin panel."""

import copy
import inspect

from starlette.requests import Request
from starlette_admin import action
from starlette_admin.contrib.sqla import ModelView

from ..i18n import Translator
from ..permissions import (
  KNOWN_PERMISSIONS,
  default_authorize,
  normalize_role_permissions,
)
from .fields import RolePermissionsJSONField
from .passwords import get_password_hasher


class _RoleProtectedView(ModelView):
  """Admin-only view using the shared authorization callback."""

  resource = 'role'

  def _allowed(self, request: Request, action_name: str = 'read') -> bool:
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
    authorize=None,
    *args,
    translations_dir: str | None = None,
    **kwargs,
  ):
    """Initialize with translations and admin username."""
    self.fields = copy.deepcopy(type(self).fields)
    super().__init__(model, *args, **kwargs)
    self.locale = locale
    self.authorize = authorize
    self.translator = Translator(locale, translations_dir)
    self.menu_label = self.translator.role.role_label
    permissions_field = next(
      (field for field in self.fields if field.name == 'permissions'), None
    )
    if permissions_field is not None:
      permissions_field.label = self.translator.role.permissions_label
      permissions_field.help_text = self.translator.role.permissions_hint

  # Fields to display (using Any to avoid mypy errors with starlette-admin)
  fields: list = [
    'id',
    'name',
    'description',
    RolePermissionsJSONField(
      'permissions',
      label='Permissions',
      default={},
      help_text=(
        'Choose allowed actions by resource. Unknown resources and actions '
        'are rejected.'
      ),
      exclude_from_list=True,
      validation_schema={
        'type': 'object',
        'properties': {
          resource: {
            'type': 'array',
            'uniqueItems': True,
            'items': {'type': 'string', 'enum': list(actions)},
          }
          for resource, actions in KNOWN_PERMISSIONS.items()
        },
        'additionalProperties': False,
      },
    ),
    'is_active',
    'created_at',
    'updated_at',
  ]

  # Fields shown in list view
  fields_default_sort = [('created_at', True)]  # Sort by created_at desc

  # Search configuration
  searchable_fields = ['name', 'description']

  # Export configuration
  export_fields = ['id', 'name', 'description', 'permissions', 'is_active']

  # Access is checked by _RoleProtectedView through the shared policy.

  async def before_create(self, request: Request, data: dict, obj) -> None:
    """Validate the grant map before creating a role."""
    data['permissions'] = normalize_role_permissions(
      data.get('permissions', {})
    )
    await super().before_create(request, data, obj)

  async def before_edit(self, request: Request, data: dict, obj) -> None:
    """Validate permission changes before updating a role."""
    if 'permissions' in data:
      data['permissions'] = normalize_role_permissions(data['permissions'])
    await super().before_edit(request, data, obj)

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
    authorize=None,
    *args,
    translations_dir: str | None = None,
    **kwargs,
  ):
    """Initialize with translations and admin username."""
    super().__init__(model, *args, **kwargs)
    self.locale = locale
    self.authorize = authorize
    self.translator = Translator(locale, translations_dir)
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

  # Keep the password hash available on create, but hide it from detail/edit.
  exclude_fields_from_create = ['created_at', 'updated_at']
  exclude_fields_from_detail = ['hashed_password']
  exclude_fields_from_edit = [
    'hashed_password',
    'created_at',
    'updated_at',
  ]

  # Search configuration
  searchable_fields = ['email']

  # Export configuration
  export_fields = ['id', 'email', 'is_active']

  # Access is checked by _RoleProtectedView through the shared policy.

  async def before_create(self, request: Request, data: dict, obj) -> None:
    """Hash and validate a newly entered password before persistence."""
    from .views import validate_and_prepare_password

    password = data.get('hashed_password')
    if not password:
      raise ValueError('A password is required when creating a user.')
    password = validate_and_prepare_password(password)
    data['hashed_password'] = get_password_hasher().hash(password)
    await super().before_create(request, data, obj)

  async def before_edit(self, request: Request, data: dict, obj) -> None:
    """Hash a changed password while preserving the existing hash if blank."""
    password = data.get('hashed_password')
    if not password:
      data.pop('hashed_password', None)
    elif password != obj.hashed_password:
      from .views import validate_and_prepare_password

      password = validate_and_prepare_password(password)
      data['hashed_password'] = get_password_hasher().hash(password)
    await super().before_edit(request, data, obj)
