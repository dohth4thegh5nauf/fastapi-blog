"""Example using environment variables for configuration.

Run this example:
    # Set environment variables
    export FASTAPI_BLOG_INCLUDE_API=true
    export FASTAPI_BLOG_ADMIN_LOGIN=myuser
    export FASTAPI_BLOG_ADMIN_PASSWORD=mypass123

    # Run the app
    cd tests/examples
    uvicorn with_env_vars:app --reload

Then open:
    Blog:     http://localhost:8000/blog
    Admin UI: http://localhost:8000/admin
    API Docs: http://localhost:8000/docs (REST API included because of env var)

Login credentials (from environment variables):
    Username: myuser (or default 'admin')
    Password: mypass123 (or default 'Admin123!')
"""

import sys  # noqa: I001
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import fastapi_blog

# Clear any cached imports
for mod in list(sys.modules.keys()):
    if mod.startswith("fastapi_blog"):
        del sys.modules[mod]


# Create necessary directories
Path("posts").mkdir(exist_ok=True)
Path("pages").mkdir(exist_ok=True)
Path("static").mkdir(exist_ok=True)

# Create FastAPI app
app = FastAPI(title="My Blog with Env Vars")

# Add blog functionality - reads FASTAPI_BLOG_INCLUDE_API from environment
# If FASTAPI_BLOG_INCLUDE_API=true, REST API will be included at /api/posts
fastapi_blog.add_blog_to_fastapi(
    app,
    prefix="blog",
    strict_frontmatter=False,
    sanitize_html=False,
    # include_api not specified - will use FASTAPI_BLOG_INCLUDE_API env var
)

# Add admin panel - reads credentials from environment
# Uses FASTAPI_BLOG_ADMIN_LOGIN and FASTAPI_BLOG_ADMIN_PASSWORD if set
admins = fastapi_blog.add_admin_to_app(
    app,
    title="Blog Admin",
    # admin_username not specified - will use FASTAPI_BLOG_ADMIN_LOGIN env var or default 'admin'
    # admin_password not specified - will use FASTAPI_BLOG_ADMIN_PASSWORD env var or default 'Admin123!'
    secret_key="change-me-in-production",
    locales=["en", "ru"],
    default_locale="en",
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    """Homepage with links and environment variable status."""
    import os

    include_api = os.getenv("FASTAPI_BLOG_INCLUDE_API", "false")
    admin_login = os.getenv("FASTAPI_BLOG_ADMIN_LOGIN", "admin")

    return {
        "message": "Welcome to FastAPI Blog with Environment Variables!",
        "environment_variables": {
            "FASTAPI_BLOG_INCLUDE_API": include_api,
            "FASTAPI_BLOG_ADMIN_LOGIN": admin_login,
            "FASTAPI_BLOG_ADMIN_PASSWORD": "***"
            if os.getenv("FASTAPI_BLOG_ADMIN_PASSWORD")
            else "default",
        },
        "links": {
            "blog": "http://localhost:8000/blog",
            "admin": "http://localhost:8000/admin",
            "api_docs": "http://localhost:8000/docs",
        },
        "info": {
            "rest_api": "Enabled"
            if include_api.lower() in ("true", "1", "yes")
            else "Disabled",
            "admin_username": admin_login,
        },
    }
