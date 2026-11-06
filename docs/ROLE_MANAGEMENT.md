# Role Management

FastAPI Blog includes a built-in role-based access policy shared by the REST API and admin panel. The same `authorize(request, resource, action)` callback can be supplied to replace the policy.

Authentication is separate from this policy. The recommended integration
passes a host-owned Starlette Admin `AuthProvider`; FastAPI Blog's user and role
views do not change accounts in that provider unless the host provider reads
those records. The local demo provider explicitly does so. See
[Admin Authentication Providers](ADMIN_AUTHENTICATION.md).

## Overview

The role management system provides:
- **Role Model:** Define custom roles, descriptions and resource/action grants
- **UserWithRoles Model:** Extended user model with role assignments
- **Many-to-Many Relationship:** Users can have multiple roles
- **Admin Views:** Manage roles and users through admin panel
- **Flexible Permissions:** Control access at the view and action level
- **Shared Authorization:** REST API routes and admin views consult the same resource/action policy

## Access URLs

When role management is enabled, the following URLs require the `admin` role by default:

- **English Admin:**
  - Role management section: `/admin/en` (in sidebar under "Access Control")
  - Roles list: `/admin/en/role/list`
  - User roles list: `/admin/en/user_with_roles/list`

- **Russian Admin:**
  - Role management section: `/admin/ru` (in sidebar under "Управление доступом")
  - Roles list: `/admin/ru/role/list`
  - User roles list: `/admin/ru/user_with_roles/list`

**Note:** Non-root users will not see the "Access Control" / "Управление доступом" section in the sidebar menu. Direct URL access is protected and will return a 403 Forbidden error.

## Models

### Role Model

Defines a role that can be assigned to users.

```python
from fastapi_blog.admin import Role

# Fields:
- id: int (primary key)
- name: str (unique, e.g., 'admin', 'editor', 'viewer')
- description: str | None
- permissions: dict[str, list[str]] (resource names mapped to allowed actions)
- is_active: bool (default: True)
- created_at: datetime
- updated_at: datetime | None
- users: list[UserWithRoles] (relationship)
```

### UserWithRoles Model

Extended user model with role support.

```python
from fastapi_blog.admin import UserWithRoles

# Fields:
- id: int (primary key)
- email: str (unique)
- hashed_password: str (bcrypt)
- is_active: bool (default: True)
- created_at: datetime
- updated_at: datetime | None
- roles: list[Role] (relationship)

# Methods:
- has_role(role_name: str) -> bool
- has_any_role(*role_names: str) -> bool
```

## Setup

### Basic Setup

```python
import os
from fastapi import FastAPI
import fastapi_blog
from fastapi_blog.admin import RoleModelView, UserWithRolesModelView
from myapp.auth import create_auth_provider

app = FastAPI()

# Add blog
fastapi_blog.add_blog_to_fastapi(app, prefix='blog')

# Add admin panel
admins = fastapi_blog.add_admin_to_app(
  app,
  auth_provider=lambda locale: create_auth_provider(locale),
  secret_key=os.environ['SECRET_KEY'],
)

# Add role management views to admin
for locale, admin in admins.items():
  from fastapi_blog.admin.models import Role, UserWithRoles
  
  # Add Role view
  role_view = RoleModelView(Role, icon='fa fa-shield')
  admin.add_view(role_view)
  
  # Add UserWithRoles view
  user_view = UserWithRolesModelView(UserWithRoles, icon='fa fa-users-cog')
  admin.add_view(user_view)
```

### Configure Role Permissions

The Role admin view includes a JSON permissions editor. Each resource maps to
the allowed actions; for example, a read-only editorial role can be configured
as:

```json
{
  "posts": ["read"],
  "users": [],
  "settings": []
}
```

The editor validates resource and action names in the browser and on the
server. Unknown values are rejected. Users assigned multiple active roles
receive the union of their grants. An explicit empty grant map denies all
actions and does not fall back to built-in role defaults.

The local demo provider loads grants from role records. Other host providers
must put a validated `permissions` mapping on `request.state.blog_user`, or
provide their own `authorize` callback, for edited grants to affect access.

### Initialize Default Roles

```python
from fastapi_blog.admin.models.role import create_default_roles
from fastapi_blog.admin.database import create_engine_and_session
from sqlalchemy.ext.asyncio import AsyncSession

# During app startup
engine, session_factory = create_engine_and_session()

async with session_factory() as session:
  await create_default_roles(session)
```

The host-supplied provider should populate `request.state.blog_user` with a
role or explicit permission mapping:

- **admin:** Full access to posts, users, settings, and role management.
- **editor:** Can create, read, update, and publish posts; can read users and
  settings; cannot delete posts or manage accounts/roles.
- **viewer:** Can read posts only.

These are the initial grants for the built-in role names. The default policy
continues to use them for principals that provide only a role name; principals
with an explicit `permissions` mapping use that mapping instead.

Unknown or unrecognized roles are denied. Principals without a recognized
role or explicit permission mapping are denied by the default policy. The REST
API has its own authentication configuration and does not inherit the admin
provider's identity automatically.

## Usage

### Check User Roles

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi_blog.admin.database import get_db
from fastapi_blog.admin.models import UserWithRoles


@app.get('/admin/dashboard')
async def admin_dashboard(db: AsyncSession = Depends(get_db)):
  # Get current user (simplified example)
  user = await get_current_user(db)

  # Check if user has admin role
  if user.has_role('admin'):
    return {'message': 'Welcome, admin!'}

  # Check if user has any of the specified roles
  if user.has_any_role('admin', 'editor'):
    return {'message': 'Welcome, editor!'}

  return {'error': 'Access denied'}
```

### Custom authorization callback

Pass the same callback to `setup_fastapi_blog()`, `add_blog_to_fastapi()` or
`add_admin_to_app()`. It receives the request, resource name and action, and
must return `bool`. Unknown combinations should be denied.

```python
from fastapi import Request


def authorize(request: Request, resource: str, action: str) -> bool:
  principal = getattr(request.state, 'blog_user', None) or {}
  role = principal.get('role')
  if role == 'owner':
    return True
  return (
    role == 'writer'
    and resource == 'posts'
    and action
    in {
      'read',
      'create',
      'update',
      'publish',
    }
  )
```

Starlette Admin's synchronous ModelView permission hooks require a synchronous
callback. Async callbacks are supported by REST and Markdown custom routes;
ModelView hooks fail closed for an awaitable result.

## Admin Views

### RoleModelView

Provides CRUD interface for managing roles.

**Features:**
- Create/edit/delete roles
- Search by name and description
- Activate/deactivate roles (custom actions)
- Export role data

**Permissions:**
- Only admins can create, edit, or delete roles (by default)

**Customization:**
```python
from fastapi_blog.admin import RoleModelView


class CustomRoleView(RoleModelView):
  # Customize fields
  fields = ['id', 'name', 'description', 'is_active']

  # Customize labels
  label = 'Custom Roles'

  # Override permissions
  def can_create(self, request: Request) -> bool:
    return True  # Allow all authenticated users
```

### UserWithRolesModelView

Provides CRUD interface for managing users with roles.

**Features:**
- Create/edit/delete users
- Assign multiple roles to users
- Search by email
- Export user data

**Permissions:**
- Only admins can create, edit, or delete users (by default)

**Customization:**
```python
from fastapi_blog.admin import UserWithRolesModelView


class CustomUserView(UserWithRolesModelView):
  # Exclude sensitive fields
  exclude_fields_from_list = ['hashed_password']
  exclude_fields_from_detail = ['hashed_password']

  # Custom permissions
  def can_edit(self, request: Request) -> bool:
    # Users can edit their own profile
    user_email = request.session.get('user')
    return user_email is not None
```

## Examples

### Complete Example with Roles

See `tests/examples/with_roles.py` for a full working example.

```python
import os
from fastapi import FastAPI
import fastapi_blog
from fastapi_blog.admin import RoleModelView, UserWithRolesModelView
from myapp.auth import create_auth_provider

app = FastAPI()

# Add blog
fastapi_blog.add_blog_to_fastapi(app, prefix='blog')

# Add admin
admins = fastapi_blog.add_admin_to_app(
  app,
  title='Blog Admin with Roles',
  auth_provider=lambda locale: create_auth_provider(locale),
  secret_key=os.environ['SECRET_KEY'],
)

# Add role management
for locale, admin in admins.items():
  from fastapi_blog.admin.models import Role, UserWithRoles
  
  role_view = RoleModelView(Role, icon='fa fa-shield')
  admin.add_view(role_view)
  
  user_view = UserWithRolesModelView(UserWithRoles, icon='fa fa-users-cog')
  admin.add_view(user_view)
```

### Creating Users with Roles Programmatically

```python
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi_blog.admin.models import Role, UserWithRoles
from fastapi_blog.admin.models.role import create_default_roles
from fastapi_blog.admin.passwords import get_password_hasher

hasher = get_password_hasher()


async def create_user_with_roles(
  session: AsyncSession,
  email: str,
  password: str,
  role_names: list[str],
):
  """Create a user and assign roles."""
  from sqlalchemy import select

  # Create user
  user = UserWithRoles(
    email=email,
    hashed_password=hasher.hash(password),
    is_active=True,
  )

  # Get roles
  result = await session.execute(select(Role).where(Role.name.in_(role_names)))
  roles = result.scalars().all()

  # Assign roles
  user.roles = roles

  session.add(user)
  await session.commit()

  return user


# Usage
async with session_factory() as session:
  await create_default_roles(session)

  # Create admin user
  admin_user = await create_user_with_roles(
    session,
    email='admin@example.com',
    password='SecurePass123!',
    role_names=['admin'],
  )

  # Create editor user
  editor_user = await create_user_with_roles(
    session,
    email='editor@example.com',
    password='EditorPass123!',
    role_names=['editor'],
  )
```

## Database Schema

### Tables

**roles:**
- id (PK)
- name (unique)
- description
- is_active
- created_at
- updated_at

**users_with_roles:**
- id (PK)
- email (unique)
- hashed_password
- is_active
- created_at
- updated_at

**user_roles (association table):**
- user_id (FK → users_with_roles.id)
- role_id (FK → roles.id)

### Relationships

```
UserWithRoles ←→ user_roles ←→ Role
  (many)                        (many)
```

One user can have many roles.  
One role can be assigned to many users.

## Migration from Simple User Model

If you're using the basic `User` model and want to migrate to `UserWithRoles`:

### 1. Create Migration

```bash
alembic revision --autogenerate -m "Add role management"
alembic upgrade head
```

### 2. Migrate Data

```python
from sqlalchemy import select
from fastapi_blog.admin.models import User
from fastapi_blog.admin.models import Role, UserWithRoles
from fastapi_blog.admin.models.role import create_default_roles


async def migrate_users_to_roles(session: AsyncSession):
  """Migrate existing users to UserWithRoles."""

  # Create default roles
  await create_default_roles(session)

  # Get admin role
  result = await session.execute(select(Role).where(Role.name == 'admin'))
  admin_role = result.scalar_one()

  # Get all existing users
  result = await session.execute(select(User))
  users = result.scalars().all()

  # Migrate each user
  for user in users:
    new_user = UserWithRoles(
      email=user.email,
      hashed_password=user.hashed_password,
      is_active=user.is_active,
      created_at=user.created_at,
      updated_at=user.updated_at,
    )

    # Assign admin role to admin users
    if user.is_admin:
      new_user.roles = [admin_role]

    session.add(new_user)

  await session.commit()
```

### 3. Update Auth Provider

Update your authentication provider to work with the new model.

## Troubleshooting

### Roles Not Appearing

**Problem:** Role views not showing in admin panel.

**Solution:** Ensure you add views to all locale admins:
```python
for locale, admin in admins.items():
  admin.add_view(RoleModelView(Role))
```

### Foreign Key Errors

**Problem:** Foreign key constraint errors when creating user_roles.

**Solution:** Ensure roles exist before assigning them to users:
```python
await create_default_roles(session)  # Create roles first
```

### Permission Denied

**Problem:** User can't create/edit/delete despite having role.

**Solution:** Override permission methods in your view:
```python
def can_create(self, request: Request) -> bool:
  user = get_current_user(request)
  return user.has_role('admin')
```

## Related Documentation

- [DATABASE.md](DATABASE.md) - Database architecture
- [QUICKSTART.md](../QUICKSTART.md) - Quick start guide
- [Examples](../tests/examples/) - Working examples

---

**Last Updated:** 2026-05-15  
**Version:** 0.8.1+
