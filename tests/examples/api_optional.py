"""Example: Blog with optional REST API.

This demonstrates the new include_api parameter that makes
REST API optional instead of requiring separate add_editor_to_app().

Run this example:
    cd tests/examples
    uvicorn api_optional:app --reload

Then check /docs:
    - Public blog endpoints (GET /blog/*)
    - REST API endpoints (POST/PUT/DELETE /api/posts/*) ← These appear in /docs!

Compare with quickstart.py:
    - quickstart.py: Only admin UI (no REST API in /docs)
    - api_optional.py: Admin UI + REST API (REST API visible in /docs)

Remember: Admin panel (/admin) is a web UI, not REST API.
"""

from demo_auth import (
  DEMO_DATABASE_URL,
  create_demo_auth_provider,
  install_demo_auth,
)
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

import fastapi_blog


app = FastAPI(title='Blog with Optional API')

# Add session middleware for authentication
app.add_middleware(
  SessionMiddleware,
  secret_key='example-only-session-secret-value-0123456789abcdef0123456789',
  same_site='lax',
)

# Add blog with REST API enabled
fastapi_blog.add_blog_to_fastapi(
  app,
  prefix='blog',
  include_api=True,  # Enable REST API
  api_prefix='/api/posts',
  api_require_auth=True,  # Require authentication for API
  admin_username='api-demo',
  admin_password='ApiDemo123!',
  strict_frontmatter=False,
  sanitize_html=False,
)

# Add admin panel (recommended for management)
fastapi_blog.add_admin_to_app(
  app,
  title='Blog Admin',
  database_url=DEMO_DATABASE_URL,
  secret_key='example-only-session-secret-value-0123456789abcdef0123456789',
  auth_provider=lambda locale: create_demo_auth_provider(locale),
  add_session_middleware=False,  # Already added above
)
install_demo_auth(app)

app.mount('/static', StaticFiles(directory='static'), name='static')


@app.get('/')
async def index() -> dict:
  return {
    'message': 'Blog with optional REST API example',
    'blog': 'http://localhost:8000/blog',
    'admin': 'http://localhost:8000/admin',
    'api_docs': 'http://localhost:8000/docs',
    'note': 'Admin demo login: admin / Admin123!. API demo Basic auth: api-demo / ApiDemo123!.',
  }
