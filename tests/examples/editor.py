from demo_auth import create_demo_auth_provider
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import fastapi_blog


app = FastAPI()

session_secret = 'example-only-session-secret-value-0123456789abcdef0123456789'

# Existing example posts use extra frontmatter fields and raw HTML,
# so strict validation and HTML sanitization are disabled here.
app = fastapi_blog.add_blog_to_fastapi(
  app, strict_frontmatter=False, sanitize_html=False
)

# Add the demo Admin login and editor with the same session secret.
fastapi_blog.add_admin_to_app(
  app,
  auth_provider=lambda locale: create_demo_auth_provider(locale),
  secret_key=session_secret,
)
app = fastapi_blog.add_editor_to_app(app, strict=False, require_auth=True)

app.mount('/static', StaticFiles(directory='static'), name='static')


@app.get('/')
async def index() -> dict:
  return {
    'message': 'Blog at /blog, editor API at /api/posts (see /docs)',
    'blog': 'http://localhost:8000/blog',
    'api_docs': 'http://localhost:8000/docs',
  }
