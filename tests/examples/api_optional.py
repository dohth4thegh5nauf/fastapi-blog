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

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

import fastapi_blog


app = FastAPI(title='Blog with Optional API')

# Add session middleware for authentication
app.add_middleware(SessionMiddleware, secret_key='change-me-in-production')

# Add blog with REST API enabled
fastapi_blog.add_blog_to_fastapi(
  app,
  prefix='blog',
  include_api=True,  # Enable REST API
  api_prefix='/api/posts',
  api_require_auth=True,  # Require authentication for API
  strict_frontmatter=False,
  sanitize_html=False,
)

# Add admin panel (recommended for management)
fastapi_blog.add_admin_to_app(
  app,
  title='Blog Admin',
  admin_username='admin',
  admin_password='Admin123!',
  secret_key='change-me-in-production',
  add_session_middleware=False,  # Already added above
)

app.mount('/static', StaticFiles(directory='static'), name='static')


@app.get('/')
async def index() -> dict:
  return {
    'message': 'Blog with optional REST API example',
    'blog': 'http://localhost:8000/blog',
    'admin': 'http://localhost:8000/dashboard',
    'api_docs': 'http://localhost:8000/docs',
    'note': 'REST API at /api/posts requires authentication',
  }
