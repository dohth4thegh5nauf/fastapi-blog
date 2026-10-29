from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

import fastapi_blog


app = FastAPI()

# Add session middleware for authentication (required by editor)
app.add_middleware(SessionMiddleware, secret_key='change-me-in-production')

# Existing example posts use extra frontmatter fields and raw HTML,
# so strict validation and HTML sanitization are disabled here.
app = fastapi_blog.add_blog_to_fastapi(
  app, strict_frontmatter=False, sanitize_html=False
)

# Add editor with authentication enabled
# To use the editor, login via admin panel first:
# 1. Add admin panel: fastapi_blog.add_admin_to_app(app)
# 2. Or use require_auth=False for testing/public access
app = fastapi_blog.add_editor_to_app(app, strict=False, require_auth=True)

app.mount('/static', StaticFiles(directory='static'), name='static')


@app.get('/')
async def index() -> dict:
  return {
    'message': 'Blog at /blog, editor API at /api/posts (see /docs)',
    'blog': 'http://localhost:8000/blog',
    'api_docs': 'http://localhost:8000/docs',
  }
