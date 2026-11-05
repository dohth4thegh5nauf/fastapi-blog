"""Example: Admin panel with role-based access control.

Demonstrates advanced authentication with:
- Multiple users with different roles
- Role-based permissions
- User avatars
- Custom photo URLs

Inspired by starlette-admin-demo.

Run:
    cd tests/examples
    uvicorn admin_with_roles:app --reload

Test users:
    admin / password     - Full access (admin role)
    editor / password    - Can edit but not delete (editor role)
    viewer / password    - Read-only access (viewer role)
"""

import secrets
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette_admin.auth import AdminUser, AuthProvider
from starlette_admin.contrib.sqla import Admin, ModelView
from starlette_admin.exceptions import FormValidationError, LoginFailed

import fastapi_blog
from fastapi_blog.admin.database import create_engine_and_session
from fastapi_blog.admin.models import Post, User


# Create directories
Path('posts').mkdir(exist_ok=True)
Path('pages').mkdir(exist_ok=True)
Path('static').mkdir(exist_ok=True)

# Mock users database
USERS = {
  'admin': {
    'name': 'Admin User',
    'password': 'password',
    'roles': ['admin'],
    'avatar': 'https://ui-avatars.com/api/?name=Admin+User&background=0D8ABC&color=fff',
  },
  'editor': {
    'name': 'Editor User',
    'password': 'password',
    'roles': ['editor'],
    'avatar': 'https://ui-avatars.com/api/?name=Editor+User&background=FF6B6B&color=fff',
  },
  'viewer': {
    'name': 'Viewer User',
    'password': 'password',
    'roles': ['viewer'],
    'avatar': 'https://ui-avatars.com/api/?name=Viewer+User&background=4ECDC4&color=fff',
  },
}


class RoleBasedAuthProvider(AuthProvider):
  """Authentication provider with role-based access control."""

  async def login(
    self,
    username: str,
    password: str,
    remember_me: bool,
    request: Request,
  ) -> None:
    """Authenticate user and save to session."""
    # Form validation
    if len(username) < 3:
      raise FormValidationError(
        {'username': 'Username must be at least 3 characters'}
      )

    # Check credentials
    user = USERS.get(username)
    if user and secrets.compare_digest(user['password'], password):
      # Save username in session
      request.session.update({'username': username})
      return None

    raise LoginFailed('Invalid username or password')

  async def authenticate(self, request: Request) -> AdminUser | None:
    """Resolve the demo identity and expose it to view permissions."""
    username = request.session.get('username')
    if username in USERS:
      request.state.user = USERS[username]
      request.state.blog_user = {
        'username': username,
        'role': username,
        'is_admin': 'admin' in USERS[username]['roles'],
      }
      user = USERS[username]
      return AdminUser(username=user['name'], photo_url=user['avatar'])
    return None

  async def logout(self, request: Request) -> None:
    """Clear session on logout."""
    request.session.clear()
    return None


class UserView(ModelView):
  """User management - admin only."""

  def is_accessible(self, request: Request) -> bool:
    """Only admin can access user management."""
    return 'admin' in request.state.user.get('roles', [])

  def can_delete(self, request: Request) -> bool:
    """Only admin can delete users."""
    return 'admin' in request.state.user.get('roles', [])


class PostView(ModelView):
  """Post management - admin and editor."""

  def is_accessible(self, request: Request) -> bool:
    """Admin and editor can access posts."""
    roles = request.state.user.get('roles', [])
    return 'admin' in roles or 'editor' in roles

  def can_delete(self, request: Request) -> bool:
    """Only admin can delete posts."""
    return 'admin' in request.state.user.get('roles', [])

  def can_edit(self, request: Request) -> bool:
    """Admin and editor can edit posts."""
    roles = request.state.user.get('roles', [])
    return 'admin' in roles or 'editor' in roles

  def can_create(self, request: Request) -> bool:
    """Admin and editor can create posts."""
    roles = request.state.user.get('roles', [])
    return 'admin' in roles or 'editor' in roles


app = FastAPI(title='Blog with RBAC')

# Add blog
fastapi_blog.add_blog_to_fastapi(
  app,
  prefix='blog',
  strict_frontmatter=False,
  sanitize_html=False,
)

# Add session middleware
app.add_middleware(
  SessionMiddleware,
  same_site='lax',
  secret_key='example-only-session-secret-value-0123456789abcdef0123456789',
)

# Create database engine
engine, _ = create_engine_and_session()

# Create admin with RBAC
admin = Admin(
  engine,
  title='Blog Admin (RBAC)',
  base_url='/admin',
  auth_provider=RoleBasedAuthProvider(),
  secret_key='example-only-session-secret-value-0123456789abcdef0123456789',
)

# Add views with role-based permissions
admin.add_view(UserView(User, icon='fa fa-users'))
post_view = PostView(Post, icon='fa fa-blog')
post_view.menu_label = 'Blog Posts'
admin.add_view(post_view)

admin.mount_to(app)

app.mount('/static', StaticFiles(directory='static'), name='static')


@app.get('/')
async def root():
  return {
    'message': 'Blog with Role-Based Access Control',
    'admin_panel': 'http://localhost:8000/admin',
    'test_users': [
      {
        'username': 'admin',
        'password': 'password',
        'roles': ['admin'],
        'permissions': 'Full access - can create, edit, delete everything',
      },
      {
        'username': 'editor',
        'password': 'password',
        'roles': ['editor'],
        'permissions': 'Can create and edit posts, but cannot delete',
      },
      {
        'username': 'viewer',
        'password': 'password',
        'roles': ['viewer'],
        'permissions': 'Read-only access, cannot access admin panel',
      },
    ],
    'note': 'Try logging in with different users to see role-based permissions',
  }


# Database initialized automatically
