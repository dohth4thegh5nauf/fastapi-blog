"""Example: Full-featured admin panel.

Demonstrates all advanced features:
- Internationalization (i18n) with EN/RU
- Custom fields (MarkdownField, TagsField, SlugField)
- RBAC authentication
- Markdown post management
"""

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
  strict_frontmatter=False,
  sanitize_html=False,
)

# Add full-featured admin panel
admin = fastapi_blog.add_admin_to_app(
  app,
  title='Blog Admin Panel',
  base_url='/admin',
  admin_username='admin',
  admin_password='Admin123!',
  secret_key='change-me-in-production',
  insecure_dev=True,
  # i18n configuration
  i18n_enabled=True,
  i18n_default_locale='en',
  i18n_locales=['en', 'ru'],  # Language switcher
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
    'credentials': {'username': 'admin', 'password': 'Admin123!'},
    'notes': [
      'Switch language in admin panel (top right corner)',
      'REST API requires authentication',
      'Markdown posts stored in ./posts directory',
    ],
  }
