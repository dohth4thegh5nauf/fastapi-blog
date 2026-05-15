"""Quick start example - minimal setup to get started.

Run this example:
    cd tests/examples
    uvicorn quickstart:app --reload

Then open:
    Blog:     http://localhost:8000/blog
    Admin UI: http://localhost:8000/admin (web interface)
    API Docs: http://localhost:8000/docs (REST API docs)

Login credentials:
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

from fastapi import FastAPI  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

import fastapi_blog  # noqa: E402


# Create necessary directories
Path("posts").mkdir(exist_ok=True)
Path("pages").mkdir(exist_ok=True)
Path("static").mkdir(exist_ok=True)

# Create FastAPI app
app = FastAPI(title="My Blog")

# Add blog functionality with i18n
fastapi_blog.add_blog_to_fastapi(
    app,
    prefix="blog",
    strict_frontmatter=False,
    sanitize_html=False,
    locales=["en", "ru"],  # Enable language switcher in blog
    default_locale="en",
)

# Add admin panel (database auto-initialized on startup)
# New API: creates /admin/en and /admin/ru, /admin redirects to /admin/en
admins = fastapi_blog.add_admin_to_app(
    app,
    title="Blog Admin",
    admin_username="admin",
    admin_password="Admin123!",
    secret_key="change-me-in-production",
    locales=["en", "ru"],
    default_locale="en",  # /admin → /admin/en
    enable_role_management=True,  # Enable role management (visible only to root admin)
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    """Homepage with links and instructions."""
    return {
        "message": "Welcome to FastAPI Blog!",
        "links": {
            "blog": "http://localhost:8000/blog",
            "admin": "http://localhost:8000/admin",
            "api_docs": "http://localhost:8000/docs",
        },
        "admin_login": {
            "username": "admin",
            "password": "Admin123!",
            "note": "⚠️ Change these credentials in production!",
        },
        "first_steps": [
            "1. Go to /admin and login",
            "2. Create your first blog post",
            "3. View it at /blog",
        ],
    }
