from typing import Any

import jinja2
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from .admin import add_admin_to_app, Admin
from .editor import add_editor_to_app, get_api_router
from .main import add_blog_to_fastapi
from .router import get_blog_router


__version__ = "0.8.0"

def setup_fastapi_blog(
    app: FastAPI,
    *,
    posts_dir: str = "posts",
    include_api: bool = False,
    locales: list[str] = ["en"],
    default_locale: str = "en",
    admin_username: str | None = None,
    admin_password: str | None = None,
    secret_key: str | None = None,
    enable_role_management: bool = False,
) -> dict[str, Admin]:
    add_blog_to_fastapi(app, posts_dir=posts_dir, include_api=include_api)
    return add_admin_to_app(
        app,
        locales=locales,
        default_locale=default_locale,
        admin_username=admin_username,
        admin_password=admin_password,
        secret_key=secret_key,
        enable_role_management=enable_role_management,
    )
