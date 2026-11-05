"""Example: Full-featured admin panel.

Demonstrates all advanced features:
- Internationalization (i18n) with EN/RU
- Custom fields (MarkdownField, TagsField, SlugField)
- RBAC authentication
- Markdown post management
"""

from demo_auth import create_demo_auth_provider
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import fastapi_blog


app = FastAPI(title='Full-Featured Blog')

# Add blog with optional REST API
fastapi_blog.add_blog_to_fastapi(
  app,
  prefix='blog',
  include_api=True,  # Enable REST API
  api_require_auth=True,
  admin_username='api-demo',
  admin_password='ApiDemo123!',
  strict_frontmatter=False,
  sanitize_html=False,
)

# Add full-featured admin panel
admin = fastapi_blog.add_admin_to_app(
  app,
  title='Blog Admin Panel',
  secret_key='demo-only-session-secret-0123456789abcdef0123456789',
  auth_provider=lambda locale: create_demo_auth_provider(locale),
  locales=['en', 'ru'],
  default_locale='en',
)

app.mount('/static', StaticFiles(directory='static'), name='static')


@app.get('/')
async def index() -> dict:
  return {
    'message': 'Full-featured blog with advanced admin panel',
    'features': [
      'Internationalization (EN/RU)',
      'Custom fields for markdown editing',
      'REST API for programmatic access',
      'Markdown file-based storage',
      'User management',
    ],
    'endpoints': {
      'blog': 'http://localhost:8000/blog',
      'admin': 'http://localhost:8000/admin',
      'api_docs': 'http://localhost:8000/docs',
    },
    'demo_credentials': {'username': 'admin', 'password': 'Admin123!'},
    'notes': [
      'Use /admin for English and /ru/admin for Russian',
      'REST API uses separate demo Basic auth credentials: api-demo / ApiDemo123!',
      'Markdown posts stored in ./posts directory',
    ],
  }
