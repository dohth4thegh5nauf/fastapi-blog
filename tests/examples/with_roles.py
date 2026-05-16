"""Example with role-based access control.

This example demonstrates how to use the Role and UserWithRoles models
for more granular access control.

Run this example:
    cd tests/examples
    uvicorn with_roles:app --reload

Then open:
    Admin UI: http://localhost:8000/admin

Note: This example shows how to set up role management views.
      The actual role enforcement logic needs to be implemented
      in your auth provider (see RoleBasedAuthProvider).
"""

import sys  # noqa: I001
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import fastapi_blog
from fastapi_blog.admin import RoleModelView, UserWithRolesModelView

# Clear any cached imports
for mod in list(sys.modules.keys()):
    if mod.startswith("fastapi_blog"):
        del sys.modules[mod]


# Create necessary directories
Path("posts").mkdir(exist_ok=True)
Path("pages").mkdir(exist_ok=True)
Path("static").mkdir(exist_ok=True)

# Create FastAPI app
app = FastAPI(title="Blog with Roles")

# Add blog functionality
fastapi_blog.add_blog_to_fastapi(
    app,
    prefix="blog",
    strict_frontmatter=False,
    sanitize_html=False,
)

# Add admin panel
admins = fastapi_blog.add_admin_to_app(
    app,
    title="Blog Admin with Roles",
    admin_username="admin",
    admin_password="Admin123!",
    secret_key="change-me-in-production",
    locales=["en", "ru"],
    default_locale="en",
)

# Add role management views to each locale admin
for locale, admin in admins.items():
    # Add Role management view
    from fastapi_blog.admin.models import Role, UserWithRoles

    role_view = RoleModelView(Role, icon="fa fa-shield")
    admin.add_view(role_view)

    # Add UserWithRoles management view
    user_roles_view = UserWithRolesModelView(UserWithRoles, icon="fa fa-users-cog")
    admin.add_view(user_roles_view)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    """Homepage with links."""
    return {
        "message": "Welcome to FastAPI Blog with Role Management!",
        "links": {
            "blog": "http://localhost:8000/blog",
            "admin": "http://localhost:8000/admin",
        },
        "features": [
            "Role-based access control",
            "User management with roles",
            "Granular permissions",
        ],
        "admin_login": {
            "username": "admin",
            "password": "Admin123!",
        },
    }
