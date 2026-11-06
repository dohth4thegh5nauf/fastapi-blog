"""Example using environment variables for configuration.

Run this example:
    # Set environment variables
    export FASTAPI_BLOG_INCLUDE_API=true
    export FASTAPI_BLOG_API_USERNAME=myuser
    export FASTAPI_BLOG_API_PASSWORD=mypass123

    # Run the app
    cd tests/examples
    uvicorn with_env_vars:app --reload

Then open:
    Blog:     http://localhost:8000/blog
    Admin UI: http://localhost:8000/admin
    API Docs: http://localhost:8000/docs (REST API included because of env var)

The admin login uses the demo-only provider. REST API credentials are read
from FASTAPI_BLOG_API_USERNAME and FASTAPI_BLOG_API_PASSWORD.
"""

import os
import sys  # noqa: I001
from pathlib import Path

from demo_auth import (
  DEMO_DATABASE_URL,
  create_demo_auth_provider,
  install_demo_auth,
)
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import fastapi_blog


# Clear any cached imports
for mod in list(sys.modules.keys()):
  if mod.startswith('fastapi_blog'):
    del sys.modules[mod]


# Create necessary directories
Path('posts').mkdir(exist_ok=True)
Path('pages').mkdir(exist_ok=True)
Path('static').mkdir(exist_ok=True)

# Create FastAPI app
app = FastAPI(title='My Blog with Env Vars')

# Add blog functionality - reads FASTAPI_BLOG_INCLUDE_API from environment
# If FASTAPI_BLOG_INCLUDE_API=true, REST API will be included at /api/posts
fastapi_blog.add_blog_to_fastapi(
  app,
  prefix='blog',
  strict_frontmatter=False,
  sanitize_html=False,
  admin_username=os.getenv('FASTAPI_BLOG_API_USERNAME', 'api-demo'),
  admin_password=os.getenv('FASTAPI_BLOG_API_PASSWORD', 'ApiDemo123!'),
  # include_api not specified - will use FASTAPI_BLOG_INCLUDE_API env var
)

# Admin UI uses a separate demo provider; API credentials do not log into it.
admins = fastapi_blog.add_admin_to_app(
  app,
  title='Blog Admin',
  database_url=DEMO_DATABASE_URL,
  auth_provider=lambda locale: create_demo_auth_provider(locale),
  secret_key=os.environ.get('SECRET_KEY'),
  locales=['en', 'ru'],
  default_locale='en',
)
install_demo_auth(app)

# Mount static files
app.mount('/static', StaticFiles(directory='static'), name='static')


@app.get('/')
async def root():
  """Homepage with links and environment variable status."""
  import os

  include_api = os.getenv('FASTAPI_BLOG_INCLUDE_API', 'false')

  return {
    'message': 'Welcome to FastAPI Blog with Environment Variables!',
    'environment_variables': {
      'FASTAPI_BLOG_INCLUDE_API': include_api,
      'FASTAPI_BLOG_API_USERNAME': os.getenv(
        'FASTAPI_BLOG_API_USERNAME', 'api-demo'
      ),
      'FASTAPI_BLOG_API_PASSWORD': '***'
      if os.getenv('FASTAPI_BLOG_API_PASSWORD')
      else 'unset',
    },
    'links': {
      'blog': 'http://localhost:8000/blog',
      'admin': 'http://localhost:8000/admin',
      'api_docs': 'http://localhost:8000/docs',
    },
    'info': {
      'rest_api': 'Enabled'
      if include_api.lower() in ('true', '1', 'yes')
      else 'Disabled',
      'admin_demo_username': 'admin',
    },
  }
