"""Quick start example - minimal setup to get started.

Run this example:
    cd tests/examples
    uvicorn quickstart:app --reload

Then open:
    Blog:     http://localhost:8000/blog
    Admin UI: http://localhost:8000/admin (web interface)
    API Docs: http://localhost:8000/docs (REST API docs)

Demo-only login credentials:
    Username: admin
    Password: Admin123!

Note: Admin panel is a web UI (not REST API), so it won't appear in /docs.
      If you need REST API for posts, see api_optional.py example.
"""

# Note: Module cache clearing removed to ensure app.state persists
# import sys  # noqa: I001
# for mod in list(sys.modules.keys()):
#     if mod.startswith("fastapi_blog"):
#         del sys.modules[mod]

from pathlib import Path  # noqa: E402

from demo_auth import (
  DEMO_DATABASE_URL,
  create_demo_auth_provider,
  install_demo_auth,
)  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

import fastapi_blog  # noqa: E402
from fastapi_blog.models import FieldSpec, FrontmatterSchema  # noqa: E402


# Create necessary directories
Path('posts').mkdir(exist_ok=True)
Path('pages').mkdir(exist_ok=True)
Path('static').mkdir(exist_ok=True)

# Create FastAPI app
app = FastAPI(title='My Blog')

# Keep the imported example posts valid in both the blog and admin panel.
frontmatter_schema = FrontmatterSchema(
  fields=(
    FieldSpec('title', required=True, role='title'),
    FieldSpec('date', role='date'),
    FieldSpec('published', type='bool', default=False, role='published'),
    FieldSpec('tags', type='list[str]', role='tags'),
    FieldSpec('description', role='description'),
    FieldSpec('source_slug', alias='slug', read_only=True),
    FieldSpec('time_to_read', type='int'),
    FieldSpec('type'),
    FieldSpec('image', type='image'),
  ),
)

# Add blog functionality with i18n
fastapi_blog.add_blog_to_fastapi(
  app,
  prefix='blog',
  strict_frontmatter=False,
  frontmatter_schema=frontmatter_schema,
  sanitize_html=False,
  locales=['en', 'ru'],  # Enable language switcher in blog
  default_locale='en',
)

# Add admin panel (database auto-initialized on startup)
# New API: creates /admin/en and /admin/ru, /admin redirects to /admin/en
admins = fastapi_blog.add_admin_to_app(
  app,
  title='Blog Admin',
  database_url=DEMO_DATABASE_URL,
  secret_key='demo-only-session-secret-0123456789abcdef0123456789',
  auth_provider=lambda locale: create_demo_auth_provider(locale),
  frontmatter_schema=frontmatter_schema,
  locales=['en', 'ru'],
  default_locale='en',  # /admin → /admin/en
  enable_role_management=True,  # Enable role management (visible only to root admin)
)
install_demo_auth(app)

# Mount static files
app.mount('/static', StaticFiles(directory='static'), name='static')


@app.get('/')
async def root():
  """Homepage with links and instructions."""
  return {
    'message': 'Welcome to FastAPI Blog!',
    'links': {
      'blog': 'http://localhost:8000/blog',
      'admin': 'http://localhost:8000/admin',
      'api_docs': 'http://localhost:8000/docs',
    },
    'demo_admin_login': {
      'username': 'admin',
      'password': 'Admin123!',
      'note': 'Demo credentials only; configure your own provider in production.',
    },
    'first_steps': [
      '1. Go to /admin and login',
      '2. Create your first blog post',
      '3. View it at /blog',
    ],
  }
