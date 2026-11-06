"""Example with role and user CRUD views.

This example demonstrates how to use the Role and UserWithRoles models
for more granular access control.

Run this example:
    cd tests/examples
    uvicorn with_roles:app --reload

Then open:
    Admin UI: http://localhost:8000/admin

Note: This example shows how to set up role management views.
      Login uses the separate demo provider and does not read these records.
      See admin_with_roles.py for a standalone provider with explicit demo roles.
"""

import sys  # noqa: I001
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import fastapi_blog
from fastapi_blog.admin import RoleModelView, UserWithRolesModelView
from fastapi_blog.admin.models import Role, UserWithRoles
from demo_auth import (
  DEMO_DATABASE_URL,
  create_demo_auth_provider,
  install_demo_auth,
)

# Clear any cached imports
for mod in list(sys.modules.keys()):
  if mod.startswith('fastapi_blog'):
    del sys.modules[mod]


# Create necessary directories
Path('posts').mkdir(exist_ok=True)
Path('pages').mkdir(exist_ok=True)
Path('static').mkdir(exist_ok=True)

# Create FastAPI app
app = FastAPI(title='Blog with Roles')

# Add blog functionality
fastapi_blog.add_blog_to_fastapi(
  app,
  prefix='blog',
  strict_frontmatter=False,
  sanitize_html=False,
)


def configure_admin(locale, admin):
  """Add the CRUD role views before each localized panel is mounted."""
  admin.add_view(RoleModelView(Role, locale=locale, icon='fa fa-shield'))
  admin.add_view(
    UserWithRolesModelView(UserWithRoles, locale=locale, icon='fa fa-users-cog')
  )


# Add admin panel
admins = fastapi_blog.add_admin_to_app(
  app,
  title='Blog Admin with Roles',
  database_url=DEMO_DATABASE_URL,
  secret_key='demo-only-session-secret-0123456789abcdef0123456789',
  auth_provider=lambda locale: create_demo_auth_provider(locale),
  locales=['en', 'ru'],
  default_locale='en',
  configure_admin=configure_admin,
)
install_demo_auth(app)

# Mount static files
app.mount('/static', StaticFiles(directory='static'), name='static')


@app.get('/')
async def root():
  """Homepage with links."""
  return {
    'message': 'Welcome to FastAPI Blog with Role Management!',
    'links': {
      'blog': 'http://localhost:8000/blog',
      'admin': 'http://localhost:8000/admin',
    },
    'features': [
      'Role-based access control',
      'User management with roles',
      'Granular permissions',
    ],
    'demo_admin_login': {
      'username': 'admin',
      'password': 'Admin123!',
    },
  }
